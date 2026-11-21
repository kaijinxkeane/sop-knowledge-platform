"""The signed-in user: profile, effective permissions, staff notice, spaces."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import CurrentUser, current_user, get_db
from app.db.models import NoticeAcknowledgement, Space
from app.identity import load_notice

router = APIRouter(tags=["me"])


class NoticeStatus(BaseModel):
    version: str
    acknowledged: bool


class MeOut(BaseModel):
    id: str
    email: str
    display_name: str
    home_space: str | None
    roles: list[str]
    scopes: dict[str, str]  # space -> highest sensitivity readable
    space_actions: dict[str, list[str]]
    global_actions: list[str]
    notice: NoticeStatus


class NoticeOut(NoticeStatus):
    markdown: str


class AckIn(BaseModel):
    version: str


class SpaceOut(BaseModel):
    name: str
    title: str
    access: str | None
    actions: list[str]


async def _acknowledged(session: AsyncSession, me: CurrentUser, version: str) -> bool:
    return await session.get(NoticeAcknowledgement, (me.user.id, version)) is not None


@router.get("/me", response_model=MeOut)
async def get_me(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> MeOut:
    p = me.principal
    notice = load_notice()
    return MeOut(
        id=str(me.user.id),
        email=me.user.email,
        display_name=me.user.display_name,
        home_space=me.user.home_space,
        roles=sorted(p.roles),
        scopes={s: level.label for s, level in sorted(p.scopes().items())},
        space_actions={s: sorted(a) for s, a in sorted(p.space_actions().items())},
        global_actions=sorted(p.global_actions()),
        notice=NoticeStatus(
            version=notice.version, acknowledged=await _acknowledged(session, me, notice.version)
        ),
    )


@router.get("/notice", response_model=NoticeOut)
async def get_notice(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> NoticeOut:
    notice = load_notice()
    return NoticeOut(
        version=notice.version,
        markdown=notice.markdown,
        acknowledged=await _acknowledged(session, me, notice.version),
    )


@router.post("/notice/acknowledge", status_code=204)
async def acknowledge_notice(
    body: AckIn, me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> None:
    notice = load_notice()
    if body.version != notice.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "the notice has changed; reload it")
    if not await _acknowledged(session, me, notice.version):
        session.add(NoticeAcknowledgement(user_id=me.user.id, notice_version=notice.version))
        await audit.record(
            session, "notice_acknowledged", actor_id=me.user.id, details={"version": notice.version}
        )
        await session.commit()


@router.get("/spaces", response_model=list[SpaceOut])
async def list_spaces(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[SpaceOut]:
    """Spaces the user can use. Spaces with no access are not listed at all."""
    scopes, actions = me.principal.scopes(), me.principal.space_actions()
    spaces = (await session.execute(select(Space).order_by(Space.name))).scalars().all()
    return [
        SpaceOut(
            name=s.name,
            title=s.title,
            access=scopes[s.name].label,
            actions=sorted(actions.get(s.name, ())),
        )
        for s in spaces
        if s.name in scopes
    ]
