"""Home cards (frontend spec §3): what changed recently, and what's waiting
for you. Titles and counts only; every document is re-checked under RLS and
the policy engine, like the Library."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.classifications import queue
from app.api.deps import CurrentUser, current_user, get_db
from app.api.documents import _out, _reader
from app.api.reviews import _can_review
from app.db.models import Document, ReviewRequest, SopApproval
from app.db.scoped import sees_latest, visible

router = APIRouter(tags=["knowledge"])

RECENT_DAYS = 30


class RecentOut(BaseModel):
    id: str
    title: str
    kind: str
    doc_type: str
    programme: str | None
    stage: str | None
    approved_at: datetime


class WaitingOut(BaseModel):
    reviews: int  # changes you can review (not your own requests)
    drafts: int  # notes you started that aren't submitted yet
    labels: int  # AI label suggestions you can see


@router.get("/me/recent", response_model=list[RecentOut])
async def recent(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=6, ge=1, le=20),
) -> list[RecentOut]:
    """SOPs approved in the last 30 days that you can read, newest first."""
    since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    # Approvals are read as the app (no RLS on them), then each document under RLS.
    latest = (
        await session.execute(
            select(SopApproval.document_id, func.max(SopApproval.approved_at).label("at"))
            .where(SopApproval.approved_at >= since)
            .group_by(SopApproval.document_id)
            .order_by(func.max(SopApproval.approved_at).desc())
            .limit(100)
        )
    ).all()
    await _reader(session, me)
    out: list[RecentOut] = []
    for doc_id, at in latest:
        doc = await session.get(Document, doc_id)
        if (
            doc is None
            or doc.approved_hash is None
            or doc.status == "retired"
            or doc.doc_type == "handover"
            or _out(doc, me) is None
        ):
            continue
        out.append(
            RecentOut(
                id=str(doc.id),
                title=doc.title,
                kind=doc.kind,
                doc_type=doc.doc_type,
                programme=doc.programme,
                stage=doc.stage,
                approved_at=at,
            )
        )
        if len(out) >= limit:
            break
    return out


@router.get("/me/waiting", response_model=WaitingOut)
async def waiting(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> WaitingOut:
    labels = sum(len(g.items) for g in await queue(me=me, session=session))
    open_reviews = (
        (await session.execute(select(ReviewRequest).where(ReviewRequest.status == "open")))
        .scalars()
        .all()
    )
    await _reader(session, me)
    reviews = 0
    for r in open_reviews:
        if r.requested_by == me.user.id:
            continue
        doc = await session.get(Document, r.document_id)
        if (
            doc is not None
            and visible(me.principal, doc)
            and sees_latest(me.principal, doc)
            and _can_review(me, doc)
        ):
            reviews += 1
    drafts = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.status == "draft", Document.author_id == me.user.id)
    )
    return WaitingOut(reviews=reviews, drafts=drafts or 0, labels=labels)
