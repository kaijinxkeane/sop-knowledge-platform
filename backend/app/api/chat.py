"""Ask the Concierge (plan §5, §8): conversations and a streamed answer (SSE).

Events on POST /conversations/{id}/messages (text/event-stream):
  routing          {spaces, reason, semantic}
  agent_dispatched {space, title}
  token            {space, text}
  citation         {space, n, document_id, title, vault_path, heading, part, part_number,
                    version, written_by, approved_by, approval, approved_on}
  section_done     {space, no_answer, unavailable, confidence, model, escalated, contact?}
  done             {message_id, question_id, answered, followups}
Conversations are private to their owner. The audit log and the gap log get
ids and outcomes only, never the question or the answer.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.agents.concierge import ask
from app.agents.department import Section
from app.agents.followups import followups
from app.api.bookmarks import _like as like_pattern
from app.api.deps import (
    CurrentUser,
    ask_limiter,
    current_user,
    get_db,
    get_gateway,
    get_query_embedder,
    get_session_factory,
)
from app.db.models import (
    ChatMessage,
    Conversation,
    Document,
    GapEvent,
    MessageCitation,
    MessageFeedback,
)
from app.db.scoped import apply_reader_scope, visible
from app.spaces import space_profiles

router = APIRouter(tags=["chat"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
NO_SPACES = "You don't have access to any knowledge areas yet. Please ask your manager."
UNAVAILABLE = "The assistant is unavailable right now. Please try again in a few minutes."


class ConversationIn(BaseModel):
    title: str = Field(default="", max_length=120)


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    # Optional filters (frontend spec §4); they only narrow what you can read.
    programme: str | None = Field(default=None, max_length=200)
    stage: str | None = Field(default=None, max_length=32)


class FollowUpOut(BaseModel):
    document_id: str
    title: str
    heading: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sections: list[dict]
    created_at: datetime
    # latest answer only: other sections of the SOPs it cited, re-read under today's access
    followups: list[FollowUpOut] = []


FEEDBACK_REASONS = ("wrong", "outdated", "missing_steps", "unclear", "other")


class FeedbackIn(BaseModel):
    helpful: bool
    # 👎 reasons (frontend spec §4); they feed gap topics and the improvement set.
    reason: Literal["wrong", "outdated", "missing_steps", "unclear", "other"] | None = None
    comment: str = Field(default="", max_length=1000)


async def _own(session: AsyncSession, me: CurrentUser, conversation_id: uuid.UUID) -> Conversation:
    """Your own conversation; someone else's or a hidden one is a 404."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != me.user.id or conv.hidden_at is not None:
        raise NOT_FOUND
    return conv


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = Conversation(user_id=me.user.id, title=body.title.strip())
    session.add(conv)
    await session.commit()
    return ConversationOut(id=str(conv.id), title=conv.title, updated_at=conv.updated_at)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=100),
) -> list[ConversationOut]:
    """Your conversations, newest first. `q` matches titles and your own
    questions (never stored or logged)."""
    query = select(Conversation).where(
        Conversation.user_id == me.user.id, Conversation.hidden_at.is_(None)
    )
    if q and q.strip():
        pattern = like_pattern(q.strip().lower())
        query = query.where(
            or_(
                func.lower(Conversation.title).like(pattern, escape="\\"),
                exists().where(
                    ChatMessage.conversation_id == Conversation.id,
                    ChatMessage.role == "user",
                    func.lower(ChatMessage.content).like(pattern, escape="\\"),
                ),
            )
        )
    rows = (
        await session.execute(query.order_by(Conversation.updated_at.desc()).limit(limit))
    ).scalars()
    return [ConversationOut(id=str(c.id), title=c.title, updated_at=c.updated_at) for c in rows]


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: RenameIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = await _own(session, me, conversation_id)
    conv.title = body.title.strip()[:120] or conv.title
    await session.commit()
    return ConversationOut(id=str(conv.id), title=conv.title, updated_at=conv.updated_at)


@router.post("/conversations/{conversation_id}/hide", status_code=204)
async def hide_conversation(
    conversation_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Hide it from your view. It isn't deleted: the audit copy is kept until
    the 24-month retention job, as the staff notice says."""
    conv = await _own(session, me, conversation_id)
    conv.hidden_at = datetime.now(UTC)
    await audit.record(
        session,
        "conversation_hidden",
        actor_id=me.user.id,
        target_type="conversation",
        target_id=conv.id,
    )
    await session.commit()


HIDDEN_SECTION = "[Hidden: this part used an SOP you can no longer open.]"


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    """Your history. Old answers are re-checked against what you can read
    today: a part that cited an SOP you've since lost access to (moved team,
    note made restricted, retracted) is hidden (red-team, 2026-11-22)."""
    await _own(session, me, conversation_id)
    rows = (
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    cited: dict[uuid.UUID, set[uuid.UUID]] = {}
    for c in (
        await session.execute(
            select(MessageCitation).where(MessageCitation.message_id.in_([m.id for m in rows]))
        )
    ).scalars():
        if c.document_id:
            cited.setdefault(c.message_id, set()).add(c.document_id)

    def section_docs(sec: dict) -> set[uuid.UUID]:
        out = set()
        for c in sec.get("citations") or []:
            try:
                out.add(uuid.UUID(str(c.get("document_id"))))
            except (ValueError, TypeError, AttributeError):
                continue
        return out

    docs_needed = set().union(*cited.values()) if cited else set()
    for m in rows:
        for sec in m.sections or []:
            docs_needed |= section_docs(sec)
    principal = me.principal
    readable: set[uuid.UUID] = set()
    if docs_needed:
        await session.commit()
        await apply_reader_scope(session, principal)
        for d in docs_needed:
            doc = await session.get(Document, d)
            if doc is not None and visible(principal, doc):
                readable.add(d)
        await session.commit()

    out = []
    last_answer = next((m.id for m in reversed(rows) if m.role == "assistant"), None)
    for m in rows:
        content, sections = m.content, m.sections or []
        hidden = False
        if m.role == "assistant":
            kept = []
            for sec in sections:
                if section_docs(sec) - readable:
                    hidden = True
                    kept.append(
                        {
                            "space": sec.get("space"),
                            "text": HIDDEN_SECTION,
                            "citations": [],
                            "hidden": True,
                        }
                    )
                else:
                    kept.append(sec)
            # citations recorded only in message_citations (older rows): all or nothing
            if cited.get(m.id, set()) - readable and not hidden:
                hidden = True
                kept = [{"space": None, "text": HIDDEN_SECTION, "citations": [], "hidden": True}]
            if hidden:
                sections = kept
                content = "\n\n".join(x["text"] for x in kept if x.get("text"))
        chips: list[dict] = []
        if m.id == last_answer and not hidden:
            cited_parts = [
                (c.get("document_id"), c.get("heading"))
                for sec in sections
                for c in sec.get("citations") or []
                if isinstance(c, dict)
            ]
            if cited_parts:
                await session.commit()
                chips = await followups(session, principal, cited_parts)
                await session.commit()
        out.append(
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=content,
                sections=sections,
                created_at=m.created_at,
                followups=[FollowUpOut(**c) for c in chips],
            )
        )
    return out


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _section_record(sec: Section, contact: str) -> dict:
    return {
        "space": sec.space,
        "text": sec.text,
        "no_answer": sec.no_answer,
        "unavailable": sec.error is not None,
        "confidence": sec.confidence,
        "citations": sec.citations,
        "contact": contact if sec.no_answer else None,
        "model": sec.model,
        "tier": sec.tier,
        "fallback_from": sec.fallback_from,
        "escalated": sec.escalated,
        "reused": sec.reused,
        "reuse_key": sec.reuse_key,
    }


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    sessions: async_sessionmaker = Depends(get_session_factory),
    gateway=Depends(get_gateway),
    embed_query=Depends(get_query_embedder),
) -> StreamingResponse:
    if not ask_limiter.check(str(me.user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many questions; wait a bit")
    conv = await _own(session, me, conversation_id)
    question = body.content.strip()
    user_msg = ChatMessage(conversation_id=conv.id, role="user", content=question)
    session.add(user_msg)
    if not conv.title:
        conv.title = question[:80]
    await session.commit()
    principal, user_id, conv_id, question_id = me.principal, me.user.id, conv.id, user_msg.id
    filters = {
        "programme": (body.programme or "").strip() or None,
        "stage": (body.stage or "").strip() or None,
    }
    from app.projects.service import project_profiles

    profiles = space_profiles() | await project_profiles(session)

    async def events():
        sections: list[Section] = []
        route = None
        async for ev in ask(
            principal=principal,
            question=question,
            sessions=sessions,
            gateway=gateway,
            embed_query=embed_query,
            profiles=profiles,
            programme=filters["programme"],
            stage=filters["stage"],
        ):
            kind = ev["type"]
            if kind == "routing":
                route = {"spaces": ev["spaces"], "reason": ev["reason"]}
                if any(filters.values()):
                    route["filters"] = {k: v for k, v in filters.items() if v}
                yield _sse("routing", ev)
            elif kind == "agent_dispatched":
                yield _sse(kind, {"space": ev["space"], "title": profiles[ev["space"]].title})
            elif kind == "token":
                yield _sse("token", ev)
            elif kind == "section_done":
                sec: Section = ev["section"]
                for c in sec.citations:
                    yield _sse("citation", {"space": sec.space, **c})
                yield _sse(
                    "section_done",
                    {
                        "space": sec.space,
                        "no_answer": sec.no_answer,
                        "unavailable": sec.error is not None,
                        "confidence": sec.confidence,
                        "model": sec.model,
                        "escalated": sec.escalated,
                        "reused": sec.reused,
                        "contact": profiles[sec.space].contact if sec.no_answer else None,
                    },
                )
            elif kind == "done":
                sections = ev["sections"]
        answered = [s for s in sections if not s.no_answer]
        shown = answered or sections  # no-answer sections are hidden if another answered
        if not sections:
            content = NO_SPACES
        elif not answered and any(s.error for s in sections):
            content = UNAVAILABLE
        elif not answered:
            contacts = " ".join(dict.fromkeys(profiles[s.space].contact for s in sections))
            content = f"I couldn't find an SOP that covers this. {contacts}"
        else:
            content = "\n\n".join(s.text for s in answered)
        async with sessions() as s:
            msg = ChatMessage(
                conversation_id=conv_id,
                role="assistant",
                content=content,
                route=route or {},
                sections=[_section_record(x, profiles[x.space].contact) for x in shown],
            )
            s.add(msg)
            await s.flush()
            for sec in answered:
                for c in sec.citations:
                    s.add(
                        MessageCitation(
                            message_id=msg.id,
                            space=sec.space,
                            n=c["n"],
                            document_id=uuid.UUID(c["document_id"]),
                            git_commit=c["version"],
                            part=c["part"],
                            part_number=c["part_number"],
                        )
                    )
            for sec in sections:
                if sec.error:
                    continue  # an outage is not a gap in the SOPs
                gap = {
                    "space": sec.space,
                    "message_id": msg.id,
                    "user_id": user_id,
                    "question_id": question_id,
                }
                if sec.no_answer and not answered:
                    s.add(GapEvent(**gap, reason="no_answer"))
                elif not sec.no_answer and sec.confidence == "low":
                    s.add(GapEvent(**gap, reason="low_confidence"))
            conv = await s.get(Conversation, conv_id)
            conv.updated_at = datetime.now(UTC)
            await audit.record(
                s,
                "question_answered",
                actor_id=user_id,
                target_type="message",
                target_id=msg.id,
                details={
                    "conversation": str(conv_id),
                    "route": (route or {}).get("reason"),
                    "spaces": [x.space for x in sections],
                    "answered": [x.space for x in answered],
                    "documents": sorted({c["document_id"] for x in answered for c in x.citations}),
                    "models": sorted({x.model for x in sections if x.model}),
                    "reused": [x.space for x in sections if x.reused],
                },
            )
            await s.commit()
        chips: list[dict] = []
        cited_parts = [(c["document_id"], c["heading"]) for x in answered for c in x.citations]
        if cited_parts:
            async with sessions() as s:
                chips = await followups(s, principal, cited_parts)
                await s.rollback()
        # question_id: the key for "Request an SOP" (POST /me/gaps/request) after a no-answer.
        yield _sse(
            "done",
            {
                "message_id": str(msg.id),
                "question_id": str(question_id),
                "answered": bool(answered),
                "followups": chips,
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{message_id}/feedback", status_code=204)
async def feedback(
    message_id: uuid.UUID,
    body: FeedbackIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    msg = await session.get(ChatMessage, message_id)
    if msg is None or msg.role != "assistant":
        raise NOT_FOUND
    await _own(session, me, msg.conversation_id)
    if body.helpful and body.reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "reasons are for 'not helpful'")
    await session.merge(
        MessageFeedback(
            message_id=msg.id,
            user_id=me.user.id,
            helpful=body.helpful,
            reason=body.reason,
            comment=body.comment.strip(),
        )
    )
    if not body.helpful:
        # never serve this answer to anyone again
        from app.agents.reuse import forget_keys

        await forget_keys(session, [sec.get("reuse_key") for sec in msg.sections])
        question = await session.scalar(
            select(ChatMessage.id)
            .where(
                ChatMessage.conversation_id == msg.conversation_id,
                ChatMessage.role == "user",
                ChatMessage.created_at <= msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        for sec in msg.sections:
            if not sec.get("no_answer"):
                session.add(
                    GapEvent(
                        space=sec["space"],
                        message_id=msg.id,
                        reason="not_helpful",
                        user_id=me.user.id,
                        question_id=question,
                    )
                )
    await session.commit()
