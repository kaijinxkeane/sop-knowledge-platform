"""Bookmarks and Ctrl+K quick search (frontend spec §9.4, §11).

Both return titles only, and only for things the user can open now: documents
are read under RLS and the policy engine (like the Library), conversations are
the user's own. A bookmark whose target is hidden or gone is left out of the
list (not deleted: access may come back). Bookmarking something you can't see
answers 404, like the Library. Queries are never logged or stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.api.documents import NOT_FOUND, _out, _reader
from app.db.models import Bookmark, Conversation, Document
from app.vault.labels import vault_config

router = APIRouter(tags=["knowledge"])
MAX_BOOKMARKS = 500


class BookmarkIn(BaseModel):
    target_type: Literal["document", "conversation"]
    target_id: uuid.UUID
    part: int | None = Field(default=None, ge=1, le=10_000)  # slide or page


class BookmarkOut(BaseModel):
    id: str
    target_type: str
    target_id: str
    part: int | None
    title: str
    kind: str | None = None  # note | attachment (documents)
    doc_type: str | None = None
    created_at: datetime


class QuickDoc(BaseModel):
    id: str
    title: str
    kind: str
    doc_type: str
    programme: str | None
    stage: str | None


class QuickConversation(BaseModel):
    id: str
    title: str


class QuickOut(BaseModel):
    documents: list[QuickDoc]
    programmes: list[str]
    stages: list[str]
    bookmarks: list[BookmarkOut]
    conversations: list[QuickConversation]


async def _visible_docs(session: AsyncSession, me: CurrentUser, ids) -> dict[uuid.UUID, Document]:
    """Documents among `ids` this user can open (RLS + policy engine)."""
    ids = list(ids)
    if not ids:
        return {}
    await _reader(session, me)
    docs = (await session.execute(select(Document).where(Document.id.in_(ids)))).scalars()
    return {d.id: d for d in docs if _out(d, me) is not None}


async def _own_conversations(session: AsyncSession, me: CurrentUser, ids) -> dict:
    ids = list(ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(Conversation).where(
            Conversation.id.in_(ids),
            Conversation.user_id == me.user.id,
            Conversation.hidden_at.is_(None),
        )
    )
    return {c.id: c for c in rows.scalars()}


async def _listed(session: AsyncSession, me: CurrentUser) -> list[BookmarkOut]:
    marks = list(
        (
            await session.execute(
                select(Bookmark)
                .where(Bookmark.user_id == me.user.id)
                .order_by(Bookmark.created_at.desc())
            )
        ).scalars()
    )
    convs = await _own_conversations(
        session, me, {b.target_id for b in marks if b.target_type == "conversation"}
    )
    docs = await _visible_docs(
        session, me, {b.target_id for b in marks if b.target_type == "document"}
    )
    out = []
    for b in marks:
        if b.target_type == "document" and (d := docs.get(b.target_id)):
            out.append(
                BookmarkOut(
                    id=str(b.id),
                    target_type=b.target_type,
                    target_id=str(b.target_id),
                    part=b.part,
                    title=d.title,
                    kind=d.kind,
                    doc_type=d.doc_type,
                    created_at=b.created_at,
                )
            )
        elif b.target_type == "conversation" and (c := convs.get(b.target_id)):
            out.append(
                BookmarkOut(
                    id=str(b.id),
                    target_type=b.target_type,
                    target_id=str(b.target_id),
                    part=None,
                    title=c.title or "",
                    created_at=b.created_at,
                )
            )
    return out


@router.get("/me/bookmarks", response_model=list[BookmarkOut])
async def list_bookmarks(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[BookmarkOut]:
    return await _listed(session, me)


@router.post("/me/bookmarks", response_model=BookmarkOut, status_code=201)
async def add_bookmark(
    body: BookmarkIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> BookmarkOut:
    if body.target_type == "document":
        if body.target_id not in await _visible_docs(session, me, [body.target_id]):
            raise NOT_FOUND
    elif body.target_id not in await _own_conversations(session, me, [body.target_id]):
        raise NOT_FOUND
    if body.target_type == "conversation" and body.part is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "conversations have no parts")
    await session.commit()  # back to the owner role: bookmarks aren't behind RLS
    count = await session.scalar(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == me.user.id)
    )
    if (count or 0) >= MAX_BOOKMARKS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"at most {MAX_BOOKMARKS} bookmarks")
    await session.execute(
        insert(Bookmark)
        .values(
            id=uuid.uuid4(),
            user_id=me.user.id,
            target_type=body.target_type,
            target_id=body.target_id,
            part=body.part,
        )
        .on_conflict_do_nothing(constraint="bookmark_once")
    )
    await session.commit()
    for b in await _listed(session, me):
        if (b.target_type, b.target_id, b.part) == (
            body.target_type,
            str(body.target_id),
            body.part,
        ):
            return b
    raise NOT_FOUND  # pragma: no cover - the target was hidden in between


@router.delete("/me/bookmarks/{bookmark_id}", status_code=204)
async def remove_bookmark(
    bookmark_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    result = await session.execute(
        delete(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == me.user.id)
    )
    await session.commit()
    if not result.rowcount:
        raise NOT_FOUND


def _like(q: str) -> str:
    """A LIKE pattern matching `q` literally anywhere (wildcards escaped)."""
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


@router.get("/quick-search", response_model=QuickOut)
async def quick_search(
    q: str = Query(min_length=1, max_length=100),
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> QuickOut:
    """Ctrl+K: titles of documents, programmes, stages, bookmarks and your
    conversations that match `q`. Titles only, never content."""
    needle = " ".join(q.split()).lower()
    if not needle:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "empty query")
    pattern = _like(needle)

    bookmarks = [b for b in await _listed(session, me) if needle in b.title.lower()][:5]
    await session.commit()
    convs = (
        await session.execute(
            select(Conversation)
            .where(
                Conversation.user_id == me.user.id,
                Conversation.hidden_at.is_(None),
                func.lower(Conversation.title).like(pattern, escape="\\"),
            )
            .order_by(Conversation.updated_at.desc())
            .limit(5)
        )
    ).scalars()
    conversations = [QuickConversation(id=str(c.id), title=c.title) for c in convs]

    await _reader(session, me)
    rows = (
        await session.execute(
            select(Document)
            .where(
                func.lower(Document.title).like(pattern, escape="\\")
                | func.lower(Document.programme).like(pattern, escape="\\")
            )
            .order_by(func.length(Document.title))
            .limit(60)
        )
    ).scalars()
    docs = [d for d in rows if _out(d, me) is not None]
    titled = [d for d in docs if needle in d.title.lower()]
    programmes = sorted(
        {
            p
            for d in docs
            if d.programme and (p := d.programme.strip("[]").split("|")[-1]) and needle in p.lower()
        }
    )[:5]
    await session.commit()
    return QuickOut(
        documents=[
            QuickDoc(
                id=str(d.id),
                title=d.title,
                kind=d.kind,
                doc_type=d.doc_type,
                programme=d.programme,
                stage=d.stage,
            )
            for d in titled[:8]
        ],
        programmes=programmes,
        stages=[s for s in vault_config().stages if needle in s.lower()][:5],
        bookmarks=bookmarks,
        conversations=conversations,
    )
