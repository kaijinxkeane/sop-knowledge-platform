"""Required reading and sign-off (frontend spec §9.2): who must read what, and
whether their acknowledgement still counts.

An acknowledgement names the approved version that was read. It stops
counting when a later version is approved as a *material change*; minor edits
don't affect it. Acknowledgements are never edited (a DB trigger refuses).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    ReadAcknowledgement,
    ReadingAssignment,
    SopApproval,
    User,
)


async def live_approval(s: AsyncSession, doc: Document) -> SopApproval | None:
    """The approval of the version people read now (None if never approved)."""
    if doc.approved_hash is None:
        return None
    return await s.scalar(
        select(SopApproval)
        .where(SopApproval.document_id == doc.id, SopApproval.content_hash == doc.approved_hash)
        .order_by(SopApproval.approved_at.desc())
        .limit(1)
    )


async def version_number(s: AsyncSession, approval: SopApproval) -> int:
    """1 for the first approved version, 2 for the next, ..."""
    return int(
        await s.scalar(
            select(func.count())
            .select_from(SopApproval)
            .where(
                SopApproval.document_id == approval.document_id,
                SopApproval.approved_at <= approval.approved_at,
            )
        )
        or 1
    )


async def material_floor(s: AsyncSession, doc_id: uuid.UUID) -> datetime | None:
    """When the latest material change was approved: older reads don't count."""
    return await s.scalar(
        select(func.max(SopApproval.approved_at)).where(
            SopApproval.document_id == doc_id, SopApproval.material_change.is_(True)
        )
    )


async def valid_acks(
    s: AsyncSession, doc_id: uuid.UUID, user_ids=None
) -> dict[uuid.UUID, ReadAcknowledgement]:
    """Each user's latest acknowledgement that still counts."""
    floor = await material_floor(s, doc_id)
    q = (
        select(ReadAcknowledgement)
        .join(SopApproval, SopApproval.id == ReadAcknowledgement.approval_id)
        .where(ReadAcknowledgement.document_id == doc_id)
        .order_by(ReadAcknowledgement.acknowledged_at)
    )
    if floor is not None:
        q = q.where(SopApproval.approved_at >= floor)
    if user_ids is not None:
        q = q.where(ReadAcknowledgement.user_id.in_(list(user_ids)))
    out: dict[uuid.UUID, ReadAcknowledgement] = {}
    for a in (await s.execute(q)).scalars():
        out[a.user_id] = a
    return out


def applies_to(a: ReadingAssignment, user: User) -> bool:
    if a.target_type == "user":
        return a.target == str(user.id)
    return a.target in {r.name for r in user.roles}


async def assignments_for(s: AsyncSession, user: User) -> list[ReadingAssignment]:
    roles = [r.name for r in user.roles]
    q = select(ReadingAssignment).where(
        ((ReadingAssignment.target_type == "user") & (ReadingAssignment.target == str(user.id)))
        | ((ReadingAssignment.target_type == "role") & ReadingAssignment.target.in_(roles or [""]))
    )
    return list((await s.execute(q)).scalars())


async def assignees(s: AsyncSession, assignments: list[ReadingAssignment]) -> list[User]:
    """Active people covered by these assignments (a user, or everyone with a role)."""
    users = (await s.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    return [u for u in users if any(applies_to(a, u) for a in assignments)]


def earliest_due(assignments: list[ReadingAssignment], user: User):
    dues = [a.due_on for a in assignments if a.due_on and applies_to(a, user)]
    return min(dues) if dues else None
