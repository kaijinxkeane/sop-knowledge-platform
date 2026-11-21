"""Editing through the app (plan §3.2): every save is a git commit in the
signed-in user's name, checked against their permissions, then re-indexed
straight away so it is searchable (to permitted users) within seconds.

Edit clashes: every save carries the version (content hash) it started from;
if the file changed meanwhile the save is refused with 409 and nothing is
overwritten.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import PurePosixPath

import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
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
from app.db.models import Document, DocumentAccess, Space
from app.db.scoped import apply_reader_scope
from app.policy.engine import Sensitivity, document_visible, resolve_sensitivity
from app.vault.git import GitVault, VaultPathError
from app.vault.indexer import Indexer
from app.vault.labels import Labels, resolve_labels, vault_config
from app.vault.parse import ATTACHMENT_EXT, parse_note
from app.vault.writes import WriteDenied, check_write

router = APIRouter(prefix="/notes", tags=["editing"])
MAX_UPLOAD = 50 * 1024 * 1024
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')


class NoteCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    space: str
    sensitivity: str = "internal"
    folder: str | None = Field(default=None, max_length=300)
    doc_type: str = Field(default="sop", max_length=32)
    programme: str | None = Field(default=None, max_length=200)
    stage: str | None = Field(default=None, max_length=32)
    body: str = Field(default="", max_length=500_000)


class NoteUpdateIn(BaseModel):
    base_version: str = Field(min_length=64, max_length=64)
    content: str = Field(max_length=500_000)


class SourceOut(BaseModel):
    id: str
    vault_path: str
    version: str  # send back as base_version when saving
    content: str


class SavedOut(BaseModel):
    id: str
    vault_path: str
    version: str
    commit: str


def _version(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(title: str) -> str:
    name = re.sub(r"\s+", " ", _UNSAFE.sub(" ", title)).strip(" .")
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "title has no usable characters")
    return name[:120]


def _labels_in_force(rows: list[DocumentAccess]) -> Labels:
    owner = next((r for r in rows if r.role == "owner"), None)
    if owner is None:
        return Labels(space=None, sensitivity=Sensitivity.RESTRICTED)
    return Labels(
        space=owner.space,
        sensitivity=resolve_sensitivity(owner.sensitivity),
        shared_with=[
            (r.space, resolve_sensitivity(r.sensitivity)) for r in rows if r.role == "shared"
        ],
    )


async def _spaces(session: AsyncSession) -> set[str]:
    return set((await session.execute(select(Space.name))).scalars())


async def _visible_note(
    session: AsyncSession, me: CurrentUser, note_id: uuid.UUID, kind: str | None = "note"
) -> tuple[Document, list[DocumentAccess]]:
    """Load a note the user can see (RLS + policy engine), then leave reader mode."""
    await session.commit()
    await apply_reader_scope(session, me.principal)
    doc = await session.get(Document, note_id)
    if doc is None or (kind and doc.kind != kind):
        raise NOT_FOUND
    rows = list(doc.access)
    if not document_visible(me.principal, [(r.space, r.sensitivity) for r in rows]):
        raise NOT_FOUND
    await session.commit()  # back to the normal role for writes
    # Re-read the full access rows (not only the ones visible to this user).
    all_rows = (
        (await session.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc.id)))
        .scalars()
        .all()
    )
    return doc, list(all_rows)


async def _reindex(sessions: async_sessionmaker, git: GitVault, embed, paths: list[str]) -> None:
    await Indexer(git, sessions, embed).index_paths(paths)


def _deny(exc: WriteDenied) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))


@router.post("", response_model=SavedOut, status_code=201)
async def create_note(
    body: NoteCreateIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    sessions: async_sessionmaker = Depends(get_session_factory),
    embed=Depends(get_embedder),
) -> SavedOut:
    config = vault_config()
    spaces = await _spaces(session)
    if body.space not in spaces:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown space")
    if body.stage and body.stage not in config.stages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown stage")
    folder = (body.folder or f"Drafts/{body.space}").strip("/")
    rel = f"{folder}/{safe_name(body.title)}.md"
    try:
        full = git.safe_path(rel)
    except VaultPathError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    if config.is_ignored(rel):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "that folder is not indexed")

    fm = {
        "doc_type": body.doc_type,
        "title": body.title.strip(),
        "status": "draft",
        "space": body.space,
        "sensitivity": body.sensitivity,
        "owner": me.user.display_name,
    }
    if body.programme:
        fm["programme"] = body.programme.strip()
    if body.stage:
        fm["stage"] = body.stage
    content = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + (body.body.strip() or f"# {body.title.strip()}")
        + "\n"
    )
    parsed = parse_note(rel, content)
    new = resolve_labels(rel, parsed.frontmatter, content, known_spaces=spaces, config=config)
    try:
        check_write(me.principal, None, new, old_status=None, new_status="draft")
    except WriteDenied as exc:
        raise _deny(exc) from None

    with git.lock():
        if full.exists():
            raise HTTPException(status.HTTP_409_CONFLICT, "a note with this name already exists")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        sha = git.commit(
            [rel],
            f"Create {rel}",
            author_name=me.user.display_name,
            author_email=me.user.email,
            user_id=me.user.id,
        )
    await _reindex(sessions, git, embed, [rel])
    async with sessions() as s:
        doc = (await s.execute(select(Document).where(Document.vault_path == rel))).scalar_one()
        doc.author_id = me.user.id
        await audit.record(
            s,
            "note_created",
            actor_id=me.user.id,
            target_type="document",
            target_id=doc.id,
            details={"space": body.space, "commit": sha},
        )
        await s.commit()
    return SavedOut(id=str(doc.id), vault_path=rel, version=_version(content.encode()), commit=sha)


@router.get("/{note_id}/source", response_model=SourceOut)
async def get_source(
    note_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> SourceOut:
    doc, _ = await _visible_note(session, me, note_id)
    data = git.safe_path(doc.vault_path).read_bytes()
    return SourceOut(
        id=str(doc.id),
        vault_path=doc.vault_path,
        version=_version(data),
        content=data.decode("utf-8", errors="replace"),
    )


@router.put("/{note_id}", response_model=SavedOut)
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdateIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    sessions: async_sessionmaker = Depends(get_session_factory),
    embed=Depends(get_embedder),
) -> SavedOut:
    doc, rows = await _visible_note(session, me, note_id)
    rel = doc.vault_path
    full = git.safe_path(rel)
    old_labels = _labels_in_force(rows)
    if old_labels.space is None or not me.principal.can("contribute", old_labels.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't edit this note")
    parsed = parse_note(rel, body.content)
    new = resolve_labels(
        rel,
        parsed.frontmatter,
        body.content,
        known_spaces=await _spaces(session),
        config=vault_config(),
        frontmatter_error=parsed.frontmatter_error,
    )
    new_status = str(parsed.frontmatter.get("status") or "") or None
    try:
        check_write(me.principal, old_labels, new, old_status=doc.status, new_status=new_status)
    except WriteDenied as exc:
        raise _deny(exc) from None

    with git.lock():
        current = _version(full.read_bytes()) if full.exists() else None
        if current != body.base_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "message": "this note changed since you opened it; merge and save again",
                    "current_version": current,
                },
            )
        full.write_text(body.content, encoding="utf-8")
        if rel in git.uncommitted():
            sha = git.commit(
                [rel],
                f"Edit {rel}",
                author_name=me.user.display_name,
                author_email=me.user.email,
                user_id=me.user.id,
            )
        else:
            sha = doc.current_commit or ""  # no change
    await _reindex(sessions, git, embed, [rel])
    async with sessions() as s:
        await audit.record(
            s,
            "note_saved",
            actor_id=me.user.id,
            target_type="document",
            target_id=doc.id,
            details={"commit": sha},
        )
        await s.commit()
    return SavedOut(
        id=str(doc.id), vault_path=rel, version=_version(body.content.encode()), commit=sha
    )


@router.post("/{note_id}/attachments", response_model=SavedOut, status_code=201)
async def upload_attachment(
    note_id: uuid.UUID,
    file: UploadFile = File(...),
    source_tool: str | None = Form(default=None, max_length=40),
    original_link: str | None = Form(default=None, max_length=1000),
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    sessions: async_sessionmaker = Depends(get_session_factory),
    embed=Depends(get_embedder),
) -> SavedOut:
    """Attach a deck/PDF/DOCX to a note. The file lands beside the note and gets the
    note's space, but never looser than `internal` (an embed doesn't make it public)."""
    doc, rows = await _visible_note(session, me, note_id)
    labels = _labels_in_force(rows)
    if labels.space is None or not me.principal.can("contribute", labels.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't edit this note")
    name = (
        safe_name(PurePosixPath(file.filename or "").stem)
        + PurePosixPath(file.filename or "").suffix.lower()
    )
    if PurePosixPath(name).suffix not in ATTACHMENT_EXT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"allowed types: {', '.join(sorted(ATTACHMENT_EXT))}",
        )
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is larger than 50 MB")
    note_dir = PurePosixPath(doc.vault_path).parent
    rel = str(note_dir / "attachments" / name)
    full, note_full = git.safe_path(rel), git.safe_path(doc.vault_path)

    line = f"\n![[{name}]]\n"
    if source_tool:
        tool = re.sub(r"[^\w .-]", "", source_tool)[:40]
        link = original_link if original_link and original_link.startswith("https://") else ""
        line += f"*Original: {tool}{' — ' + link if link else ''}*\n"
    with git.lock():
        if full.exists():
            raise HTTPException(status.HTTP_409_CONFLICT, "a file with this name already exists")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        with note_full.open("a", encoding="utf-8") as fh:
            fh.write(line)
        sha = git.commit(
            [rel, doc.vault_path],
            f"Attach {name} to {doc.vault_path}",
            author_name=me.user.display_name,
            author_email=me.user.email,
            user_id=me.user.id,
        )
    async with sessions() as s:
        att = Document(
            vault_path=rel, title=PurePosixPath(name).stem, kind="attachment", author_id=me.user.id
        )
        att.access.append(
            DocumentAccess(
                space=labels.space,
                role="owner",
                source="upload",
                sensitivity=max(labels.sensitivity, Sensitivity.INTERNAL).label,
            )
        )
        s.add(att)
        await s.commit()
    await _reindex(sessions, git, embed, [rel, doc.vault_path])
    async with sessions() as s:
        att = (await s.execute(select(Document).where(Document.vault_path == rel))).scalar_one()
        await audit.record(
            s,
            "attachment_uploaded",
            actor_id=me.user.id,
            target_type="document",
            target_id=att.id,
            details={"note": str(doc.id), "commit": sha, "bytes": len(data)},
        )
        await s.commit()
    return SavedOut(id=str(att.id), vault_path=rel, version=_version(data), commit=sha)
