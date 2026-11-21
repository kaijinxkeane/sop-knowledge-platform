"""Ask the Concierge (plan §5, §8): conversations and a streamed answer (SSE).

Events on POST /conversations/{id}/messages (text/event-stream):
  routing          {spaces, reason, semantic}
  agent_dispatched {space, title}
  token            {space, text}
  citation         {space, n, document_id, title, vault_path, heading, part, part_number}
  section_done     {space, no_answer, unavailable, confidence, model, escalated, contact?}
  done             {message_id, answered}
Conversations are private to their owner. The audit log and the gap log get
ids and outcomes only, never the question or the answer.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.agents.concierge import ask
from app.agents.department import Section
from app.api.deps import (
    CurrentUser,
    ask_limiter,
    current_user,
    get_db,
    get_gateway,
    get_query_embedder,
    get_session_factory,
)
from app.db.models import ChatMessage, Conversation, GapEvent, MessageCitation, MessageFeedback
from app.spaces import space_profiles

router = APIRouter(tags=["chat"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
NO_SPACES = "You don't have access to any knowledge areas yet. Please ask your manager."
UNAVAILABLE = "The assistant is unavailable right now. Please try again in a few minutes."


class ConversationIn(BaseModel):
    title: str = Field(default="", max_length=120)


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=2, max_length=2000)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sections: list[dict]
    created_at: datetime


class FeedbackIn(BaseModel):
    helpful: bool
    comment: str = Field(default="", max_length=1000)


async def _own(session: AsyncSession, me: CurrentUser, conversation_id: uuid.UUID) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != me.user.id:
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
) -> list[ConversationOut]:
    rows = (
        await session.execute(
            select(Conversation)
            .where(Conversation.user_id == me.user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [ConversationOut(id=str(c.id), title=c.title, updated_at=c.updated_at) for c in rows]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    await _own(session, me, conversation_id)
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        )
    ).scalars()
    return [
        MessageOut(
            id=str(m.id),
            role=m.role,
            content=m.content,
            sections=m.sections,
            created_at=m.created_at,
        )
        for m in rows
    ]


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
    principal, user_id, conv_id = me.principal, me.user.id, conv.id
    profiles = space_profiles()

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
        ):
            kind = ev["type"]
            if kind == "routing":
                route = {"spaces": ev["spaces"], "reason": ev["reason"]}
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
                if sec.no_answer and not answered:
                    s.add(GapEvent(space=sec.space, message_id=msg.id, reason="no_answer"))
                elif not sec.no_answer and sec.confidence == "low":
                    s.add(GapEvent(space=sec.space, message_id=msg.id, reason="low_confidence"))
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
                },
            )
            await s.commit()
        yield _sse("done", {"message_id": str(msg.id), "answered": bool(answered)})

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
    await session.merge(
        MessageFeedback(
            message_id=msg.id,
            user_id=me.user.id,
            helpful=body.helpful,
            comment=body.comment.strip(),
        )
    )
    if not body.helpful:
        for sec in msg.sections:
            if not sec.get("no_answer"):
                session.add(GapEvent(space=sec["space"], message_id=msg.id, reason="not_helpful"))
    await session.commit()
