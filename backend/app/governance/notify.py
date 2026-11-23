"""In-app notifications and who receives them. Rows hold ids only."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Notification, User
from app.identity import principal_for


async def users_with(s: AsyncSession, action: str, space: str) -> list[uuid.UUID]:
    """Active users who hold `action` on `space` (e.g. the space's leads).

    Project spaces (`p-...`) have no role grants: their approver is the project
    lead and their reviewers are its members, worked out exactly as on a
    request (`principal_with_projects`), so an ended project asks nobody."""
    if not space.startswith("p-"):
        users = (await s.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        return [u.id for u in users if principal_for(u).can(action, space)]
    from app.db.models import Project
    from app.projects.service import principal_with_projects

    p = (await s.execute(select(Project).where(Project.space == space))).scalar_one_or_none()
    if p is None:
        return []
    ids = {p.lead_id, *(m.user_id for m in p.members)}
    users = (
        (await s.execute(select(User).where(User.id.in_(ids), User.is_active.is_(True))))
        .scalars()
        .all()
    )
    out = []
    for u in users:
        if (await principal_with_projects(s, u, principal_for(u))).can(action, space):
            out.append(u.id)
    return out


async def users_with_role(s: AsyncSession, roles: Iterable[str]) -> list[uuid.UUID]:
    wanted = set(roles)
    users = (await s.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    return [u.id for u in users if wanted & {r.name for r in u.roles}]


async def notify(
    s: AsyncSession,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    *,
    document_id: uuid.UUID | None = None,
    ref_id: str | None = None,
    dedupe: str | None = None,
    skip: uuid.UUID | None = None,
) -> int:
    """Queue one notification per user. With `dedupe`, a user gets it only once."""
    n = 0
    for uid in dict.fromkeys(user_ids):
        if uid is None or uid == skip:
            continue
        stmt = insert(Notification).values(
            id=uuid.uuid4(),
            user_id=uid,
            kind=kind,
            document_id=document_id,
            ref_id=ref_id,
            dedupe_key=f"{dedupe}:{uid}" if dedupe else None,
        )
        if dedupe:
            stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"])
        n += (await s.execute(stmt)).rowcount or 0
    return n
