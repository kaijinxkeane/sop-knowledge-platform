"""Library folders: each department arranges its own documents.

  GET    /library/folders                 folders I can see, by department
  POST   /library/folders                 new folder inside a department (contribute)
  DELETE /library/folders/{id}            remove an empty folder made in the app
  POST   /library/documents/{id}/move     move a document to another folder

Departments never mix: a folder belongs to the department whose vault folder
it sits under (config/vault.yaml folder rules, longest match), and a document
moves only to a folder where it keeps exactly the access it has now (same
department, sensitivity and shares). So moving never widens, narrows or moves
a document to another department; that stays a reviewed label change.

A document keeps its identity when it moves (approvals, versions, bookmarks,
required reading), and its past versions are still found under the old name
(GitVault.show follows moves). Folder names are shown only to people who can
work in the department or read something inside the folder.
"""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.db.models import Document, DocumentAccess, LibraryFolder, ProgrammeOrder, Space
from app.db.scoped import apply_reader_scope, visible
from app.vault.folders import department_of, may_leave
from app.vault.git import GitVault, VaultPathError
from app.vault.indexer import Indexer
from app.vault.labels import VaultConfig, labels_from_rows, resolve_labels, vault_config

router = APIRouter(prefix="/library", tags=["library"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &'(),._-]{0,79}$")


class FolderOut(BaseModel):
    id: str | None  # set for folders made in the app
    space: str
    path: str
    can_edit: bool


class FolderIn(BaseModel):
    space: str = Field(max_length=64)
    parent: str = Field(max_length=500)
    name: str = Field(min_length=1, max_length=80)


class MoveIn(BaseModel):
    folder: str = Field(max_length=500)


class MovedOut(BaseModel):
    id: str
    vault_path: str


def _clean(path: str) -> str:
    return "/".join(p.strip() for p in path.strip().strip("/").split("/") if p.strip())


def _roots(space: str, config: VaultConfig) -> list[str]:
    return [
        r.path.strip("/")
        for r in config.folder_rules
        if r.space == space and department_of(r.path.strip("/"), config) == space
    ]


async def _readable_docs(session: AsyncSession, me: CurrentUser) -> dict[uuid.UUID, Document]:
    """Every document this person can read (RLS and the policy engine)."""
    await session.commit()
    await apply_reader_scope(session, me.principal)
    docs = {
        d.id: d
        for d in (await session.execute(select(Document))).scalars().all()
        if visible(me.principal, d)
    }
    await session.commit()
    return docs


@router.get("/folders", response_model=list[FolderOut])
async def list_folders(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[FolderOut]:
    config = vault_config()
    spaces = list((await session.execute(select(Space.name))).scalars())
    editable = {s for s in spaces if me.principal.can("contribute", s)}
    readable = [d.vault_path for d in (await _readable_docs(session, me)).values()]
    out: dict[str, FolderOut] = {}
    for space in sorted(editable):
        for root in _roots(space, config):
            out[root] = FolderOut(id=None, space=space, path=root, can_edit=True)
    for f in (await session.execute(select(LibraryFolder))).scalars():
        holds_readable = any(p.startswith(f.path + "/") for p in readable)
        if f.space in editable or holds_readable:
            out[f.path] = FolderOut(
                id=str(f.id), space=f.space, path=f.path, can_edit=f.space in editable
            )
    return sorted(out.values(), key=lambda f: (f.space, f.path.lower()))


@router.post("/folders", response_model=FolderOut, status_code=201)
async def create_folder(
    body: FolderIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> FolderOut:
    config = vault_config()
    if not me.principal.can("contribute", body.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't add folders in this department")
    parent, name = _clean(body.parent), body.name.strip()
    if not NAME.match(name) or name in (".", ".."):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "folder names can't contain slashes or start with a dot",
        )
    if department_of(parent, config) != body.space:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "choose a folder of this department"
        )
    path = f"{parent}/{name}"
    try:
        exists_on_disk = git.safe_path(path).exists()
    except VaultPathError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid folder name") from None
    taken = (
        await session.execute(select(LibraryFolder).where(LibraryFolder.path == path))
    ).scalar()
    if taken or exists_on_disk:
        raise HTTPException(status.HTTP_409_CONFLICT, "that folder already exists")
    folder = LibraryFolder(space=body.space, path=path, created_by=me.user.id)
    session.add(folder)
    await session.flush()
    await audit.record(
        session,
        "folder_created",
        actor_id=me.user.id,
        target_type="folder",
        target_id=folder.id,
        details={"space": body.space},
    )
    await session.commit()
    return FolderOut(id=str(folder.id), space=folder.space, path=folder.path, can_edit=True)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> None:
    folder = await session.get(LibraryFolder, folder_id)
    if folder is None or not me.principal.can("contribute", folder.space):
        raise NOT_FOUND
    has_docs = (
        await session.execute(
            select(Document.id)
            .where(Document.vault_path.startswith(folder.path + "/", autoescape=True))
            .limit(1)
        )
    ).scalar()
    inside = (
        await session.execute(
            select(LibraryFolder.id)
            .where(LibraryFolder.path.startswith(folder.path + "/", autoescape=True))
            .limit(1)
        )
    ).scalar()
    on_disk = git.safe_path(folder.path)
    if has_docs or inside or (on_disk.is_dir() and any(on_disk.iterdir())):
        raise HTTPException(status.HTTP_409_CONFLICT, "only an empty folder can be removed")
    await session.delete(folder)
    await audit.record(
        session, "folder_deleted", actor_id=me.user.id, target_type="folder", target_id=folder_id
    )
    await session.commit()


AUTHORITATIVE = ("frontmatter", "folder_rule")


def _values(labels) -> tuple:
    return (
        labels.space,
        labels.sensitivity,
        sorted((s, lvl.label) for s, lvl in labels.shared_with if s != labels.space),
    )


def _same_access(before, after, in_force) -> bool:
    """After the move the document must have exactly the access it has now.
    Where the new folder decides access (a folder rule or the note's own
    labels), it must give the access in force, e.g. a note placed from the
    Inbox by a reviewer can be filed where the folder says the same thing.
    Where it doesn't, the decisions in force are kept, as long as the old
    folder didn't decide either."""
    if after.source in AUTHORITATIVE:
        return _values(after) == _values(in_force)
    return before.source not in AUTHORITATIVE


@router.post("/documents/{doc_id}/move", response_model=MovedOut)
async def move_document(
    doc_id: uuid.UUID,
    body: MoveIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
    sessions: async_sessionmaker = Depends(get_session_factory),
    embed=Depends(get_embedder),
) -> MovedOut:
    config = vault_config()
    await session.commit()
    await apply_reader_scope(session, me.principal)
    doc = await session.get(Document, doc_id)
    if doc is None or not visible(me.principal, doc):
        raise NOT_FOUND
    await session.commit()
    rows = (
        (await session.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc.id)))
        .scalars()
        .all()
    )
    in_force = labels_from_rows(rows)
    if in_force.space is None or not me.principal.can("contribute", in_force.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't move this document")

    old = doc.vault_path
    old_folder = str(PurePosixPath(old).parent).strip(".")
    folder = _clean(body.folder)
    if not may_leave(old_folder, config):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "documents in this folder can't be moved"
        )
    target = department_of(folder, config)
    if target != in_force.space:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "a document can only move between its own department's folders",
        )
    new = f"{folder}/{PurePosixPath(old).name}"
    if new == old:
        return MovedOut(id=str(doc.id), vault_path=old)
    known = set((await session.execute(select(Space.name))).scalars())
    fm = doc.frontmatter or {}
    before = resolve_labels(old, fm, "", known_spaces=known, config=config)
    after = resolve_labels(new, fm, "", known_spaces=known, config=config)
    if not _same_access(before, after, in_force):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "moving it there would change who can read it; change its access in the editor first",
        )

    with git.lock():
        try:
            git.move(old, new)
        except VaultPathError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        # The index follows the document before git does, so a background
        # re-index never sees it as deleted.
        doc.vault_path = new
        await session.commit()
        try:
            sha = git.commit(
                [old, new],
                f"Move {old} to {new}",
                author_name=me.user.display_name,
                author_email=me.user.email,
                user_id=me.user.id,
            )
        except Exception:
            git.move(new, old)
            doc.vault_path = old
            await session.commit()
            raise
    await Indexer(git, sessions, embed).index_paths([new])
    await audit.record(
        session,
        "document_moved",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={"commit": sha},
    )
    await session.commit()
    return MovedOut(id=str(doc.id), vault_path=new)


# --- manual order inside a programme stage -----------------------------------------


class OrderOut(BaseModel):
    document_id: str
    position: int


class OrderIn(BaseModel):
    programme: str = Field(min_length=1, max_length=200)
    stage: str | None = Field(default=None, max_length=32)
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


@router.get("/order", response_model=list[OrderOut])
async def programme_order(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[OrderOut]:
    """Hand-arranged positions, for documents this person can read (ids only)."""
    readable = await _readable_docs(session, me)
    rows = (await session.execute(select(ProgrammeOrder))).scalars().all()
    return [
        OrderOut(document_id=str(r.document_id), position=r.position)
        for r in rows
        if r.document_id in readable
    ]


@router.put("/order", status_code=204)
async def set_programme_order(
    body: OrderIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Arrange one stage of a programme. Every document listed must be readable,
    in that programme and stage, and in a department where this person may
    contribute. Documents they can't see keep their place."""
    ids = list(dict.fromkeys(body.document_ids))
    readable = await _readable_docs(session, me)
    for doc_id in ids:
        doc = readable.get(doc_id)
        if doc is None:
            raise NOT_FOUND
        if doc.programme != body.programme or (doc.stage or None) != (body.stage or None):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "documents must be in this programme stage"
            )
        owner = next((a.space for a in doc.access if a.role == "owner"), None)
        if owner is None or not me.principal.can("contribute", owner):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "you can't arrange this programme")
    # The whole stage as everyone with full access sees it (outside the reader
    # scope: positions only, nothing is returned). The listed documents take
    # the places they held, in the new order; the others stay where they were,
    # and the stage is renumbered so no two documents share a place.
    same_stage = (
        Document.stage == body.stage
        if body.stage
        else (Document.stage.is_(None) | (Document.stage == ""))
    )
    stage = [
        (doc_id, title)
        for doc_id, title in await session.execute(
            select(Document.id, Document.title).where(
                Document.programme == body.programme, same_stage
            )
        )
    ]
    existing = {
        r.document_id: r
        for r in (
            await session.execute(
                select(ProgrammeOrder).where(ProgrammeOrder.document_id.in_([i for i, _ in stage]))
            )
        ).scalars()
    }
    current = [
        i
        for i, _ in sorted(
            stage,
            key=lambda d: (
                existing[d[0]].position if d[0] in existing else float("inf"),
                d[1].lower(),
            ),
        )
    ]
    listed, new = set(ids), iter(ids)
    sequence = [next(new) if doc_id in listed else doc_id for doc_id in current]
    for n, doc_id in enumerate(sequence):
        row = existing.get(doc_id)
        if row is None:
            row = ProgrammeOrder(document_id=doc_id, updated_by=me.user.id)
        elif doc_id in listed:
            row.updated_by = me.user.id
        row.position = (n + 1) * 10
        session.add(row)
    await audit.record(
        session,
        "programme_arranged",
        actor_id=me.user.id,
        target_type="programme",
        target_id=None,
        details={"documents": len(ids)},
    )
    await session.commit()
