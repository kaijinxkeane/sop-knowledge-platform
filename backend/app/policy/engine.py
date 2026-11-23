"""The policy engine: who may read and do what (plan §4).

Pure functions, no I/O. Permissions are computed on the server for every
request from the user's roles and grants; nothing here trusts the client or a
model. Anything unknown or malformed resolves to the most restrictive outcome.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from uuid import UUID


class Sensitivity(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    RESTRICTED = 2

    @property
    def label(self) -> str:
        return self.name.lower()


_BY_LABEL = {s.label: s for s in Sensitivity}

# Actions inside one space. `admin` implies every other space action.
SPACE_ACTIONS = frozenset({"ask", "contribute", "review", "approve", "admin"})
# Company-wide actions; only allowed on grants without a space.
GLOBAL_ACTIONS = frozenset({"manage_users", "view_audit", "view_gap_reports"})
# Any of these lets the holder read content in the space.
_READ_ACTIONS = SPACE_ACTIONS


def resolve_sensitivity(raw: object) -> Sensitivity:
    """Fail closed: anything but an exact known label is `restricted`.

    `None`, empty, misspelled ("pubic"), differently cased ("Public") or
    non-string values all resolve to RESTRICTED, never to something looser.
    """
    if isinstance(raw, Sensitivity):  # already resolved
        return raw
    if isinstance(raw, str):
        return _BY_LABEL.get(raw.strip(), Sensitivity.RESTRICTED)
    return Sensitivity.RESTRICTED  # including plain ints: 0 is not "public"


@dataclass(frozen=True)
class GrantRule:
    space: str | None  # None = company-wide grant (global actions only)
    max_sensitivity: Sensitivity
    actions: frozenset[str]


class GrantError(ValueError):
    """A grant that would be unsafe or meaningless."""


def validate_grant(
    space: str | None, max_sensitivity: str, actions: Iterable[str], known_spaces: Iterable[str]
) -> GrantRule:
    actions = frozenset(actions)
    if not actions:
        raise GrantError("a grant needs at least one action")
    if max_sensitivity not in _BY_LABEL:
        raise GrantError(f"unknown sensitivity {max_sensitivity!r}")
    if space is None:
        bad = actions - GLOBAL_ACTIONS
        if bad:
            # Prevents one grant from opening every space at once.
            raise GrantError(
                f"company-wide grants may only hold {sorted(GLOBAL_ACTIONS)}; got {sorted(bad)}"
            )
    else:
        if space not in set(known_spaces):
            raise GrantError(f"unknown space {space!r}")
        bad = actions - SPACE_ACTIONS
        if bad:
            raise GrantError(
                f"space grants may only hold {sorted(SPACE_ACTIONS)}; got {sorted(bad)}"
            )
    return GrantRule(space, _BY_LABEL[max_sensitivity], actions)


@dataclass(frozen=True)
class PartialShare:
    """Part of a department's space shared with a project (selected folders or
    SOPs), approved by that department's lead. Read-only, published SOPs only,
    and never above `level` after the safeguard floor (app/projects)."""

    space: str
    level: Sensitivity
    folders: tuple[str, ...] = ()  # vault path prefixes, ending in "/"
    documents: tuple[str, ...] = ()  # document ids

    def covers(self, path: str | None, doc_id: object | None) -> bool:
        return (doc_id is not None and str(doc_id) in self.documents) or (
            path is not None and any(path.startswith(f) for f in self.folders)
        )


@dataclass(frozen=True)
class Principal:
    """The signed-in user as the policy engine sees them."""

    user_id: UUID
    roles: frozenset[str]
    grants: tuple[GrantRule, ...] = field(default_factory=tuple)
    partial: tuple[PartialShare, ...] = field(default_factory=tuple)

    def scopes(self) -> dict[str, Sensitivity]:
        """allowed_scopes(user) -> {space: highest readable sensitivity} (plan §4)."""
        out: dict[str, Sensitivity] = {}
        for g in self.grants:
            if g.space is None or not (g.actions & _READ_ACTIONS):
                continue
            if g.space not in out or g.max_sensitivity > out[g.space]:
                out[g.space] = g.max_sensitivity
        return out

    def space_actions(self) -> dict[str, frozenset[str]]:
        out: dict[str, set[str]] = {}
        for g in self.grants:
            if g.space is None:
                continue
            acts = SPACE_ACTIONS if "admin" in g.actions else g.actions
            out.setdefault(g.space, set()).update(acts)
        return {k: frozenset(v) for k, v in out.items()}

    def global_actions(self) -> frozenset[str]:
        return frozenset(a for g in self.grants if g.space is None for a in g.actions)

    def can(self, action: str, space: str | None = None) -> bool:
        if space is None:
            return action in self.global_actions()
        return action in self.space_actions().get(space, frozenset())

    def can_read(self, space: str, sensitivity: object) -> bool:
        level = self.scopes().get(space)
        return level is not None and resolve_sensitivity(sensitivity) <= level


def document_visible(principal: Principal, access: Iterable[tuple[str, object]]) -> bool:
    """A document is visible if any of its access rows (space, sensitivity) is readable.

    No rows means unassigned (quarantined): visible to nobody here; reviewers
    reach it only through the classification queue (Phase 2b).
    """
    return any(principal.can_read(space, sens) for space, sens in access)


UNPUBLISHED = frozenset({"draft", "in_review"})


def effective_access(
    access: Iterable[tuple[str, object]], safeguards: Iterable[str] = ()
) -> list[tuple[str, Sensitivity]]:
    """The labels in force, with the safeguard floor applied: any safeguard hit
    (personal data, flagged terms, unchecked or unconfirmed names) makes every
    row `restricted` until it is cleared. Invalid labels resolve to restricted."""
    floor = Sensitivity.RESTRICTED if any(True for _ in safeguards) else Sensitivity.PUBLIC
    return [(space, max(resolve_sensitivity(sens), floor)) for space, sens in access]


def can_view_document(
    principal: Principal,
    access: Iterable[tuple[str, object]],
    *,
    safeguards: Iterable[str] = (),
    status: str | None = None,
    author_id: object | None = None,
    readers: Iterable[object] = (),
    path: str | None = None,
    doc_id: object | None = None,
) -> bool:
    """Python twin of the database's sop_doc_visible() (both must agree):

    - the author of a note made in the app always sees it
    - so does anyone listed as a reader of that one document (handovers)
    - otherwise some access row must be readable after the safeguard floor
    - drafts and notes in review also need `review` on one of those spaces
    """
    if author_id is not None and author_id == principal.user_id:
        return True
    if principal.user_id in set(readers):
        return True
    if principal.partial and status not in UNPUBLISHED:
        eff = effective_access(access, safeguards)
        for p in principal.partial:
            if p.covers(path, doc_id) and any(s == p.space and lvl <= p.level for s, lvl in eff):
                return True
    rows = [
        (s, lvl) for s, lvl in effective_access(access, safeguards) if principal.can_read(s, lvl)
    ]
    if not rows:
        return False
    if status in UNPUBLISHED:
        return any(principal.can("review", s) for s, _ in rows)
    return True


EDIT_ACTIONS = frozenset({"contribute", "review"})


def edit_spaces(principal: Principal) -> list[str]:
    """Spaces where the user may see work in progress (unapproved changes)."""
    return sorted(s for s, acts in principal.space_actions().items() if acts & EDIT_ACTIONS)


def can_see_unapproved(
    principal: Principal,
    access: Iterable[tuple[str, object]],
    *,
    author_id: object | None = None,
) -> bool:
    """Python twin of sop_doc_editor() (on top of can_view_document): the author,
    or someone with contribute/review on one of the document's spaces, sees a
    change that is not approved yet. Everyone else sees the approved version."""
    if author_id is not None and author_id == principal.user_id:
        return True
    spaces = set(edit_spaces(principal))
    return any(space in spaces for space, _ in access)
