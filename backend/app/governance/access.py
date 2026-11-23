"""Access follows approval (red-team finding, 2026-11-22).

A document's access rows apply to every version of it, including the live
(approved) text used in answers. If an edit widened access at once, people
newly allowed in would read the *old* text, the one approved under narrower
labels, before anyone approved the change. So while a newer version waits for
approval, the access in force is the overlap of the approved access and the
new one (it can only narrow), and the wider rows wait in `pending_access`
until a lead approves that version. Tightening applies at once.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentAccess
from app.policy.engine import resolve_sensitivity

Row = tuple[str, str, str, str]  # space, role, sensitivity, source


def _rows(items) -> list[Row]:
    return [(str(a), str(b), str(c), str(d)) for a, b, c, d in items or []]


def overlap(new: list[Row], approved: list[Row]) -> list[Row]:
    """Rows no wider than either side: spaces in both, at the stricter level.
    The owner space stays the approved one (a move waits for approval)."""
    old = {space: (role, sens) for space, role, sens, _ in approved}
    out = []
    for space, _role, sens, source in new:
        if space not in old:
            continue
        old_role, old_sens = old[space]
        level = max(resolve_sensitivity(sens), resolve_sensitivity(old_sens))
        out.append((space, old_role, level.label, source))
    if not any(role == "owner" for _, role, _, _ in out):
        # Moved to another space: until the move is approved, the note keeps the
        # access it was approved under (the old space's lead can then approve it).
        return list(approved)
    return out


def is_pending(doc: Document) -> bool:
    return doc.approved_hash is not None and doc.approved_hash != doc.governed_hash


async def current_rows(s: AsyncSession, doc: Document) -> list[Row]:
    rows = (
        await s.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc.id))
    ).scalars()
    return [(r.space, r.role, r.sensitivity, r.source) for r in rows]


async def write_rows(s: AsyncSession, doc: Document, rows: list[Row]) -> None:
    await s.execute(delete(DocumentAccess).where(DocumentAccess.document_id == doc.id))
    await s.flush()
    for space, role, sens, source in rows:
        s.add(
            DocumentAccess(
                document_id=doc.id, space=space, role=role, sensitivity=sens, source=source
            )
        )
    await s.flush()
    s.expire(doc, ["access"])


async def hold_until_approved(s: AsyncSession, doc: Document) -> None:
    """After the indexer set the rows the latest version asks for."""
    if not is_pending(doc) or doc.approved_access is None:
        doc.pending_access = None
        return
    wanted = await current_rows(s, doc)
    allowed = overlap(wanted, _rows(doc.approved_access))
    if sorted(allowed) == sorted(wanted):
        doc.pending_access = None
        return
    doc.pending_access = [list(r) for r in wanted]
    await write_rows(s, doc, allowed)


async def on_approval(s: AsyncSession, doc: Document) -> None:
    """The approved version's access comes into force and becomes the reference."""
    if doc.pending_access is not None:
        await write_rows(s, doc, _rows(doc.pending_access))
        doc.pending_access = None
    doc.approved_access = [list(r) for r in await current_rows(s, doc)]
