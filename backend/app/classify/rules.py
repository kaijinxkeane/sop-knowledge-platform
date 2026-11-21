"""The one-way rule (plan §4.1), as pure functions so it can be tested exhaustively.

On a labelled note the AI may make it *more* restricted by itself, never less:
anything looser, a different space or sharing waits for a person. An unplaced
note gets no access from the AI at all until a person places it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.policy.engine import Principal, Sensitivity
from app.vault.labels import Labels

# Name-detector flags kept in documents.safeguards (next to the pattern hits).
NAMES_PENDING = "names_pending"  # not checked yet for this version
NAMES_FOUND = "names_unconfirmed"  # possible client names, awaiting a reviewer
NAME_FLAGS = frozenset({NAMES_PENDING, NAMES_FOUND})
# humans (or, for handovers, the platform's per-person rule) already decided
RULE_SOURCES = frozenset({"frontmatter", "folder_rule", "handover"})
AI_SOURCES = frozenset({"auto_tighten", "approved_ai"})
CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class Proposal:
    space: str | None  # None = unsure
    sensitivity: Sensitivity
    shared_with: tuple[tuple[str, Sensitivity], ...] = ()
    confidence: float = 0.0
    rationale: str = ""
    evidence: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    model: str = ""
    valid: bool = True  # False: the model's reply could not be read

    def labels(self) -> Labels:
        return Labels(
            space=self.space, sensitivity=self.sensitivity, shared_with=list(self.shared_with)
        )


@dataclass
class Decision:
    decision: str  # auto_tighten | queued | quarantined | unchanged
    status: str  # auto_applied | pending | recorded
    apply: Labels | None = None  # labels to put in force now (always stricter)
    notes: list[str] = field(default_factory=list)


def _shares(labels: Labels) -> dict[str, Sensitivity]:
    return {s: lvl for s, lvl in labels.shared_with if s != labels.space}


def is_looser(current: Labels, new: Labels) -> bool:
    """True if `new` lets anyone read something `current` does not."""
    if new.space != current.space or new.sensitivity < current.sensitivity:
        return True
    cur = _shares(current)
    return any(s not in cur or lvl < cur[s] for s, lvl in _shares(new).items())


def decide(
    current: Labels | None,
    proposal: Proposal,
    *,
    known_spaces: set[str],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> Decision:
    """`current` = labels in force (None if unassigned / quarantined)."""
    space_ok = proposal.space in known_spaces
    if not space_ok or proposal.confidence < threshold:
        if current is None:
            return Decision("quarantined", "pending")
        return Decision("queued", "pending", notes=["low confidence: current labels kept"])

    target = Labels(
        space=proposal.space,
        sensitivity=proposal.sensitivity,
        shared_with=[
            (s, lvl) for s, lvl in proposal.shared_with if s in known_spaces and s != proposal.space
        ],
    )
    if current is None:
        # An unplaced note gets no access from the AI at all, not even restricted:
        # a wrong space would show it to the wrong space's leads (seen in the blind
        # eval). It stays visible to its author only until a person places it.
        return Decision("queued", "pending", notes=["unplaced: author only until placed"])

    if is_looser(current, target):
        return Decision("queued", "pending", notes=["looser than now: current labels kept"])
    if (target.space, target.sensitivity, _shares(target)) == (
        current.space,
        current.sensitivity,
        _shares(current),
    ):
        return Decision("unchanged", "recorded")
    return Decision("auto_tighten", "auto_applied", apply=target)


def required_action(target: Labels) -> str:
    """`approve` (the lead) for the widest decisions, otherwise `review`."""
    if target.sensitivity is Sensitivity.PUBLIC or _shares(target):
        return "approve"
    return "review"


def may_approve(principal: Principal, target: Labels, *, is_author: bool) -> bool:
    if target.space is None:
        return False
    action = required_action(target)
    if principal.can(action, target.space):
        return True
    # Authors may place their own note in their own department at
    # internal or restricted (plan §4.1).
    return action == "review" and is_author and principal.can("contribute", target.space)
