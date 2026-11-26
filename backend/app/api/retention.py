"""Knowledge-retention reports and actions (plan §7, Phase 5).

  GET   /spaces/{space}/gaps     the space's leads/reviewers: topics, anonymous examples,
                                 access gaps
  PATCH /gap-topics/{id}         leads or HR: open -> training_planned -> addressed
  GET   /reports/gaps            HR (view_gap_reports): topics with >= 3 people, counts by
                                 role, before/after trend; no questions, no documents
  GET   /me/gaps                 my own "gaps from your searches"
  POST  /me/gaps/request         "Request an SOP": tells the space's leads, anonymously
  GET   /reports/coverage        programme x stage grid (titles for leads, counts for HR)
  GET   /spaces/{space}/stale    review due soon or overdue
  GET   /reports/bus-factor      SOPs with one author; people leaving
  GET   /reports/conflicts       SOPs that may contradict each other
  POST  /conflicts/{id}/dismiss
  POST  /retractions             admins: purge a document or a value (PDPA)

Privacy rules (plan §7, §11): askers are never named; HR sees a topic only
once at least 3 people asked, broken down by role only where a role has at
least 3 of them; personal suggestions are visible only to that user and never
mention documents they can't read.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, clock
from app.api.deps import (
    CurrentUser,
    current_user,
    get_db,
    get_git,
    get_query_embedder,
    require_global,
)
from app.api.reviews import owner_space
from app.db.models import (
    Conflict,
    Document,
    DocumentVersion,
    GapEvent,
    GapTopic,
    SearchEvent,
    User,
)
from app.db.scoped import apply_reader_scope, visible
from app.governance.notify import notify, users_with
from app.retention.gaps import MIN_PEOPLE_FOR_HR, personal_gaps, question_texts
from app.retention.retract import retract_document, retract_term
from app.retrieval.search import search
from app.vault.folders import department_of
from app.vault.git import GitVault
from app.vault.labels import vault_config

router = APIRouter(tags=["retention"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
view_gap_reports = require_global("view_gap_reports")
manage_users = require_global("manage_users")
TOPIC_STATUSES = ("open", "training_planned", "addressed")
SOP_TYPES = ("sop", "guide", "checklist", "faq", "template")


def _lead_of(me: CurrentUser, space: str) -> bool:
    return me.principal.can("approve", space) or me.principal.can("review", space)


# --- gap topics ----------------------------------------------------------------------


class AccessGapOut(BaseModel):
    document_id: str
    title: str


class TopicOut(BaseModel):
    id: str
    space: str
    label: str
    status: str
    programme: str | None
    stage: str | None
    questions: int
    people: int
    last_30_days: int
    reasons: dict[str, int]
    examples: list[str]  # anonymous: no names, no dates
    access_gap: AccessGapOut | None
    addressed_at: datetime | None


async def _topic_events(s: AsyncSession, topic_ids) -> dict[uuid.UUID, list[GapEvent]]:
    rows = (
        (await s.execute(select(GapEvent).where(GapEvent.topic_id.in_(list(topic_ids)))))
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, list[GapEvent]] = defaultdict(list)
    for e in rows:
        out[e.topic_id].append(e)
    return out


@router.get("/spaces/{space}/gaps", response_model=list[TopicOut])
async def space_gaps(
    space: str,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    status_: str | None = Query(
        default=None, alias="status", pattern="^(open|training_planned|addressed)$"
    ),
) -> list[TopicOut]:
    if not _lead_of(me, space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only this space's leads")
    q = select(GapTopic).where(GapTopic.space == space).order_by(GapTopic.updated_at.desc())
    if status_:
        q = q.where(GapTopic.status == status_)
    topics = (await session.execute(q)).scalars().all()
    events = await _topic_events(session, [t.id for t in topics])
    since = datetime.now(UTC) - timedelta(days=30)
    texts = await question_texts(session, [e for evs in events.values() for e in evs])
    gap_docs = {t.access_gap_document_id for t in topics if t.access_gap_document_id}
    await session.commit()
    await apply_reader_scope(session, me.principal)
    readable = {}
    for d in gap_docs:
        doc = await session.get(Document, d)
        if doc is not None and visible(me.principal, doc):
            readable[d] = doc.title
    await session.commit()
    out = []
    for t in topics:
        evs = events.get(t.id, [])
        examples = list(dict.fromkeys(texts[e.id] for e in reversed(evs) if e.id in texts))[:3]
        out.append(
            TopicOut(
                id=str(t.id),
                space=t.space,
                label=t.label,
                status=t.status,
                programme=t.programme,
                stage=t.stage,
                questions=len(evs),
                people=len({e.user_id for e in evs if e.user_id}),
                last_30_days=sum(1 for e in evs if e.created_at >= since),
                reasons=dict(Counter(e.reason for e in evs)),
                examples=[x[:300] for x in examples],
                access_gap=(
                    AccessGapOut(
                        document_id=str(t.access_gap_document_id),
                        title=readable[t.access_gap_document_id],
                    )
                    if t.access_gap_document_id in readable
                    else None
                ),
                addressed_at=t.addressed_at,
            )
        )
    return out


class TopicStatusIn(BaseModel):
    status: str = Field(pattern="^(open|training_planned|addressed)$")


@router.patch("/gap-topics/{topic_id}", status_code=204)
async def set_topic_status(
    topic_id: uuid.UUID,
    body: TopicStatusIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    t = await session.get(GapTopic, topic_id)
    if t is None:
        raise NOT_FOUND
    if not (me.principal.can("approve", t.space) or me.principal.can("view_gap_reports")):
        raise NOT_FOUND
    t.status, t.status_changed_by = body.status, me.user.id
    t.addressed_at = datetime.now(UTC) if body.status == "addressed" else None
    await audit.record(
        session,
        "gap_topic_status",
        actor_id=me.user.id,
        target_type="gap_topic",
        target_id=t.id,
        details={"status": body.status},
    )
    await session.commit()


class HrTopicOut(BaseModel):
    id: str
    space: str
    label: str
    status: str
    programme: str | None
    stage: str | None
    questions: int
    people: int
    by_role: dict[str, int]  # people per role; roles with < 3 people are grouped as "other"
    before_addressed_30d: int | None
    after_addressed_30d: int | None


@router.get("/reports/gaps", response_model=list[HrTopicOut])
async def hr_gaps(
    me: CurrentUser = Depends(view_gap_reports),
    session: AsyncSession = Depends(get_db),
) -> list[HrTopicOut]:
    topics = (await session.execute(select(GapTopic))).scalars().all()
    events = await _topic_events(session, [t.id for t in topics])
    users = {
        u.id: u
        for u in (
            await session.execute(
                select(User).where(
                    User.id.in_({e.user_id for evs in events.values() for e in evs if e.user_id})
                )
            )
        ).scalars()
    }
    hidden = {"platform-admin"}
    out = []
    for t in topics:
        evs = events.get(t.id, [])
        people = {e.user_id for e in evs if e.user_id}
        if len(people) < MIN_PEOPLE_FOR_HR:
            continue  # nobody can be singled out
        roles: Counter = Counter()
        for uid in people:
            names = (
                sorted(r.name for r in users[uid].roles if r.name not in hidden)
                if uid in users
                else []
            )
            # the most specific role (not the everyone role) stands for the person
            specific = [n for n in names if n != "employee"] or ["employee"]
            roles[specific[0]] += 1
        by_role: dict[str, int] = {}
        for role, n in roles.items():
            key = role if n >= MIN_PEOPLE_FOR_HR else "other"
            by_role[key] = by_role.get(key, 0) + n
        before = after = None
        if t.addressed_at:
            window = timedelta(days=30)
            before = sum(1 for e in evs if t.addressed_at - window <= e.created_at < t.addressed_at)
            after = sum(1 for e in evs if t.addressed_at <= e.created_at < t.addressed_at + window)
        out.append(
            HrTopicOut(
                id=str(t.id),
                space=t.space,
                label=t.label,
                status=t.status,
                programme=t.programme,
                stage=t.stage,
                questions=len(evs),
                people=len(people),
                by_role=by_role,
                before_addressed_30d=before,
                after_addressed_30d=after,
            )
        )
    await audit.record(
        session, "gap_report_viewed", actor_id=me.user.id, details={"topics": len(out)}
    )
    await session.commit()
    return sorted(out, key=lambda x: -x.people)


# --- personal gaps -----------------------------------------------------------------------


class RelatedOut(BaseModel):
    document_id: str
    title: str
    space: str | None


class PersonalGapOut(BaseModel):
    key: str  # pass back to /me/gaps/request
    label: str
    count: int
    last_at: datetime
    message: str
    related: list[RelatedOut]  # SOPs you can read that come closest
    experts: list[str]  # authors of those SOPs
    space: str | None  # where a new SOP would go
    programme: str | None
    stage: str | None


@router.get("/me/gaps", response_model=list[PersonalGapOut])
async def my_gaps(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    embed_query=Depends(get_query_embedder),
) -> list[PersonalGapOut]:
    groups = await personal_gaps(session, me.user.id, embed_query)
    await session.commit()
    out = []
    for g in groups[:10]:
        await apply_reader_scope(session, me.principal)
        hits = await search(session, me.principal, g.label, query_vector=g.vector, limit=6)
        await session.commit()
        related, seen = [], set()
        for h in hits:
            if h.document_id not in seen and h.kind == "note":
                seen.add(h.document_id)
                related.append(h)
        related = related[:3]
        experts = []
        if related:
            names = (
                await session.execute(
                    select(DocumentVersion.author_name)
                    .where(
                        DocumentVersion.document_id.in_([h.document_id for h in related]),
                        DocumentVersion.author_source.in_(("app", "git")),
                    )
                    .distinct()
                )
            ).scalars()
            experts = sorted(n for n in names if n and n != me.user.display_name)[:3]
        readable = sorted(me.principal.scopes())
        space = (
            related[0].space
            if related
            else (me.user.home_space if me.user.home_space in readable else (readable or [None])[0])
        )
        out.append(
            PersonalGapOut(
                key=",".join(str(i) for i in [*g.search_ids, *g.question_ids][:20]),
                label=g.label[:200],
                count=g.count,
                last_at=g.last_at,
                message=(
                    f"You've looked for '{g.label[:120]}' {g.count} time"
                    f"{'s' if g.count != 1 else ''} this month; no SOP you can access covers it."
                ),
                related=[
                    RelatedOut(document_id=str(h.document_id), title=h.title, space=h.space)
                    for h in related
                ],
                experts=experts,
                space=space,
                programme=related[0].programme if related else None,
                stage=related[0].stage if related else None,
            )
        )
    return out


class RequestIn(BaseModel):
    key: str = Field(min_length=1, max_length=2000)
    space: str = Field(max_length=64)


@router.post("/me/gaps/request", status_code=202)
async def request_sop(
    body: RequestIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Ask the space's leads for an SOP. They are told a request came in (no
    name); the question shows up, anonymously, in that space's gap topics."""
    if body.space not in me.principal.scopes():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't ask in that space")
    try:
        ids = [uuid.UUID(x) for x in body.key.split(",") if x]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad key") from None
    search_id = await session.scalar(
        select(SearchEvent.id).where(SearchEvent.id.in_(ids), SearchEvent.user_id == me.user.id)
    )
    question_id = None
    if search_id is None:
        question_id = await session.scalar(
            select(GapEvent.question_id).where(
                GapEvent.question_id.in_(ids), GapEvent.user_id == me.user.id
            )
        )
    if search_id is None and question_id is None:
        raise NOT_FOUND
    e = GapEvent(
        space=body.space,
        reason="requested",
        user_id=me.user.id,
        search_event_id=search_id,
        question_id=question_id,
    )
    session.add(e)
    await session.flush()
    await notify(
        session,
        await users_with(session, "approve", body.space),
        "sop_requested",
        ref_id=str(e.id),
        skip=me.user.id,
    )
    await audit.record(
        session,
        "sop_requested",
        actor_id=me.user.id,
        target_type="gap_event",
        target_id=e.id,
        details={"space": body.space},
    )
    await session.commit()
    return {"requested": True}


# --- coverage, staleness, bus factor ------------------------------------------------------


class CellOut(BaseModel):
    programme: str
    stage: str
    published: int
    stale: int
    titles: list[str] | None  # leads/CEO only (documents they can read)


@router.get("/reports/coverage", response_model=list[CellOut])
async def coverage(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[CellOut]:
    leads = [s for s, acts in me.principal.space_actions().items() if "approve" in acts]
    hr = me.principal.can("view_gap_reports")
    if not leads and not hr:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
    config = vault_config()
    today = clock.today()
    docs = (
        (
            await session.execute(
                select(Document).where(
                    Document.kind == "note",
                    Document.doc_type.in_(SOP_TYPES),
                    Document.programme.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    ids = [d.id for d in docs]
    await session.commit()
    await apply_reader_scope(session, me.principal)
    readable = {
        d.id: d.title
        for i in ids
        if (d := await session.get(Document, i)) is not None and visible(me.principal, d)
    }
    await session.commit()

    # A programme named only in restricted SOPs is not revealed (red-team,
    # 2026-11-22): names come from SOPs this viewer can read, or that are not
    # restricted (the company's ordinary programmes).
    def ordinary(d: Document) -> bool:
        owner = next((a for a in d.access if a.role == "owner"), None)
        return owner is not None and owner.sensitivity != "restricted" and not d.safeguards

    programmes = sorted({d.programme for d in docs if d.id in readable or ordinary(d)})
    out = []
    for prog in programmes:
        for stage in config.stages:
            cell = [d for d in docs if d.programme == prog and d.stage == stage]
            live = [d for d in cell if d.approved_hash is not None and d.status == "published"]
            stale = [d for d in live if d.review_due is not None and d.review_due < today]
            out.append(
                CellOut(
                    programme=prog,
                    stage=stage,
                    published=len(live),
                    stale=len(stale),
                    titles=sorted(readable[d.id] for d in live if d.id in readable)
                    if leads
                    else None,
                )
            )
    return out


class FolderCoverageOut(BaseModel):
    folder: str
    documents: int
    approved: int
    stale: int  # approved, review date passed
    open_gaps: int  # gap topics nearest this folder, not addressed
    gap_questions: int


@router.get("/spaces/{space}/folder-coverage", response_model=list[FolderCoverageOut])
async def folder_coverage(
    space: str,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[FolderCoverageOut]:
    """A department's Library folders for its leads: how much is written and
    approved, how much is overdue for review, and how many unanswered question
    topics sit closest to each folder. Counts only, over documents the lead can
    read (RLS and the policy engine); gap topics only name folders shown here."""
    if not _lead_of(me, space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only this space's leads")
    config = vault_config()
    today = clock.today()
    topics = (
        (await session.execute(select(GapTopic).where(GapTopic.space == space))).scalars().all()
    )
    events = await _topic_events(session, [t.id for t in topics])
    await session.commit()
    await apply_reader_scope(session, me.principal)
    docs = [
        d
        for d in (await session.execute(select(Document))).scalars().all()
        if visible(me.principal, d)
    ]
    rows: dict[str, FolderCoverageOut] = {}
    for d in docs:
        owner = next((a.space for a in d.access if a.role == "owner"), None)
        folder = str(PurePosixPath(d.vault_path).parent)
        if owner != space or department_of(folder, config) != space or d.doc_type == "handover":
            continue
        row = rows.setdefault(
            folder,
            FolderCoverageOut(
                folder=folder, documents=0, approved=0, stale=0, open_gaps=0, gap_questions=0
            ),
        )
        row.documents += 1
        if d.approved_hash is not None:
            row.approved += 1
            if d.review_due is not None and d.review_due < today:
                row.stale += 1
    await session.commit()
    for t in topics:
        if t.folder in rows and t.status != "addressed":
            rows[t.folder].open_gaps += 1
            rows[t.folder].gap_questions += len(events.get(t.id, []))
    return sorted(rows.values(), key=lambda r: r.folder.lower())


class StaleOut(BaseModel):
    document_id: str
    title: str
    review_due: date
    overdue: bool
    approved_on: date | None


@router.get("/spaces/{space}/stale", response_model=list[StaleOut])
async def stale(
    space: str,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    within_days: int = Query(default=30, ge=0, le=365),
) -> list[StaleOut]:
    if not _lead_of(me, space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only this space's leads")
    horizon = clock.today() + timedelta(days=within_days)
    docs = (
        (
            await session.execute(
                select(Document)
                .where(
                    Document.review_due.is_not(None),
                    Document.review_due <= horizon,
                    Document.status == "published",
                )
                .order_by(Document.review_due)
            )
        )
        .scalars()
        .all()
    )
    docs = [d for d in docs if owner_space(d) == space and visible(me.principal, d)]
    from app.db.models import SopApproval

    approved = dict(
        (
            await session.execute(
                select(SopApproval.document_id, func.max(SopApproval.approved_at))
                .where(SopApproval.document_id.in_([d.id for d in docs]))
                .group_by(SopApproval.document_id)
            )
        ).all()
    )
    today = clock.today()
    out = []
    for d in docs:
        last = approved.get(d.id)
        out.append(
            StaleOut(
                document_id=str(d.id),
                title=d.title,
                review_due=d.review_due,
                overdue=d.review_due < today,
                approved_on=clock.local_date(last) if last else None,
            )
        )
    return out


class BusItem(BaseModel):
    document_id: str
    title: str
    space: str | None
    only_author: str
    author_leaving_on: date | None


class LeavingOut(BaseModel):
    name: str
    leaving_on: date
    sole_author_of: int
    owner_of: int


class BusFactorOut(BaseModel):
    single_author: list[BusItem]
    leaving: list[LeavingOut]


@router.get("/reports/bus-factor", response_model=BusFactorOut)
async def bus_factor(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> BusFactorOut:
    spaces = [s for s, acts in me.principal.space_actions().items() if "approve" in acts]
    if not spaces:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only space leads")
    docs = (
        (
            await session.execute(
                select(Document).where(
                    Document.kind == "note",
                    Document.status == "published",
                    Document.doc_type != "handover",
                )
            )
        )
        .scalars()
        .all()
    )
    docs = [d for d in docs if owner_space(d) in spaces and visible(me.principal, d)]
    authors: dict[uuid.UUID, set[str]] = defaultdict(set)
    author_ids: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for v in (
        await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id.in_([d.id for d in docs]),
                DocumentVersion.author_source.in_(("app", "git")),
            )
        )
    ).scalars():
        authors[v.document_id].add(v.author_name)
        if v.authored_by:
            author_ids[v.document_id].add(v.authored_by)
    users = {u.id: u for u in (await session.execute(select(User))).scalars()}
    by_name = {u.display_name: u for u in users.values()}
    single = []
    for d in docs:
        names = authors.get(d.id, set())
        if len(names) == 1:
            (name,) = names
            uid = next(iter(author_ids.get(d.id, set())), None)
            person = users.get(uid) or by_name.get(name)
            single.append(
                BusItem(
                    document_id=str(d.id),
                    title=d.title,
                    space=owner_space(d),
                    only_author=name,
                    author_leaving_on=person.leaving_on if person else None,
                )
            )
    leaving = []
    for u in users.values():
        if u.leaving_on is None:
            continue
        sole = sum(1 for i in single if i.only_author == u.display_name)
        owner = sum(1 for d in docs if d.owner and u.display_name.lower() in d.owner.lower())
        if sole or owner:
            leaving.append(
                LeavingOut(
                    name=u.display_name,
                    leaving_on=u.leaving_on,
                    sole_author_of=sole,
                    owner_of=owner,
                )
            )
    return BusFactorOut(
        single_author=sorted(single, key=lambda i: (i.author_leaving_on is None, i.title)),
        leaving=sorted(leaving, key=lambda x: x.leaving_on),
    )


# --- conflicts -----------------------------------------------------------------------------


class ConflictOut(BaseModel):
    id: str
    document_a: str
    title_a: str
    document_b: str
    title_b: str
    explanation: str
    created_at: datetime


@router.get("/reports/conflicts", response_model=list[ConflictOut])
async def conflicts(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ConflictOut]:
    rows = (
        (await session.execute(select(Conflict).where(Conflict.status == "open"))).scalars().all()
    )
    await session.commit()
    await apply_reader_scope(session, me.principal)
    out = []
    for c in rows:
        a, b = await session.get(Document, c.document_a), await session.get(Document, c.document_b)
        if a is None or b is None or not (visible(me.principal, a) and visible(me.principal, b)):
            continue
        out.append((c, a, b))
    await session.commit()
    result = []
    for c, a, b in out:
        await session.refresh(a)
        await session.refresh(b)
        if not any(_lead_of(me, sp) for sp in (owner_space(a), owner_space(b)) if sp):
            continue
        # Stale once either SOP has a newer approved version (re-checked nightly).
        if (a.approved_hash or "") != c.hash_a or (b.approved_hash or "") != c.hash_b:
            continue
        result.append(
            ConflictOut(
                id=str(c.id),
                document_a=str(a.id),
                title_a=a.title,
                document_b=str(b.id),
                title_b=b.title,
                explanation=c.explanation,
                created_at=c.created_at,
            )
        )
    return result


@router.post("/conflicts/{conflict_id}/dismiss", status_code=204)
async def dismiss_conflict(
    conflict_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    c = await session.get(Conflict, conflict_id)
    if c is None:
        raise NOT_FOUND
    a, b = await session.get(Document, c.document_a), await session.get(Document, c.document_b)
    if not any(me.principal.can("approve", sp) for sp in (owner_space(a), owner_space(b)) if sp):
        raise NOT_FOUND
    c.status = "dismissed"
    await audit.record(
        session, "conflict_dismissed", actor_id=me.user.id, target_type="conflict", target_id=c.id
    )
    await session.commit()


# --- retract -------------------------------------------------------------------------------


class RetractIn(BaseModel):
    document_id: uuid.UUID | None = None
    value: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def one_of(self):
        if (self.document_id is None) == (self.value is None):
            raise ValueError("give either document_id or value")
        return self


@router.post("/retractions")
async def retract(
    body: RetractIn,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> dict:
    """Purge from the index and history; returns counts only (never the value)."""
    if body.document_id is not None:
        if await session.get(Document, body.document_id) is None:
            raise NOT_FOUND
        result = await retract_document(session, body.document_id, me.user.id)
        kind = "document"
    else:
        try:
            result = await retract_term(session, body.value, me.user.id, git)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        kind = "value"
    summary = result.summary()
    await audit.record(
        session,
        "retraction_applied",
        actor_id=me.user.id,
        target_type="document" if kind == "document" else None,
        target_id=body.document_id,
        details={
            "kind": kind,
            "documents": result.documents,
            "answers_removed": result.answers_removed,
            "remaining": sum(result.remaining.values()),
            "vault_files": result.vault_files_with_term,
        },
    )
    await session.commit()
    return summary
