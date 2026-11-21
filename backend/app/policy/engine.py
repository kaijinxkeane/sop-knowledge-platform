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
    if isinstance(raw, str):
        return _BY_LABEL.get(raw.strip(), Sensitivity.RESTRICTED)
    return Sensitivity.RESTRICTED


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
class Principal:
    """The signed-in user as the policy engine sees them."""

    user_id: UUID
    roles: frozenset[str]
    grants: tuple[GrantRule, ...] = field(default_factory=tuple)

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
