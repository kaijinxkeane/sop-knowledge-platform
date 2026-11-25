"""Gap detection (plan §7).

Nightly, `group_gaps` puts each new gap event (a question a space couldn't
answer well, or an explicit "request an SOP") into a *gap topic* of similar
questions in that space, using local embeddings. A topic's label is written
by the local `router` tier from the questions only (never from SOP text), so
it is safe to show HR. For each topic it also records:
- programme/stage and Library folder, from the nearest approved SOP (no text)
- an *access gap*: a document that covers the topic but that the people
  asking couldn't read (shown to the space's leads only, never to askers)

`personal_gaps` builds the user's own "gaps from your searches" on demand.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.untrusted import REMINDER, tag, with_rules
from app.db.models import ChatMessage, Document, GapEvent, GapTopic, SearchEvent, User
from app.identity import principal_for
from app.models.types import ContentScope, Message
from app.policy.engine import can_view_document
from app.vault.folders import department_of
from app.vault.labels import vault_config

log = logging.getLogger("sop.gaps")
TOPIC_DISTANCE = 0.35  # a question joins a topic if this close to its centre (cosine)
META_DISTANCE = 0.6  # nearest SOP close enough to borrow programme/stage from
ACCESS_DISTANCE = 0.45  # a hidden document this close "covers" the topic
WEAK_DISTANCE = 0.5  # a search whose best semantic match is farther than this is weak
OPENED_UNUSED = 2  # opened this many results and used none
MIN_PEOPLE_FOR_HR = 3
LABEL_SYSTEM = (
    "Several staff asked these questions and the company's SOPs had no good "
    "answer. Write a short topic label (at most 10 words) naming what they "
    "wanted to know. Use only the questions; no names of people or clients. "
    "Reply with the label only."
)


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 1 - dot / (na * nb) if na and nb else 1.0


def _vec(v) -> list[float] | None:
    return None if v is None else [float(x) for x in v]


async def question_texts(s: AsyncSession, events: list[GapEvent]) -> dict[uuid.UUID, str]:
    """The question behind each gap event (chat message or search), by event id."""
    msg_ids = {e.question_id for e in events if e.question_id}
    search_ids = {e.search_event_id for e in events if e.search_event_id}
    msgs = (
        dict(
            (
                await s.execute(
                    select(ChatMessage.id, ChatMessage.content).where(ChatMessage.id.in_(msg_ids))
                )
            ).all()
        )
        if msg_ids
        else {}
    )
    searches = (
        dict(
            (
                await s.execute(
                    select(SearchEvent.id, SearchEvent.query).where(SearchEvent.id.in_(search_ids))
                )
            ).all()
        )
        if search_ids
        else {}
    )
    out = {}
    for e in events:
        t = msgs.get(e.question_id) or searches.get(e.search_event_id)
        if t:
            out[e.id] = t
    return out


async def _nearest_live(s: AsyncSession, space: str, vector: list[float], maxd: float):
    vec = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
    rows = (
        await s.execute(
            text("""
            SELECT c.document_id, min(c.embedding <=> CAST(:v AS vector)) AS dist
            FROM chunks c JOIN documents d ON d.id = c.document_id
            JOIN document_access a ON a.document_id = d.id AND a.role = 'owner'
            WHERE c.live AND c.embedding IS NOT NULL AND a.space = :space
              AND d.status <> 'retired' AND d.doc_type <> 'handover'
              AND c.embedding <=> CAST(:v AS vector) <= :maxd
            GROUP BY c.document_id ORDER BY dist LIMIT 5"""),
            {"v": vec, "space": space, "maxd": maxd},
        )
    ).all()
    return [(doc_id, float(d)) for doc_id, d in rows]


async def _label(gateway, questions: list[str]) -> str:
    fallback = min(questions, key=len)[:80]
    if gateway is None:
        return fallback
    try:
        result = await gateway.chat(
            "router",
            system=with_rules(LABEL_SYSTEM),
            messages=[
                Message(
                    "user",
                    "\n".join(tag("question", q[:300]) for q in questions[:5]) + f"\n{REMINDER}",
                )
            ],
            scope=ContentScope.none(),  # staff questions, no vault content
        )
        label = result.text.strip().strip('"').splitlines()[0][:120] if result.text else ""
        return label or fallback
    except Exception:  # noqa: BLE001
        return fallback


@dataclass
class GroupReport:
    events: int = 0
    new_topics: int = 0
    relabelled: int = 0
    access_gaps: int = 0

    def summary(self) -> dict:
        return self.__dict__.copy()


async def group_gaps(
    sessions: async_sessionmaker,
    embed_query,
    gateway=None,
    *,
    topic_distance: float = TOPIC_DISTANCE,
    access_distance: float = ACCESS_DISTANCE,
    limit: int = 500,
) -> GroupReport:
    report = GroupReport()
    async with sessions() as s, s.begin():
        events = (
            (
                await s.execute(
                    select(GapEvent)
                    .where(GapEvent.topic_id.is_(None))
                    .order_by(GapEvent.created_at)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        texts = await question_texts(s, events)
        searches = {
            e.search_event_id: await s.get(SearchEvent, e.search_event_id)
            for e in events
            if e.search_event_id
        }
        topics = (await s.execute(select(GapTopic))).scalars().all()
        by_space: dict[str, list[GapTopic]] = defaultdict(list)
        for t in topics:
            by_space[t.space].append(t)
        changed: set[uuid.UUID] = set()
        for e in events:
            q = texts.get(e.id)
            if not q:
                continue
            v = _vec(searches[e.search_event_id].vector) if e.search_event_id else None
            if v is None:
                try:
                    v = await embed_query(q)
                except Exception:  # noqa: BLE001 - try again tomorrow
                    continue
            best, best_d = None, 2.0
            for t in by_space[e.space]:
                if t.centroid is None:
                    continue
                d = cosine(v, _vec(t.centroid))
                if d < best_d:
                    best, best_d = t, d
            if best is None or best_d > topic_distance:
                best = GapTopic(space=e.space, label="", status="open", centroid=v, size=0)
                s.add(best)
                await s.flush()
                by_space[e.space].append(best)
                report.new_topics += 1
            c = _vec(best.centroid)
            best.centroid = [
                (x * best.size + y) / (best.size + 1) for x, y in zip(c, v, strict=True)
            ]
            best.size += 1
            best.updated_at = datetime.now(UTC)
            e.topic_id = best.id
            changed.add(best.id)
            report.events += 1
        await s.flush()
        for tid in changed:
            t = await s.get(GapTopic, tid)
            await _describe(s, t, gateway, report, access_distance)
    if report.events:
        log.info("gaps_grouped", extra={"fields": report.summary()})
    return report


async def _describe(
    s: AsyncSession, t: GapTopic, gateway, report: GroupReport, access_distance: float
) -> None:
    evs = (
        (
            await s.execute(
                select(GapEvent).where(GapEvent.topic_id == t.id).order_by(GapEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    qs = list((await question_texts(s, list(evs))).values())
    if qs:
        t.label = await _label(gateway, qs[-5:])
        report.relabelled += 1
    centre = _vec(t.centroid)
    near = await _nearest_live(s, t.space, centre, max(META_DISTANCE, access_distance))
    if near and near[0][1] <= META_DISTANCE:
        doc = await s.get(Document, near[0][0])
        t.programme, t.stage = doc.programme, doc.stage
        folder = str(PurePosixPath(doc.vault_path).parent)
        t.folder = folder if department_of(folder, vault_config()) == t.space else None
    # Access gap: unanswered questions near a document the askers couldn't read.
    t.access_gap_document_id = None
    askers = {e.user_id for e in evs if e.user_id and e.reason == "no_answer"}
    if askers:
        users = (await s.execute(select(User).where(User.id.in_(askers)))).scalars().all()
        principals = [principal_for(u) for u in users]
        for doc_id, d in near:
            if d > access_distance:
                break
            doc = await s.get(Document, doc_id)
            rows = [(a.space, a.sensitivity) for a in doc.access]
            hidden = [
                p
                for p in principals
                if not can_view_document(
                    p,
                    rows,
                    safeguards=doc.safeguards or (),
                    status=doc.status,
                    author_id=doc.author_id,
                )
            ]
            if hidden:
                t.access_gap_document_id = doc.id
                report.access_gaps += 1
                break


# --- personal "gaps from your searches" ---------------------------------------------


@dataclass
class PersonalGap:
    label: str
    count: int
    last_at: datetime
    search_ids: list[uuid.UUID] = field(default_factory=list)
    question_ids: list[uuid.UUID] = field(default_factory=list)
    unanswered_chat: bool = False
    looked_and_left: bool = False  # opened several results, none helped
    vector: list[float] | None = None


async def personal_gaps(
    s: AsyncSession, user_id: uuid.UUID, embed_query, *, days: int = 30
) -> list[PersonalGap]:
    """This user's weak searches and unanswered questions, grouped. Owner-only data."""
    since = datetime.now(UTC) - timedelta(days=days)
    searches = (
        (
            await s.execute(
                select(SearchEvent).where(
                    SearchEvent.user_id == user_id, SearchEvent.created_at >= since
                )
            )
        )
        .scalars()
        .all()
    )
    weak = [
        x
        for x in searches
        if x.results == 0
        or x.best_distance is None
        or x.best_distance > WEAK_DISTANCE
        or (x.used is False and x.opened >= OPENED_UNUSED)  # looked, found nothing useful
    ]
    events = (
        (
            await s.execute(
                select(GapEvent).where(
                    GapEvent.user_id == user_id,
                    GapEvent.created_at >= since,
                    GapEvent.question_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    qtexts = await question_texts(s, list(events))
    items: list[tuple[str, list[float] | None, datetime, str, uuid.UUID]] = [
        (
            x.query,
            _vec(x.vector),
            x.created_at,
            "search_unused" if x.used is False and x.opened >= OPENED_UNUSED else "search",
            x.id,
        )
        for x in weak
    ]
    seen_questions: set[uuid.UUID] = set()
    for e in events:  # one question can be a gap in several spaces: count it once
        if e.id in qtexts and e.question_id not in seen_questions:
            seen_questions.add(e.question_id)
            items.append((qtexts[e.id], None, e.created_at, e.reason, e.question_id))
    groups: list[PersonalGap] = []
    for label, v, at, kind, ref in sorted(items, key=lambda i: i[2]):
        if v is None:
            try:
                v = await embed_query(label)
            except Exception:  # noqa: BLE001
                v = None
        target = None
        if v is not None:
            near = [(cosine(v, g.vector), g) for g in groups if g.vector is not None]
            near = [(d, g) for d, g in near if d <= TOPIC_DISTANCE]
            target = min(near, key=lambda t: t[0])[1] if near else None
        if target is None:
            target = PersonalGap(label=label, count=0, last_at=at, vector=v)
            groups.append(target)
        target.count += 1
        target.label, target.last_at = label, max(target.last_at, at)
        if kind in ("search", "search_unused"):
            target.search_ids.append(ref)
            target.looked_and_left = target.looked_and_left or kind == "search_unused"
        elif ref not in target.question_ids:
            target.question_ids.append(ref)
            target.unanswered_chat = target.unanswered_chat or kind == "no_answer"
    keep = [g for g in groups if g.count >= 2 or g.unanswered_chat or g.looked_and_left]
    return sorted(keep, key=lambda g: (-g.count, -g.last_at.timestamp()))


def people_count(events) -> int:
    return len({e.user_id for e in events if e.user_id})
