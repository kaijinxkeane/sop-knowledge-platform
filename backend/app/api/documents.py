"""Library: document metadata, slides/pages, versions and files, filtered by scope.

Two independent checks on every read: Postgres row-level security (queries run
as `sop_reader` with the user's scopes) and the policy engine in Python.
Hidden documents answer 404, exactly like missing ones.
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db, get_git
from app.db.models import (
    AttachmentPart,
    Document,
    DocumentAccess,
    DocumentLink,
    DocumentVersion,
    Space,
)
from app.db.scoped import apply_reader_scope, has_pending_change, sees_latest, visible
from app.governance.history import approved_commits, readable_versions
from app.policy.engine import effective_access
from app.vault.git import GitError, GitVault
from app.vault.labels import vault_config

router = APIRouter(prefix="/documents", tags=["knowledge"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")


class AccessOut(BaseModel):
    space: str
    sensitivity: str  # resolved: invalid labels show as restricted


class DocumentOut(BaseModel):
    id: str
    title: str
    vault_path: str
    kind: str
    doc_type: str
    status: str
    programme: str | None
    stage: str | None
    owner: str | None
    access: list[AccessOut]
    approved: bool = False  # has an approved version (only that is cited)
    pending_change: bool = False  # editors only: the latest version isn't approved yet
    review_due: date | None = None


class VersionContentOut(BaseModel):
    commit: str
    author_name: str
    committed_at: datetime
    approved: bool
    content: str


class PartOut(BaseModel):
    part: str
    number: int
    title: str
    speaker_notes: str


class VersionOut(BaseModel):
    commit: str
    approved: bool = False  # this exact version was approved at some point
    live: bool = False  # the approved version answers are cited from now
    latest: bool = False  # the newest version (may be unapproved: editors only)
    author_name: str
    author_source: str  # app | git | unattributed
    authored_by: str | None
    committed_at: datetime


class BacklinkOut(BaseModel):
    id: str
    title: str
    kind: str
    embed: bool  # embedded (![[...]]) rather than linked


def _out(doc: Document, me: CurrentUser) -> DocumentOut | None:
    if not visible(me.principal, doc):
        return None
    rows = effective_access([(a.space, a.sensitivity) for a in doc.access], doc.safeguards or ())
    return DocumentOut(
        id=str(doc.id),
        title=doc.title,
        vault_path=doc.vault_path,
        kind=doc.kind,
        doc_type=doc.doc_type,
        status=doc.status,
        programme=doc.programme,
        stage=doc.stage,
        owner=doc.owner,
        access=[
            AccessOut(space=s, sensitivity=v.label) for s, v in rows if me.principal.can_read(s, v)
        ],
        approved=doc.approved_hash is not None,
        pending_change=has_pending_change(doc) and sees_latest(me.principal, doc),
        review_due=doc.review_due,
    )


async def _reader(session: AsyncSession, me: CurrentUser) -> None:
    await session.commit()  # end the owner transaction used for sign-in checks
    await apply_reader_scope(session, me.principal)


async def _visible(session: AsyncSession, me: CurrentUser, document_id: uuid.UUID) -> Document:
    await _reader(session, me)
    doc = await session.get(Document, document_id)
    if doc is None or _out(doc, me) is None:
        raise NOT_FOUND
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    space: str | None = Query(default=None, max_length=64),
    programme: str | None = Query(default=None, max_length=200),
    stage: str | None = Query(default=None, max_length=32),
    doc_type: str | None = Query(default=None, max_length=32),
    kind: str | None = Query(default=None, max_length=16),
) -> list[DocumentOut]:
    await _reader(session, me)
    q = select(Document).order_by(Document.title)
    if space:
        q = q.where(
            Document.id.in_(select(DocumentAccess.document_id).where(DocumentAccess.space == space))
        )
    for col, val in (
        (Document.programme, programme),
        (Document.stage, stage),
        (Document.doc_type, doc_type),
        (Document.kind, kind),
    ):
        if val:
            q = q.where(col == val)
    docs = (await session.execute(q)).scalars().all()
    return [out for d in docs if (out := _out(d, me)) is not None]


@router.get("/stages", response_model=list[str])
async def list_stages(_: CurrentUser = Depends(current_user)) -> list[str]:
    """Delivery stages in order (config/vault.yaml), for the Library's stage columns."""
    return list(vault_config().stages)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentOut:
    return _out(await _visible(session, me, document_id), me)


@router.get("/{document_id}/parts", response_model=list[PartOut])
async def get_parts(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[PartOut]:
    """Slides (with speaker notes) or PDF pages, for viewers and citations."""
    doc = await _visible(session, me, document_id)
    parts = (
        await session.execute(
            select(AttachmentPart)
            .where(AttachmentPart.document_id == doc.id)
            .order_by(AttachmentPart.number)
        )
    ).scalars()
    return [
        PartOut(part=p.part, number=p.number, title=p.title, speaker_notes=p.speaker_notes)
        for p in parts
    ]


@router.get("/{document_id}/backlinks", response_model=list[BacklinkOut])
async def get_backlinks(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[BacklinkOut]:
    """Notes that link to or embed this one ("used in"). A linking note the user
    can't read is left out entirely: no title, no count."""
    doc = await _visible(session, me, document_id)
    rows = (
        await session.execute(
            select(Document, DocumentLink.embed)
            .join(DocumentLink, DocumentLink.from_id == Document.id)
            .where(DocumentLink.to_id == doc.id, Document.id != doc.id)
            .order_by(Document.title)
        )
    ).all()
    seen: dict[uuid.UUID, BacklinkOut] = {}
    for d, embed in rows:
        if d.id in seen or _out(d, me) is None:
            continue
        seen[d.id] = BacklinkOut(id=str(d.id), title=d.title, kind=d.kind, embed=embed)
    return list(seen.values())


async def _history_doc(
    session: AsyncSession, me: CurrentUser, document_id: uuid.UUID
) -> tuple[Document, bool]:
    """A visible document and whether this user sees its unapproved changes,
    both decided under RLS; then reloaded as the owner role (all access rows,
    for the labels-it-had check, and approvals, which `sop_reader` can't read)."""
    doc = await _visible(session, me, document_id)
    editor = sees_latest(me.principal, doc)
    await session.commit()
    await session.refresh(doc)
    return doc, editor


async def _spaces(session: AsyncSession) -> set[str]:
    return set((await session.execute(select(Space.name))).scalars())


@router.get("/{document_id}/versions", response_model=list[VersionOut])
async def get_versions(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> list[VersionOut]:
    """Versions this person may read: approved ones (all versions for the
    note's editors), each judged by the labels it had (app.governance.history)."""
    doc, editor = await _history_doc(session, me, document_id)
    rows = list(
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.committed_at.desc())
            )
        ).scalars()
    )
    if doc.kind != "note":
        readable = {v.git_commit for v in rows} if editor else set()
        approved: set[str] = set()
    else:
        approved = await approved_commits(session, doc)
        readable = await readable_versions(
            session,
            me.principal,
            doc,
            git,
            [v.git_commit for v in rows],
            await _spaces(session),
            editor=editor,
        )
    return [
        VersionOut(
            commit=v.git_commit,
            author_name=v.author_name,
            author_source=v.author_source,
            authored_by=str(v.authored_by) if v.authored_by else None,
            committed_at=v.committed_at,
            approved=v.git_commit in approved,
            live=v.git_commit == doc.approved_commit,
            latest=v.git_commit == doc.current_commit,
        )
        for v in rows
        if v.git_commit in readable
    ]


@router.get("/{document_id}/versions/{commit}", response_model=VersionContentOut)
async def get_version(
    document_id: uuid.UUID,
    commit: str = Path(pattern=r"^[0-9a-f]{40}$"),
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> VersionContentOut:
    """The text of one version of a note, for reading and side-by-side diffs.
    Unknown, unapproved (for non-editors) and once-narrower versions all 404."""
    doc, editor = await _history_doc(session, me, document_id)
    if doc.kind != "note":
        raise NOT_FOUND
    v = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.git_commit == commit
        )
    )
    if v is None or commit not in await readable_versions(
        session, me.principal, doc, git, [commit], await _spaces(session), editor=editor
    ):
        raise NOT_FOUND
    try:
        content = git.show(doc.vault_path, commit).decode("utf-8", errors="replace")
    except GitError:
        raise NOT_FOUND from None
    return VersionContentOut(
        commit=commit,
        author_name=v.author_name,
        committed_at=v.committed_at,
        approved=commit in await approved_commits(session, doc),
        content=content,
    )


@router.get("/{document_id}/file")
async def get_file(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> Response:
    """The original file (deck, PDF, note), only to users who may read it."""
    doc = await _visible(session, me, document_id)
    from app.api.notes import read_for

    try:
        data = read_for(me, doc, git)
    except (OSError, ValueError):
        raise NOT_FOUND from None
    media = mimetypes.guess_type(doc.vault_path)[0] or "application/octet-stream"
    name = doc.vault_path.rsplit("/", 1)[-1].replace('"', "")
    return Response(
        data,
        media_type=media,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
