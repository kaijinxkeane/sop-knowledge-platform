"""Answer reuse (plan §5.2, cost lever 5).

A department answer is a function of its prompt: the question, the approved
passages retrieved for *this* user (under RLS and the policy engine), the
space's rules, and the models. The key is a hash of exactly those, plus each
passage's document version, so:

- Access is never widened: a stored answer is only served after the asker's own
  retrieval returned the very same passages, which they can therefore read.
- It is invalidated by construction: approving a new version of any cited SOP,
  changing its text, a different set of passages, a new model or new rules all
  give a new key. Old rows are never looked up again and age out.
- Rows are removed at once when a cited document is retracted, or when someone
  marks the answer not helpful; and after `answers.reuse_days`.

Only clean answers are stored: no outages, no fallback-model answers, no
answers the output guard had to trim.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.department import Section, answer_tiers, system_prompt, user_prompt
from app.agents.output_guard import allowed_domains
from app.db.models import AnswerReuse
from app.models.gateway import ModelGateway
from app.models.types import ContentScope
from app.retrieval.search import Hit
from app.spaces import SpaceProfile

VERSION = 1
_SPACE = re.compile(r"\s+")


def normalise(question: str) -> str:
    """Same question, different spacing/case/closing punctuation."""
    return _SPACE.sub(" ", question).strip().rstrip("?!. ").lower()


def reuse_days() -> int:
    from app.vault.labels import vault_config

    return vault_config().answer_reuse_days


def key_for(
    gateway: ModelGateway,
    profile: SpaceProfile,
    question: str,
    passages: list[Hit],
    scope: ContentScope,
) -> str:
    tiers = answer_tiers(gateway, profile)
    models = []
    for t in tiers:
        cfg = gateway.config.tier(t)
        models.append([t, cfg.provider, cfg.model])
    material = {
        "v": VERSION,
        "space": profile.name,
        "system": system_prompt(profile),
        "user": user_prompt(normalise(question), passages),
        "passages": [[str(h.document_id), h.version, str(h.chunk_id)] for h in passages],
        "models": models,
        "scope": sorted(scope.spaces),
        "links": sorted(allowed_domains()),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def _storable(sec: Section) -> bool:
    return (
        sec.error is None
        and sec.fallback_from is None
        and sec.dropped_lines == 0
        and sec.invalid_citations == 0
        and bool(sec.passages)
    )


async def lookup(sessions: async_sessionmaker, key: str, space: str) -> Section | None:
    days = reuse_days()
    if days <= 0:
        return None
    async with sessions() as s, s.begin():
        row = await s.get(AnswerReuse, key)
        if row is None or row.space != space:
            return None
        if row.created_at < datetime.now(UTC) - timedelta(days=days):
            await s.delete(row)
            return None
        await s.execute(
            update(AnswerReuse)
            .where(AnswerReuse.key == key)
            .values(hits=AnswerReuse.hits + 1, last_used_at=datetime.now(UTC))
        )
        d = row.section
    return Section(
        space=space,
        text=d["text"],
        no_answer=d["no_answer"],
        confidence=d["confidence"],
        citations=d["citations"],
        tier=d.get("tier"),
        model=d.get("model"),
        escalated=d.get("escalated", False),
        reused=True,
        reuse_key=key,
    )


async def store(sessions: async_sessionmaker, key: str, sec: Section) -> None:
    if reuse_days() <= 0 or not _storable(sec):
        return
    docs = sorted({h.document_id for h in sec.passages})
    async with sessions() as s, s.begin():
        await s.merge(
            AnswerReuse(
                key=key,
                space=sec.space,
                section={
                    "text": sec.text,
                    "no_answer": sec.no_answer,
                    "confidence": sec.confidence,
                    "citations": sec.citations,
                    "tier": sec.tier,
                    "model": sec.model,
                    "escalated": sec.escalated,
                },
                document_ids=docs,
                hits=0,
            )
        )
    sec.reuse_key = key


async def forget_keys(s, keys) -> int:
    keys = [k for k in keys if k]
    if not keys:
        return 0
    return (await s.execute(delete(AnswerReuse).where(AnswerReuse.key.in_(keys)))).rowcount or 0


async def forget_documents(s, doc_ids: list[uuid.UUID]) -> int:
    if not doc_ids:
        return 0
    return (
        await s.execute(delete(AnswerReuse).where(AnswerReuse.document_ids.overlap(doc_ids)))
    ).rowcount or 0


async def expired(s, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=max(reuse_days(), 0))
    return (
        await s.execute(delete(AnswerReuse).where(AnswerReuse.created_at < cutoff))
    ).rowcount or 0
