"""The Concierge: one question in, one section per department out (plan §5).

Request flow:
1. the policy engine gives the user's readable spaces (never the client/LLM)
2. one hybrid search under RLS across those spaces decides routing
3. each chosen space is searched again (its own top passages), still under RLS
4. department agents answer in parallel; their tokens are streamed as events
5. no model merges answers: each department keeps its own section

The data-boundary scope of each agent call covers every space that owns or
shares a passage, so a local-only space's text can't reach a cloud tier
even when the user reads it through a shared space.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents import reuse
from app.agents.department import Section, answer
from app.agents.router import Route, route
from app.db.models import DocumentAccess
from app.db.scoped import apply_reader_scope
from app.governance.approvals import provenance
from app.models.gateway import ModelGateway
from app.models.types import ContentScope
from app.policy.engine import Principal
from app.retrieval.search import Hit, expand, search
from app.spaces import SpaceProfile

log = logging.getLogger("sop.concierge")

ROUTE_HITS = 12
SPACE_HITS = 6


async def retrieve(
    sessions: async_sessionmaker,
    principal: Principal,
    question: str,
    vector: list[float] | None,
    profiles: dict[str, SpaceProfile],
    gateway: ModelGateway | None,
    *,
    programme: str | None = None,
    stage: str | None = None,
) -> tuple[Route, dict[str, list[Hit]]]:
    # Programme/stage filters narrow both searches; access still comes from RLS.
    narrow = {"programme": programme, "stage": stage}
    # spaces shared with a project only in part (selected folders/SOPs) count too
    readable = sorted(set(principal.scopes()) | {p.space for p in principal.partial})
    async with sessions() as s:
        await apply_reader_scope(s, principal)
        # Answers use approved text only (plan §6): live chunks, not retired.
        hits = await search(
            s,
            principal,
            question,
            query_vector=vector,
            limit=ROUTE_HITS,
            live_only=True,
            **narrow,
        )
        chosen = await route(question, hits, readable, profiles, gateway)
        per_space = {
            sp: await expand(
                s,
                await search(
                    s,
                    principal,
                    question,
                    query_vector=vector,
                    space=sp,
                    limit=SPACE_HITS,
                    live_only=True,
                    **narrow,
                ),
                live_only=True,
            )
            for sp in chosen.spaces
        }
        await s.rollback()
    all_hits = [h for hs in per_space.values() for h in hs]
    if all_hits:
        async with sessions() as s:
            info = await provenance(s, [h.document_id for h in all_hits])
        for h in all_hits:
            h.provenance = info.get(h.document_id)
    return chosen, per_space


async def boundary_scope(sessions: async_sessionmaker, space: str, hits: list[Hit]) -> ContentScope:
    """Every space attached to these passages' documents (not limited by RLS)."""
    if not hits:
        return ContentScope.of(space)
    async with sessions() as s:
        spaces = set(
            (
                await s.execute(
                    select(DocumentAccess.space).where(
                        DocumentAccess.document_id.in_({h.document_id for h in hits})
                    )
                )
            ).scalars()
        )
    return ContentScope.of(space, *spaces)


async def _reused(sessions, key: str, space: str):
    try:
        return await reuse.lookup(sessions, key, space)
    except Exception:  # noqa: BLE001 - reuse is an optimisation; answer normally
        log.warning("answer_reuse_failed")
        return None


async def _keep(sessions, key: str, sec) -> None:
    try:
        await reuse.store(sessions, key, sec)
    except Exception:  # noqa: BLE001
        log.warning("answer_reuse_failed")


async def ask(
    *,
    principal: Principal,
    question: str,
    sessions: async_sessionmaker,
    gateway: ModelGateway,
    embed_query: Callable[[str], Awaitable[list[float]]],
    profiles: dict[str, SpaceProfile],
    programme: str | None = None,
    stage: str | None = None,
) -> AsyncIterator[dict]:
    """Yield events: routing, agent_dispatched, token, section_done, done."""
    try:
        vector = await embed_query(question)
    except Exception:  # noqa: BLE001 - keyword search still works
        vector = None
    chosen, per_space = await retrieve(
        sessions, principal, question, vector, profiles, gateway, programme=programme, stage=stage
    )
    yield {
        "type": "routing",
        "spaces": list(chosen.spaces),
        "reason": chosen.reason,
        "semantic": vector is not None,
    }
    if not chosen.spaces:
        yield {"type": "done", "sections": [], "route": chosen}
        return

    queue: asyncio.Queue = asyncio.Queue()

    async def run(space: str) -> None:
        try:
            scope = await boundary_scope(sessions, space, per_space[space])
            passages = per_space[space]
            key = reuse.key_for(gateway, profiles[space], question, passages, scope)
            if passages and (hit := await _reused(sessions, key, space)) is not None:
                hit.passages = passages
                if hit.text:
                    await queue.put({"type": "token", "space": space, "text": hit.text})
                await queue.put({"type": "section_done", "section": hit})
                return
            async for event in answer(gateway, profiles[space], question, passages, scope):
                if event["type"] == "section_done":
                    await _keep(sessions, key, event["section"])
                await queue.put(event)
        except Exception as exc:  # noqa: BLE001 - one department failing doesn't stop others
            sec = Section(space=space, no_answer=True, confidence="low", error=type(exc).__name__)
            await queue.put({"type": "section_done", "section": sec, "error": type(exc).__name__})

    for space in chosen.spaces:
        yield {"type": "agent_dispatched", "space": space}
    tasks = [asyncio.create_task(run(sp)) for sp in chosen.spaces]
    sections: dict[str, Section] = {}
    errors: dict[str, str] = {}
    try:
        while len(sections) < len(tasks):
            event = await queue.get()
            if event["type"] == "section_done":
                sec = event["section"]
                sections[sec.space] = sec
                if event.get("error"):
                    errors[sec.space] = event["error"]
            yield event
    finally:
        for t in tasks:
            t.cancel()
    yield {
        "type": "done",
        "sections": [sections[s] for s in chosen.spaces],
        "route": chosen,
        "errors": errors,
    }
