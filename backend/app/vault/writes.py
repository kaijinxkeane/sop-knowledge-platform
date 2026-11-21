"""Who may save what (plan §3.2, §4.1). Enforced on every app save.

- Saving needs `contribute` on the note's space.
- The one-way rule applies to people too: a save may tighten access freely,
  but widening it (to `public`, below the previous level, to another space, or
  sharing with another space) needs `approve` on that space.
- New notes may start at `internal` or `restricted` without approval.
- Only approvers may set a note's status to `published`.
"""

from __future__ import annotations

from app.policy.engine import Principal, Sensitivity
from app.vault.labels import Labels

NEW_NOTE_CEILING = Sensitivity.INTERNAL


class WriteDenied(PermissionError):
    pass


def check_write(
    principal: Principal,
    old: Labels | None,
    new: Labels,
    *,
    old_status: str | None,
    new_status: str | None,
) -> None:
    if new.space is None:
        raise WriteDenied("choose a space for this note")
    if not principal.can("contribute", new.space):
        raise WriteDenied(f"you can't save notes in '{new.space}'")
    approver = principal.can("approve", new.space)

    if old is not None and old.space is not None and old.space != new.space:
        if not principal.can("contribute", old.space) or not approver:
            raise WriteDenied("moving a note to another space needs that space's lead")

    baseline = old.sensitivity if old is not None and old.space is not None else NEW_NOTE_CEILING
    if new.sensitivity < baseline and not approver:
        raise WriteDenied(
            f"making this note '{new.sensitivity.label}' needs approval from the space lead"
        )
    old_shared = {s for s, _ in (old.shared_with if old else [])}
    if {s for s, _ in new.shared_with} - old_shared and not approver:
        raise WriteDenied("sharing a note with another space needs approval from the space lead")

    if new_status in ("published", "retired") and new_status != old_status and not approver:
        raise WriteDenied(f"only the space lead can mark a note {new_status}")
