"""SOP review in the platform (plan §6 "Workflow", Phase 4).

  POST /notes/{id}/submit           author/contributor submits the latest version
  GET  /notes/{id}/diff             changes against the last approved version
  POST /notes/{id}/approve          a lead approves the latest version directly
  POST /notes/{id}/retire           a lead retires a note (no longer cited)
  GET  /reviews                     open requests I can act on, and my own
  GET  /reviews/{id}                one request, with the change summary
  POST /reviews/{id}/approve        approve exactly the submitted version
  POST /reviews/{id}/request-changes
  POST /reviews/{id}/withdraw
  GET  /reports/governance          unattributed edits, unreviewed changes, ...
  GET  /notifications, POST /notifications/{id}/read

An approval covers one exact version: if the note changed after it was
submitted, approving the request is refused (409). Approving your own change
is allowed only for someone who could approve it anyway (the space's lead),
and is recorded as *self-approved*. Unapproved changes, diffs and summaries
are shown only to the note's editors; everyone else gets 404.
"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.api.deps import (
    CurrentUser,
    current_user,
    get_db,
    get_embedder,
    get_git,
    get_session_factory,
)
from app.db.models import (
    AuditEvent,
    Document,
    DocumentAccess,
    DocumentVersion,
    Notification,
    ReadingAssignment,
    ReviewRequest,
    Role,
    SopApproval,
    Space,
    User,
)
from app.db.scoped import apply_reader_scope, has_pending_change, sees_latest, visible
from app.governance import webhooks
from app.governance.approvals import approve as approve_version
from app.governance.approvals import write_back
from app.governance.history import owner_space, version_readable
from app.governance.notify import notify, users_with
from app.governance.versions import with_frontmatter
from app.vault.git import GitError, GitVault
from app.vault.indexer import Indexer
from app.vault.labels import vault_config

router = APIRouter(tags=["workflow"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
_SHA = re.compile(r"^[0-9a-f]{7,64}$")
REPORT_DAYS = 180


class ReviewOut(BaseModel):
    id: str
    document_id: str
    title: str
    vault_path: str
    space: str | None
    status: str
    requested_by: str
    requested_at: datetime
    self_review: bool  # the person asking to approve is also an author of the change
    stale: bool  # the note changed after it was submitted
    git_commit: str | None  # the exact version submitted
    base_commit: str | None  # the approved version it is compared against (None: first)
    summary: str | None
    summary_pending: bool
    comment: str
    decided_by: str | None
    decided_at: datetime | None
    # instruction-like text found in the note (pattern ids only): worth a look
    flags: list[str] = []


class DecisionIn(BaseModel):
    comment: str = Field(default="", max_length=4000)


class ApproveIn(DecisionIn):
    # People who must read this SOP read it again (frontend spec §9.2).
    material_change: bool = False


class DirectApproveIn(BaseModel):
    version: str = Field(min_length=64, max_length=64)  # governed hash shown in the diff
    comment: str = Field(default="", max_length=4000)
    material_change: bool = False


class DiffOut(BaseModel):
    document_id: str
    from_commit: str | None
    to_commit: str | None  # None = the latest version in the vault
    version: str | None  # governed hash of the "to" side (send it to approve)
    added: int
    removed: int
    diff: str


class NotificationOut(BaseModel):
    id: str
    kind: str
    document_id: str | None
    title: str | None  # only if you can still see the document
    ref_id: str | None
    created_at: datetime
    read: bool


# --- helpers ----------------------------------------------------------------------


async def _editor_doc(session: AsyncSession, me: CurrentUser, doc_id: uuid.UUID) -> Document:
    """A document this user can see *including* unapproved changes, else 404."""
    await session.commit()
    await apply_reader_scope(session, me.principal)
    doc = await session.get(Document, doc_id)
    ok = doc is not None and doc.kind == "note" and visible(me.principal, doc)
    ok = ok and sees_latest(me.principal, doc)
    await session.commit()
    if not ok:
        raise NOT_FOUND
    await session.refresh(doc)  # all access rows (RLS showed only the readable ones)
    return doc


def _can_review(me: CurrentUser, doc: Document) -> bool:
    space = owner_space(doc)
    return space is not None and (
        me.principal.can("review", space) or me.principal.can("approve", space)
    )


async def _spaces(session: AsyncSession) -> set[str]:
    return set((await session.execute(select(Space.name))).scalars())


def _version_readable(me: CurrentUser, doc: Document, git: GitVault, commit: str, spaces) -> bool:
    return version_readable(me.principal, doc, git, commit, spaces)


async def _change_authors(session: AsyncSession, doc: Document) -> set[uuid.UUID]:
    """People who wrote versions since the last approval (platform commits excluded)."""
    last = await session.scalar(
        select(func.max(SopApproval.approved_at)).where(SopApproval.document_id == doc.id)
    )
    q = select(DocumentVersion.authored_by).where(
        DocumentVersion.document_id == doc.id,
        DocumentVersion.authored_by.is_not(None),
        DocumentVersion.author_source != "platform",
    )
    if last is not None:
        q = q.where(DocumentVersion.indexed_at > last)
    return set((await session.execute(q)).scalars())


async def _names(session: AsyncSession, ids) -> dict[uuid.UUID, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return dict(rows.all())


def _read_version(git: GitVault, rel: str, commit: str | None) -> str:
    if commit is None:
        return ""
    try:
        return git.show(rel, commit).decode("utf-8", errors="replace")
    except GitError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found") from None


async def _review_out(
    session: AsyncSession, r: ReviewRequest, doc: Document, me: CurrentUser
) -> ReviewOut:
    authors = await _change_authors(session, doc) | {r.requested_by}
    names = await _names(session, [r.requested_by, r.decided_by])
    return ReviewOut(
        id=str(r.id),
        document_id=str(doc.id),
        title=doc.title,
        vault_path=doc.vault_path,
        space=owner_space(doc),
        status=r.status,
        requested_by=names.get(r.requested_by, "unknown"),
        requested_at=r.created_at,
        self_review=me.user.id in authors,
        stale=r.status == "open" and r.content_hash != doc.governed_hash,
        git_commit=r.git_commit,
        base_commit=r.base_commit,
        summary=r.summary,
        summary_pending=r.status == "open" and r.summary is None and r.summary_failed < 3,
        comment=r.comment,
        decided_by=names.get(r.decided_by) if r.decided_by else None,
        decided_at=r.decided_at,
        flags=doc.injection_flags or [],
    )


async def _finish_approval(
    *,
    me: CurrentUser,
    doc_id: uuid.UUID,
    version: str,
    request_id: uuid.UUID | None,
    sessions: async_sessionmaker,
    git: GitVault,
    embed,
    material_change: bool = False,
) -> str:
    """Approve the document's current version if it is still `version`.

    With `material_change`, earlier read acknowledgements stop counting and the
    people it's assigned to are asked to read it again."""
    config = vault_config()
    async with sessions() as s, s.begin():
        doc = await s.get(Document, doc_id, with_for_update=True)
        if doc is None:
            raise NOT_FOUND
        if doc.governed_hash != version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "the note changed after it was submitted; review the latest version",
            )
        if doc.approved_hash == doc.governed_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "this version is already approved")
        space = owner_space(doc)
        if space is None or not me.principal.can("approve", space):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only the space's lead can approve")
        authors = await _change_authors(s, doc)
        request = await s.get(ReviewRequest, request_id) if request_id else None
        if request is not None:
            authors.add(request.requested_by)
        method = "self" if me.user.id in authors else "review"
        doc_had_approval = doc.approved_hash is not None
        approval = await approve_version(
            s, doc, approver_id=me.user.id, method=method, config=config, request_id=request_id
        )
        # A first approval has nothing to re-read.
        approval.material_change = material_change and doc_had_approval
        if approval.material_change:
            from app.governance.reading import assignees

            assigned = (
                (
                    await s.execute(
                        select(ReadingAssignment).where(ReadingAssignment.document_id == doc.id)
                    )
                )
                .scalars()
                .all()
            )
            if assigned:
                await notify(
                    s,
                    [u.id for u in await assignees(s, list(assigned))],
                    "reading_reread",
                    document_id=doc.id,
                    skip=me.user.id,
                )
        if request is not None:
            request.status, request.decided_by = "approved", me.user.id
            request.decided_at = datetime.now(UTC)
        # Any other open request for this note is now out of date.
        for other in (
            await s.execute(
                select(ReviewRequest).where(
                    ReviewRequest.document_id == doc.id,
                    ReviewRequest.status == "open",
                    ReviewRequest.id != request_id,
                )
            )
        ).scalars():
            other.status = "superseded"
        await notify(
            s,
            [*authors, request.requested_by if request else None],
            "sop_approved",
            document_id=doc.id,
            ref_id=str(approval.id),
            skip=me.user.id,
        )
        await webhooks.emit(
            s, "sop_published", document_id=doc.id, space=space, commit=doc.approved_commit
        )
        await audit.record(
            s,
            "sop_approved",
            actor_id=me.user.id,
            target_type="document",
            target_id=doc.id,
            details={
                "commit": doc.approved_commit,
                "method": method,
                "review": str(request_id) if request_id else None,
                "material_change": approval.material_change,
            },
        )
        rel, due, title_status = doc.vault_path, doc.review_due, doc.status
    if config.write_back:
        doc_view = Document(id=doc_id, vault_path=rel, kind="note", status=title_status)
        if write_back(
            git,
            doc_view,
            reviewer=me.user.display_name,
            approved_on=datetime.now(UTC).date(),
            review_due=due,
        ):
            await Indexer(git, sessions, embed).index_paths([rel])
    return method


# --- submit, diff, direct approve, retire ----------------------------------------------


@router.post("/notes/{note_id}/submit", response_model=ReviewOut, status_code=201)
async def submit(
    note_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ReviewOut:
    doc = await _editor_doc(session, me, note_id)
    space = owner_space(doc)
    if space is None or not (me.principal.can("contribute", space) or doc.author_id == me.user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't submit this note")
    if doc.governed_hash is None or doc.approved_hash == doc.governed_hash:
        raise HTTPException(status.HTTP_409_CONFLICT, "nothing new to review")
    for r in (
        await session.execute(
            select(ReviewRequest).where(
                ReviewRequest.document_id == doc.id, ReviewRequest.status == "open"
            )
        )
    ).scalars():
        if r.content_hash == doc.governed_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "this version is already in review")
        r.status = "superseded"
    req = ReviewRequest(
        document_id=doc.id,
        git_commit=doc.current_commit,
        content_hash=doc.governed_hash,
        base_commit=doc.approved_commit,
        requested_by=me.user.id,
        status="open",
    )
    session.add(req)
    await session.flush()
    reviewers = await users_with(session, "approve", space) + await users_with(
        session, "review", space
    )
    await notify(
        session,
        reviewers,
        "review_requested",
        document_id=doc.id,
        ref_id=str(req.id),
        skip=me.user.id,
    )
    await webhooks.emit(
        session,
        "review_requested",
        document_id=doc.id,
        space=space,
        review_id=req.id,
        commit=doc.current_commit,
    )
    await audit.record(
        session,
        "review_requested",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={"review": str(req.id), "commit": doc.current_commit},
    )
    await session.commit()
    return await _review_out(session, req, doc, me)


@router.get("/notes/{note_id}/diff", response_model=DiffOut)
async def diff(
    note_id: uuid.UUID,
    from_: str | None = Query(default=None, alias="from", max_length=64),
    to: str | None = Query(default=None, max_length=64),
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> DiffOut:
    """Unified diff between two versions (default: last approved -> latest)."""
    doc = await _editor_doc(session, me, note_id)
    known = set(
        (
            await session.execute(
                select(DocumentVersion.git_commit).where(DocumentVersion.document_id == doc.id)
            )
        ).scalars()
    )
    for c in (from_, to):
        if c is not None and (not _SHA.match(c) or not any(k.startswith(c) for k in known)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
        if c is not None and not _version_readable(me, doc, git, c, await _spaces(session)):
            # An older version may have been under narrower labels (red-team, 2026-11-22).
            raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    start = from_ or doc.approved_commit
    old = _read_version(git, doc.vault_path, start)
    if to is None:
        new = git.safe_path(doc.vault_path).read_text(encoding="utf-8", errors="replace")
    else:
        new = _read_version(git, doc.vault_path, to)
    lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"approved {start[:10]}" if start else "nothing approved yet",
            tofile=to[:10] if to else "latest",
            lineterm="",
        )
    )
    return DiffOut(
        document_id=str(doc.id),
        from_commit=start,
        to_commit=to,
        version=doc.governed_hash if to is None else None,
        added=sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++")),
        removed=sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---")),
        diff="\n".join(lines),
    )


@router.post("/notes/{note_id}/approve", status_code=200)
async def approve_direct(
    note_id: uuid.UUID,
    body: DirectApproveIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    sessions: async_sessionmaker = Depends(get_session_factory),
    git: GitVault = Depends(get_git),
    embed=Depends(get_embedder),
) -> dict:
    """A lead approves the latest version without a request (e.g. an Obsidian edit).
    `version` is the governed hash shown by the diff, so what was read is what's approved."""
    await _editor_doc(session, me, note_id)
    method = await _finish_approval(
        me=me,
        doc_id=note_id,
        version=body.version,
        request_id=None,
        sessions=sessions,
        git=git,
        embed=embed,
        material_change=body.material_change,
    )
    return {"approval": method}


@router.post("/notes/{note_id}/retire", status_code=204)
async def retire(
    note_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    sessions: async_sessionmaker = Depends(get_session_factory),
    git: GitVault = Depends(get_git),
    embed=Depends(get_embedder),
) -> None:
    """Retire a note: it stays in the Library (marked retired) but is never cited."""
    doc = await _editor_doc(session, me, note_id)
    space = owner_space(doc)
    if space is None or not me.principal.can("approve", space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the space's lead can retire a note")
    full = git.safe_path(doc.vault_path)
    with git.lock():
        text = full.read_text(encoding="utf-8")
        new = with_frontmatter(text, {"status": "retired"})
        if new is None:
            new = f"---\nstatus: retired\n---\n\n{text}"
        if new != text:
            full.write_text(new, encoding="utf-8")
            git.commit(
                [doc.vault_path],
                f"Retire {doc.vault_path}",
                author_name=me.user.display_name,
                author_email=me.user.email,
                user_id=me.user.id,
            )
    await Indexer(git, sessions, embed).index_paths([doc.vault_path])
    async with sessions() as s:
        await audit.record(
            s, "sop_retired", actor_id=me.user.id, target_type="document", target_id=doc.id
        )
        await s.commit()


# --- review requests ---------------------------------------------------------------------


async def _request(
    session: AsyncSession, me: CurrentUser, review_id: uuid.UUID
) -> tuple[ReviewRequest, Document]:
    r = await session.get(ReviewRequest, review_id)
    if r is None:
        raise NOT_FOUND
    doc = await _editor_doc(session, me, r.document_id)
    if r.requested_by != me.user.id and not _can_review(me, doc):
        raise NOT_FOUND
    r = await session.get(ReviewRequest, review_id)  # reload after the scope switch
    return r, doc


@router.get("/reviews", response_model=list[ReviewOut])
async def list_reviews(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    state: str = Query(default="open", pattern="^(open|all)$"),
) -> list[ReviewOut]:
    q = select(ReviewRequest).order_by(ReviewRequest.created_at.desc()).limit(200)
    if state == "open":
        q = q.where(ReviewRequest.status == "open")
    rows = (await session.execute(q)).scalars().all()
    await session.commit()
    await apply_reader_scope(session, me.principal)
    out = []
    for r in rows:
        doc = await session.get(Document, r.document_id)
        if doc is None or not visible(me.principal, doc) or not sees_latest(me.principal, doc):
            continue
        out.append((r, doc))
    await session.commit()
    result = []
    for r, doc in out:
        await session.refresh(doc)
        if r.requested_by == me.user.id or _can_review(me, doc):
            result.append(await _review_out(session, r, doc, me))
    return result


@router.get("/reviews/{review_id}", response_model=ReviewOut)
async def get_review(
    review_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ReviewOut:
    r, doc = await _request(session, me, review_id)
    return await _review_out(session, r, doc, me)


@router.post("/reviews/{review_id}/approve")
async def approve_request(
    review_id: uuid.UUID,
    body: ApproveIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    sessions: async_sessionmaker = Depends(get_session_factory),
    git: GitVault = Depends(get_git),
    embed=Depends(get_embedder),
) -> dict:
    r, _ = await _request(session, me, review_id)
    if r.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"this review is {r.status}")
    version, doc_id = r.content_hash, r.document_id
    if body.comment.strip():
        r.comment = body.comment.strip()
        await session.commit()
    await session.commit()
    method = await _finish_approval(
        me=me,
        doc_id=doc_id,
        version=version,
        request_id=review_id,
        sessions=sessions,
        git=git,
        embed=embed,
        material_change=body.material_change,
    )
    return {"approval": method}


@router.post("/reviews/{review_id}/request-changes", status_code=204)
async def request_changes(
    review_id: uuid.UUID,
    body: DecisionIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    r, doc = await _request(session, me, review_id)
    if not _can_review(me, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only reviewers of this space can do that")
    if r.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"this review is {r.status}")
    r.status, r.decided_by, r.decided_at = "changes_requested", me.user.id, datetime.now(UTC)
    r.comment = body.comment.strip()
    await notify(
        session,
        [r.requested_by],
        "changes_requested",
        document_id=doc.id,
        ref_id=str(r.id),
        skip=me.user.id,
    )
    await webhooks.emit(
        session, "changes_requested", document_id=doc.id, space=owner_space(doc), review_id=r.id
    )
    await audit.record(
        session,
        "review_changes_requested",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={"review": str(r.id)},
    )
    await session.commit()


@router.post("/reviews/{review_id}/withdraw", status_code=204)
async def withdraw(
    review_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    r, doc = await _request(session, me, review_id)
    if r.requested_by != me.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the person who submitted it")
    if r.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"this review is {r.status}")
    r.status = "withdrawn"
    await session.commit()


# --- governance report ------------------------------------------------------------------


class GovernanceItem(BaseModel):
    document_id: str
    title: str | None
    space: str | None
    detail: dict = {}


class GovernanceOut(BaseModel):
    spaces: list[str]
    unattributed_edits: list[GovernanceItem]
    changes_awaiting_review: list[GovernanceItem]
    never_approved: list[GovernanceItem]
    published_outside_platform: list[GovernanceItem]
    self_approved: list[GovernanceItem]
    review_overdue: list[GovernanceItem]
    # notes with instruction-like text ("note to the assistant", "ignore the
    # rules"): shown here only, never pushed as an alert
    possible_instructions: list[GovernanceItem] = []
    # people given more than public access to these spaces, and who did it (quiet)
    access_changes: list[dict] = []


@router.get("/reports/governance", response_model=GovernanceOut)
async def governance_report(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    space: str | None = Query(default=None, max_length=64),
) -> GovernanceOut:
    """For a space's leads (approve) and auditors (view_audit: every space)."""
    all_spaces = sorted(
        {a.space for a in (await session.execute(select(DocumentAccess))).scalars()}
    )
    if me.principal.can("view_audit"):
        spaces = all_spaces
    else:
        spaces = [s for s in all_spaces if me.principal.can("approve", s)]
    if space is not None:
        spaces = [s for s in spaces if s == space]
    if not spaces:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
    since = datetime.now(UTC) - timedelta(days=REPORT_DAYS)
    today = date.today()
    docs = (await session.execute(select(Document))).scalars().all()
    in_scope = {d.id: d for d in docs if owner_space(d) in spaces}

    latest_method: dict[uuid.UUID, SopApproval] = {}
    for a in (
        await session.execute(select(SopApproval).order_by(SopApproval.approved_at))
    ).scalars():
        latest_method[a.document_id] = a
    open_requests = set(
        (
            await session.execute(
                select(ReviewRequest.document_id).where(ReviewRequest.status == "open")
            )
        ).scalars()
    )
    unattributed = (
        (
            await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.author_source == "unattributed",
                    DocumentVersion.committed_at >= since,
                )
            )
        )
        .scalars()
        .all()
    )

    def item(doc: Document, **detail) -> GovernanceItem:
        # Titles only for documents the reader may see (ids otherwise).
        return GovernanceItem(
            document_id=str(doc.id),
            title=doc.title if visible(me.principal, doc) else None,
            space=owner_space(doc),
            detail=detail,
        )

    out = GovernanceOut(
        spaces=spaces,
        unattributed_edits=[
            item(in_scope[v.document_id], commit=v.git_commit, at=v.committed_at.isoformat())
            for v in unattributed
            if v.document_id in in_scope
        ],
        changes_awaiting_review=[
            item(d, submitted=d.id in open_requests)
            for d in in_scope.values()
            if has_pending_change(d)
        ],
        never_approved=[
            item(d, status=d.status)
            for d in in_scope.values()
            if d.kind == "note" and d.approved_hash is None and d.doc_type != "handover"
        ],
        published_outside_platform=[
            item(d)
            for d in in_scope.values()
            if (a := latest_method.get(d.id)) is not None
            and a.method == "baseline"
            and d.kind == "note"
        ],
        self_approved=[
            item(d, at=a.approved_at.isoformat())
            for d in in_scope.values()
            if (a := latest_method.get(d.id)) is not None
            and a.method == "self"
            and a.approved_at >= since
        ],
        review_overdue=[
            item(d, due=d.review_due.isoformat())
            for d in in_scope.values()
            if d.review_due is not None and d.review_due < today and d.status != "retired"
        ],
        possible_instructions=[
            item(d, patterns=d.injection_flags)
            for d in in_scope.values()
            if d.injection_flags and d.status != "retired"
        ],
    )
    out.access_changes = await _access_changes(session, spaces, since)
    return out


async def _access_changes(session: AsyncSession, spaces: list[str], since: datetime) -> list[dict]:
    """Role assignments and new grants that open these spaces beyond `public`
    (from the audit log). Lets leads see access changes, including any an
    administrator made, without an alert."""
    role_spaces: dict[str, set[str]] = {}
    role_by_id: dict[str, str] = {}
    for role in (await session.execute(select(Role))).scalars():
        role_by_id[str(role.id)] = role.name
        role_spaces[role.name] = {
            g.space
            for g in role.grants
            if g.space in spaces and (g.max_sensitivity != "public" or set(g.actions) - {"ask"})
        }
    events = (
        (
            await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.action.in_(("user_updated", "user_created", "grant_added")),
                    AuditEvent.ts >= since,
                )
                .order_by(AuditEvent.ts.desc())
            )
        )
        .scalars()
        .all()
    )
    names = await _names(
        session,
        [e.actor_id for e in events]
        + [uuid.UUID(e.target_id) for e in events if e.target_type == "user" and e.target_id],
    )
    out = []
    for e in events:
        d = e.details or {}
        if e.action == "grant_added":
            if d.get("space") not in spaces:
                continue
            what = {"role": role_by_id.get(e.target_id or "", "deleted role"), "grant": d}
        else:
            added = d.get("roles_added") if e.action == "user_updated" else d.get("roles")
            touched = sorted({sp for r in added or [] for sp in role_spaces.get(r, ())})
            if not touched:
                continue
            what = {
                "person": names.get(uuid.UUID(e.target_id), "unknown") if e.target_id else None,
                "roles_added": added,
                "spaces": touched,
            }
        out.append(
            {"at": e.ts.isoformat(), "by": names.get(e.actor_id, "system"), "action": e.action}
            | what
        )
    return out[:200]


# --- notifications --------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    unread: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NotificationOut]:
    q = (
        select(Notification)
        .where(Notification.user_id == me.user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread:
        q = q.where(Notification.read_at.is_(None))
    rows = (await session.execute(q)).scalars().all()
    await session.commit()
    await apply_reader_scope(session, me.principal)
    out = []
    for n in rows:
        title = None
        if n.document_id is not None:
            doc = await session.get(Document, n.document_id)
            title = doc.title if doc is not None and visible(me.principal, doc) else None
        out.append(
            NotificationOut(
                id=str(n.id),
                kind=n.kind,
                document_id=str(n.document_id) if n.document_id and title else None,
                title=title,
                ref_id=n.ref_id,
                created_at=n.created_at,
                read=n.read_at is not None,
            )
        )
    await session.commit()
    return out


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    n = await session.get(Notification, notification_id)
    if n is None or n.user_id != me.user.id:
        raise NOT_FOUND
    n.read_at = n.read_at or datetime.now(UTC)
    await session.commit()
