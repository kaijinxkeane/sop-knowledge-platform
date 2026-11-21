"""Handover notes (plan §7, Phase 5).

  POST /handovers                     create (author needs `contribute` on the space)
  GET  /handovers                     the ones I wrote, receive, or lead
  GET  /handovers/{id}                detail, with the note text and rule check
  PUT  /handovers/{id}                author edits fields or receivers
  POST /handovers/{id}/check          rule check + local-model check
  POST /handovers/{id}/send           notify the receivers
  POST /handovers/{id}/acknowledge    a receiver confirms "read and understood"
  GET/POST /handovers/{id}/comments   questions while the author is still around

Only the author, receivers, the space's leads and the CEO roles can read a
handover (per-person rows, enforced by RLS and the policy engine). Anyone else
gets 404. Audit events carry ids only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.api.deps import (
    CurrentUser,
    current_user,
    get_db,
    get_embedder,
    get_gateway,
    get_git,
    get_session_factory,
)
from app.api.notes import safe_name
from app.db.models import Document, Handover, HandoverComment, HandoverReceiver, Space, User
from app.db.scoped import apply_reader_scope, visible
from app.governance.notify import notify
from app.retention.handovers import HandoverFields, check, model_check, render, sync_readers
from app.vault.git import GitVault
from app.vault.indexer import Indexer
from app.vault.labels import vault_config

router = APIRouter(prefix="/handovers", tags=["retention"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")


class HandoverIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    space: str = Field(max_length=64)
    receivers: list[uuid.UUID] = Field(min_length=1, max_length=20)
    fields: HandoverFields


class HandoverUpdate(BaseModel):
    receivers: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=20)
    fields: HandoverFields | None = None


class IssueOut(BaseModel):
    section: str
    message: str
    source: str


class ReceiverOut(BaseModel):
    user_id: str
    name: str
    acknowledged_at: datetime | None


class HandoverOut(BaseModel):
    id: str
    document_id: str
    title: str
    space: str
    status: str
    author: str
    mine: bool
    receivers: list[ReceiverOut]
    created_at: datetime
    sent_at: datetime | None
    issues: list[IssueOut]


class HandoverDetail(HandoverOut):
    fields: HandoverFields
    markdown: str


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(BaseModel):
    id: str
    author: str
    body: str
    created_at: datetime


async def _names(session: AsyncSession, ids) -> dict[uuid.UUID, str]:
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(list(ids))))
    return dict(rows.all())


async def _readable(session: AsyncSession, me: CurrentUser, h: Handover) -> bool:
    """The handover note is readable to this user (RLS + policy engine)."""
    await session.commit()
    await apply_reader_scope(session, me.principal)
    doc = await session.get(Document, h.document_id)
    ok = doc is not None and visible(me.principal, doc)
    await session.commit()
    return ok


async def _load(session: AsyncSession, me: CurrentUser, handover_id: uuid.UUID) -> Handover:
    h = await session.get(Handover, handover_id)
    if h is None or not await _readable(session, me, h):
        raise NOT_FOUND
    await session.refresh(h)
    return h


async def _out(session: AsyncSession, h: Handover, me: CurrentUser, cls=HandoverOut, **extra):
    doc = await session.get(Document, h.document_id)
    names = await _names(session, {h.author_id, *(r.user_id for r in h.receivers)})
    fields = HandoverFields.model_validate(h.fields)
    return cls(
        id=str(h.id),
        document_id=str(h.document_id),
        title=doc.title if doc else "",
        space=h.space,
        status=h.status,
        author=names.get(h.author_id, "unknown"),
        mine=h.author_id == me.user.id,
        receivers=[
            ReceiverOut(
                user_id=str(r.user_id),
                name=names.get(r.user_id, "unknown"),
                acknowledged_at=r.acknowledged_at,
            )
            for r in h.receivers
        ],
        created_at=h.created_at,
        sent_at=h.sent_at,
        issues=[IssueOut(**i.__dict__) for i in check(fields).issues],
        **extra,
    )


async def _active_users(session: AsyncSession, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    found = set(
        (
            await session.execute(select(User.id).where(User.id.in_(ids), User.is_active.is_(True)))
        ).scalars()
    )
    if set(ids) - found:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown receiver")
    return list(dict.fromkeys(ids))


def _write(git: GitVault, rel: str, content: str, me: CurrentUser, message: str) -> str:
    full = git.safe_path(rel)
    with git.lock():
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        if rel not in git.uncommitted():
            return ""
        return git.commit(
            [rel],
            message,
            author_name=me.user.display_name,
            author_email=me.user.email,
            user_id=me.user.id,
        )


@router.post("", response_model=HandoverOut, status_code=201)
async def create_handover(
    body: HandoverIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    sessions: async_sessionmaker = Depends(get_session_factory),
    embed=Depends(get_embedder),
) -> HandoverOut:
    config = vault_config()
    if await session.get(Space, body.space) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown space")
    if not me.principal.can("contribute", body.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't write handovers in this space")
    receivers = await _active_users(session, body.receivers)
    rel = f"{config.handover_folder}/{body.space}/{safe_name(body.title)}.md"
    if git.safe_path(rel).exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "a handover with this title already exists")
    sha = _write(
        git, rel, render(body.title.strip(), body.space, body.fields), me, f"Handover {rel}"
    )
    await Indexer(git, sessions, embed).index_paths([rel])
    async with sessions() as s, s.begin():
        doc = (await s.execute(select(Document).where(Document.vault_path == rel))).scalar_one()
        doc.author_id = me.user.id
        h = Handover(
            document_id=doc.id,
            space=body.space,
            author_id=me.user.id,
            status="draft",
            fields=body.fields.model_dump(mode="json"),
            receivers=[HandoverReceiver(user_id=u) for u in receivers],
        )
        s.add(h)
        await s.flush()
        await sync_readers(s, h, config)
        await audit.record(
            s,
            "handover_created",
            actor_id=me.user.id,
            target_type="handover",
            target_id=h.id,
            details={"document": str(doc.id), "receivers": len(receivers), "commit": sha},
        )
        hid = h.id
    return await _out(session, await session.get(Handover, hid), me)


@router.get("", response_model=list[HandoverOut])
async def list_handovers(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[HandoverOut]:
    all_rows = (
        (await session.execute(select(Handover).order_by(Handover.created_at.desc())))
        .scalars()
        .all()
    )
    await session.commit()
    await apply_reader_scope(session, me.principal)
    keep = []
    for h in all_rows:
        doc = await session.get(Document, h.document_id)
        if doc is not None and visible(me.principal, doc):
            keep.append(h.id)
    await session.commit()
    return [await _out(session, await session.get(Handover, i), me) for i in keep]


@router.get("/{handover_id}", response_model=HandoverDetail)
async def get_handover(
    handover_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> HandoverDetail:
    h = await _load(session, me, handover_id)
    doc = await session.get(Document, h.document_id)
    text = git.safe_path(doc.vault_path).read_text(encoding="utf-8", errors="replace")
    await audit.record(
        session, "handover_viewed", actor_id=me.user.id, target_type="handover", target_id=h.id
    )
    await session.commit()
    return await _out(
        session,
        h,
        me,
        HandoverDetail,
        fields=HandoverFields.model_validate(h.fields),
        markdown=text,
    )


@router.put("/{handover_id}", response_model=HandoverOut)
async def update_handover(
    handover_id: uuid.UUID,
    body: HandoverUpdate,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    sessions: async_sessionmaker = Depends(get_session_factory),
    embed=Depends(get_embedder),
) -> HandoverOut:
    h = await _load(session, me, handover_id)
    if h.author_id != me.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the author can edit a handover")
    doc = await session.get(Document, h.document_id)
    if body.fields is not None:
        title = str((doc.frontmatter or {}).get("title") or doc.title)
        _write(
            git,
            doc.vault_path,
            render(title, h.space, body.fields),
            me,
            f"Update handover {doc.vault_path}",
        )
        h.fields = body.fields.model_dump(mode="json")
    if body.receivers is not None:
        wanted = await _active_users(session, body.receivers)
        acked = {r.user_id: r.acknowledged_at for r in h.receivers}
        h.receivers = [HandoverReceiver(user_id=u, acknowledged_at=acked.get(u)) for u in wanted]
    await session.flush()
    await sync_readers(session, h, vault_config())
    await audit.record(
        session, "handover_updated", actor_id=me.user.id, target_type="handover", target_id=h.id
    )
    await session.commit()
    if body.fields is not None:
        await Indexer(git, sessions, embed).index_paths([doc.vault_path])
    return await _out(session, h, me)


@router.post("/{handover_id}/check", response_model=list[IssueOut])
async def check_handover(
    handover_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    gateway=Depends(get_gateway),
) -> list[IssueOut]:
    h = await _load(session, me, handover_id)
    if h.author_id != me.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the author can run the check")
    doc = await session.get(Document, h.document_id)
    issues = check(HandoverFields.model_validate(h.fields)).issues
    text = git.safe_path(doc.vault_path).read_text(encoding="utf-8", errors="replace")
    issues += await model_check(gateway, text, h.space)
    return [IssueOut(**i.__dict__) for i in issues]


@router.post("/{handover_id}/send", response_model=HandoverOut)
async def send_handover(
    handover_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> HandoverOut:
    h = await _load(session, me, handover_id)
    if h.author_id != me.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the author can send a handover")
    h.status, h.sent_at = "sent", h.sent_at or datetime.now(UTC)
    await notify(
        session,
        [r.user_id for r in h.receivers],
        "handover_received",
        document_id=h.document_id,
        ref_id=str(h.id),
        skip=me.user.id,
    )
    await audit.record(
        session,
        "handover_sent",
        actor_id=me.user.id,
        target_type="handover",
        target_id=h.id,
        details={"receivers": len(h.receivers)},
    )
    await session.commit()
    return await _out(session, h, me)


@router.post("/{handover_id}/acknowledge", response_model=HandoverOut)
async def acknowledge(
    handover_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> HandoverOut:
    h = await _load(session, me, handover_id)
    mine = next((r for r in h.receivers if r.user_id == me.user.id), None)
    if mine is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only a receiver can acknowledge")
    if h.status == "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "this handover hasn't been sent yet")
    mine.acknowledged_at = mine.acknowledged_at or datetime.now(UTC)
    if all(r.acknowledged_at for r in h.receivers):
        h.status = "acknowledged"
    await notify(
        session,
        [h.author_id],
        "handover_acknowledged",
        document_id=h.document_id,
        ref_id=str(h.id),
    )
    await audit.record(
        session,
        "handover_acknowledged",
        actor_id=me.user.id,
        target_type="handover",
        target_id=h.id,
    )
    await session.commit()
    return await _out(session, h, me)


@router.get("/{handover_id}/comments", response_model=list[CommentOut])
async def list_comments(
    handover_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[CommentOut]:
    h = await _load(session, me, handover_id)
    rows = (
        (
            await session.execute(
                select(HandoverComment)
                .where(HandoverComment.handover_id == h.id)
                .order_by(HandoverComment.created_at)
            )
        )
        .scalars()
        .all()
    )
    names = await _names(session, {c.user_id for c in rows})
    return [
        CommentOut(
            id=str(c.id),
            author=names.get(c.user_id, "unknown"),
            body=c.body,
            created_at=c.created_at,
        )
        for c in rows
    ]


@router.post("/{handover_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    handover_id: uuid.UUID,
    body: CommentIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> CommentOut:
    h = await _load(session, me, handover_id)
    c = HandoverComment(handover_id=h.id, user_id=me.user.id, body=body.body.strip())
    session.add(c)
    await session.flush()
    others = [h.author_id, *(r.user_id for r in h.receivers)]
    await notify(
        session,
        others,
        "handover_comment",
        document_id=h.document_id,
        ref_id=str(h.id),
        skip=me.user.id,
    )
    await session.commit()
    return CommentOut(
        id=str(c.id), author=me.user.display_name, body=c.body, created_at=c.created_at
    )
