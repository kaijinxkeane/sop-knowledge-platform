"""Library: document metadata, slides/pages, versions and files, filtered by scope.

Two independent checks on every read: Postgres row-level security (queries run
as `sop_reader` with the user's scopes) and the policy engine in Python.
Hidden documents answer 404, exactly like missing ones.
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db, get_git
from app.db.models import AttachmentPart, Document, DocumentAccess, DocumentVersion
from app.db.scoped import apply_reader_scope
from app.policy.engine import document_visible, resolve_sensitivity
from app.vault.git import GitVault

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


class PartOut(BaseModel):
    part: str
    number: int
    title: str
    speaker_notes: str


class VersionOut(BaseModel):
    commit: str
    author_name: str
    author_source: str  # app | git | unattributed
    authored_by: str | None
    committed_at: datetime


def _out(doc: Document, me: CurrentUser) -> DocumentOut | None:
    rows = [(a.space, a.sensitivity) for a in doc.access]
    if not document_visible(me.principal, rows):
        return None
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
            AccessOut(space=s, sensitivity=resolve_sensitivity(v).label)
            for s, v in rows
            if me.principal.can_read(s, v)
        ],
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


@router.get("/{document_id}/versions", response_model=list[VersionOut])
async def get_versions(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[VersionOut]:
    doc = await _visible(session, me, document_id)
    rows = (
        await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.committed_at.desc())
        )
    ).scalars()
    return [
        VersionOut(
            commit=v.git_commit,
            author_name=v.author_name,
            author_source=v.author_source,
            authored_by=str(v.authored_by) if v.authored_by else None,
            committed_at=v.committed_at,
        )
        for v in rows
    ]


@router.get("/{document_id}/file")
async def get_file(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> Response:
    """The original file (deck, PDF, note), only to users who may read it."""
    doc = await _visible(session, me, document_id)
    try:
        data = git.safe_path(doc.vault_path).read_bytes()
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
