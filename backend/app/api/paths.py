"""Onboarding paths (frontend spec §9.1, §11).

  GET    /paths                      paths I manage (a space's leads; HR sees all)
  POST   /paths                      a lead builds one for their space
  GET    /paths/{id}                 a manager's view (item titles only if they can read them)
  PUT    /paths/{id}                 replace title, description and steps
  DELETE /paths/{id}
  POST   /paths/{id}/assign          a lead or HR: to people or roles, with a due date
  GET    /me/paths                   my paths with progress and the next item
  GET    /me/paths/{id}              steps and items, each with my done state
  POST   /path-items/{id}/done       "Done" on an item that isn't required reading
  GET    /reports/path-completion    per path and person: done of total (leads, HR)

An item the viewer can't read shows no title, link or type: only that it
exists, so progress still adds up. A required item is done when its SOP's
current version is acknowledged (required reading), never by a click.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import CurrentUser, current_user, get_db
from app.db.models import (
    Document,
    PathAssignment,
    PathItem,
    PathProgress,
    ReadingPath,
    Role,
    User,
)
from app.db.scoped import apply_reader_scope, visible
from app.governance.notify import notify
from app.governance.reading import applies_to, assignees, valid_acks
from app.identity import principal_for
from app.policy.engine import Principal

router = APIRouter(tags=["paths"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")


class ItemIn(BaseModel):
    document_id: uuid.UUID
    required: bool = False


class StepIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    items: list[ItemIn] = Field(default_factory=list, max_length=50)


class PathIn(BaseModel):
    space: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    steps: list[StepIn] = Field(default_factory=list, max_length=20)


class PathAssignIn(BaseModel):
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    roles: list[str] = Field(default_factory=list, max_length=20)
    due_on: date | None = None


class PathItemOut(BaseModel):
    id: str
    required: bool
    readable: bool
    # Only when readable: an unreadable item shows no title, link or type.
    document_id: str | None = None
    title: str | None = None
    kind: str | None = None
    doc_type: str | None = None
    done: bool = False


class PathStepOut(BaseModel):
    title: str
    items: list[PathItemOut]


class PathAssignmentOut(BaseModel):
    id: str
    target_type: str
    target: str
    due_on: date | None


class PathOut(BaseModel):
    id: str
    space: str
    title: str
    description: str
    steps: list[PathStepOut]
    total: int
    done: int
    due_on: date | None = None
    next_item: str | None = None  # id of the first item not done that I can open
    assignments: list[PathAssignmentOut] = []
    can_edit: bool = False


class PersonProgress(BaseModel):
    name: str
    done: int
    total: int
    due_on: date | None
    overdue: bool


class CompletionOut(BaseModel):
    path_id: str
    title: str
    space: str
    total: int
    people: list[PersonProgress]


def _lead(p: Principal, space: str) -> bool:
    return p.can("approve", space)


def _hr(p: Principal) -> bool:
    return p.can("view_gap_reports")


async def _scoped_docs(
    session: AsyncSession, principal: Principal, ids: set[uuid.UUID]
) -> dict[uuid.UUID, Document]:
    """The documents among `ids` this principal can read (RLS and policy engine)."""
    await session.commit()
    await apply_reader_scope(session, principal)
    out = {}
    if ids:
        for d in (await session.execute(select(Document).where(Document.id.in_(ids)))).scalars():
            if visible(principal, d) and d.status != "retired":
                out[d.id] = d
    await session.commit()
    return out


async def _done_items(
    session: AsyncSession, user_id: uuid.UUID, items: list[PathItem]
) -> set[uuid.UUID]:
    clicked = set(
        (
            await session.execute(
                select(PathProgress.item_id).where(
                    PathProgress.user_id == user_id,
                    PathProgress.item_id.in_([i.id for i in items] or [uuid.uuid4()]),
                )
            )
        ).scalars()
    )
    done = set()
    for i in items:
        if i.required:
            if user_id in await valid_acks(session, i.document_id, [user_id]):
                done.add(i.id)
        elif i.id in clicked:
            done.add(i.id)
    return done


def _path_out(
    p: ReadingPath,
    docs: dict[uuid.UUID, Document],
    done: set[uuid.UUID],
    *,
    assignments: list[PathAssignment] = (),
    names: dict[str, str] | None = None,
    due: date | None = None,
    can_edit: bool = False,
) -> PathOut:
    steps: dict[int, PathStepOut] = {}
    next_item = None
    for i in p.items:
        d = docs.get(i.document_id)
        item = PathItemOut(
            id=str(i.id), required=i.required, readable=d is not None, done=i.id in done
        )
        if d is not None:
            item.document_id, item.title = str(d.id), d.title
            item.kind, item.doc_type = d.kind, d.doc_type
            if next_item is None and not item.done:
                next_item = item.id
        steps.setdefault(i.step, PathStepOut(title=i.step_title, items=[])).items.append(item)
    names = names or {}
    return PathOut(
        id=str(p.id),
        space=p.space,
        title=p.title,
        description=p.description,
        steps=[steps[k] for k in sorted(steps)],
        total=len(p.items),
        done=len(done),
        due_on=due,
        next_item=next_item,
        assignments=[
            PathAssignmentOut(
                id=str(a.id),
                target_type=a.target_type,
                target=names.get(a.target, "unknown") if a.target_type == "user" else a.target,
                due_on=a.due_on,
            )
            for a in assignments
        ],
        can_edit=can_edit,
    )


async def _user_names(session: AsyncSession, rows) -> dict[str, str]:
    ids = [uuid.UUID(a.target) for a in rows if a.target_type == "user"]
    if not ids:
        return {}
    res = await session.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {str(i): n for i, n in res.all()}


async def _managed(session: AsyncSession, me: CurrentUser, path_id: uuid.UUID) -> ReadingPath:
    p = await session.get(ReadingPath, path_id)
    if p is None or not (_lead(me.principal, p.space) or _hr(me.principal)):
        raise NOT_FOUND
    return p


async def _set_items(session: AsyncSession, me: CurrentUser, p: ReadingPath, body: PathIn) -> None:
    ids = {it.document_id for s in body.steps for it in s.items}
    docs = await _scoped_docs(session, me.principal, ids)
    if set(docs) != ids:
        # Unknown and unreadable look the same.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "a document on the path can't be found"
        )
    for s in body.steps:
        for it in s.items:
            d = docs[it.document_id]
            if it.required and (d.kind != "note" or d.approved_hash is None):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "only approved SOPs can be required (they are signed off as read)",
                )
    p.items.clear()
    await session.flush()
    for n, s in enumerate(body.steps):
        for k, it in enumerate(s.items):
            p.items.append(
                PathItem(
                    step=n,
                    step_title=s.title.strip(),
                    position=k,
                    document_id=it.document_id,
                    required=it.required,
                )
            )


@router.get("/paths", response_model=list[PathOut])
async def list_paths(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[PathOut]:
    paths = (await session.execute(select(ReadingPath).order_by(ReadingPath.title))).scalars()
    mine = [p for p in paths if _lead(me.principal, p.space) or _hr(me.principal)]
    if not mine and not any("approve" in a for a in me.principal.space_actions().values()):
        if not _hr(me.principal):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only leads and HR")
    return await _manager_views(session, me, mine)


async def _manager_views(session, me: CurrentUser, paths: list[ReadingPath]) -> list[PathOut]:
    ids = {i.document_id for p in paths for i in p.items}
    docs = await _scoped_docs(session, me.principal, ids)
    out = []
    for p in paths:
        assigned = list(
            (
                await session.execute(select(PathAssignment).where(PathAssignment.path_id == p.id))
            ).scalars()
        )
        out.append(
            _path_out(
                p,
                docs,
                set(),
                assignments=assigned,
                names=await _user_names(session, assigned),
                can_edit=_lead(me.principal, p.space),
            )
        )
    return out


@router.post("/paths", response_model=PathOut, status_code=201)
async def create_path(
    body: PathIn, me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> PathOut:
    if not _lead(me.principal, body.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the space's lead builds its paths")
    p = ReadingPath(
        space=body.space,
        title=body.title.strip(),
        description=body.description.strip(),
        created_by=me.user.id,
    )
    await _set_items(session, me, p, body)
    session.add(p)
    await session.flush()
    await audit.record(
        session,
        "path_created",
        actor_id=me.user.id,
        target_type="path",
        target_id=p.id,
        details={"items": len(p.items)},
    )
    await session.commit()
    return (await _manager_views(session, me, [p]))[0]


@router.get("/paths/{path_id}", response_model=PathOut)
async def get_path(
    path_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> PathOut:
    p = await _managed(session, me, path_id)
    return (await _manager_views(session, me, [p]))[0]


@router.put("/paths/{path_id}", response_model=PathOut)
async def update_path(
    path_id: uuid.UUID,
    body: PathIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> PathOut:
    p = await _managed(session, me, path_id)
    if not _lead(me.principal, p.space) or body.space != p.space:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the space's lead edits its paths")
    p.title, p.description = body.title.strip(), body.description.strip()
    await _set_items(session, me, p, body)
    await audit.record(
        session,
        "path_updated",
        actor_id=me.user.id,
        target_type="path",
        target_id=p.id,
        details={"items": len(body.steps)},
    )
    await session.commit()
    return (await _manager_views(session, me, [p]))[0]


@router.delete("/paths/{path_id}", status_code=204)
async def delete_path(
    path_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    p = await _managed(session, me, path_id)
    if not _lead(me.principal, p.space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the space's lead deletes its paths")
    await session.delete(p)
    await audit.record(
        session, "path_deleted", actor_id=me.user.id, target_type="path", target_id=path_id
    )
    await session.commit()


@router.post("/paths/{path_id}/assign", response_model=PathOut)
async def assign_path(
    path_id: uuid.UUID,
    body: PathAssignIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> PathOut:
    p = await _managed(session, me, path_id)
    if not body.user_ids and not body.roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "choose people or roles")
    known = set((await session.execute(select(Role.name))).scalars())
    if set(body.roles) - known:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown role")
    active = set(
        (
            await session.execute(
                select(User.id).where(User.id.in_(body.user_ids), User.is_active.is_(True))
            )
        ).scalars()
    )
    if set(body.user_ids) - active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown person")
    existing = {
        (a.target_type, a.target): a
        for a in (
            await session.execute(select(PathAssignment).where(PathAssignment.path_id == p.id))
        ).scalars()
    }
    touched = []
    for kind, target in [("user", str(u)) for u in dict.fromkeys(body.user_ids)] + [
        ("role", r) for r in dict.fromkeys(body.roles)
    ]:
        a = existing.get((kind, target))
        if a is None:
            a = PathAssignment(
                path_id=p.id,
                target_type=kind,
                target=target,
                due_on=body.due_on,
                assigned_by=me.user.id,
            )
            session.add(a)
        else:
            a.due_on = body.due_on
        touched.append(a)
    await session.flush()
    people = await assignees(session, touched)
    await notify(
        session, [u.id for u in people], "path_assigned", ref_id=str(p.id), skip=me.user.id
    )
    await audit.record(
        session,
        "path_assigned",
        actor_id=me.user.id,
        target_type="path",
        target_id=p.id,
        details={"users": len(body.user_ids), "roles": len(body.roles), "people": len(people)},
    )
    await session.commit()
    return (await _manager_views(session, me, [p]))[0]


async def _my_paths(session: AsyncSession, user: User) -> list[tuple[ReadingPath, date | None]]:
    roles = [r.name for r in user.roles]
    rows = (
        await session.execute(
            select(PathAssignment).where(
                ((PathAssignment.target_type == "user") & (PathAssignment.target == str(user.id)))
                | (
                    (PathAssignment.target_type == "role")
                    & PathAssignment.target.in_(roles or [""])
                )
            )
        )
    ).scalars()
    due: dict[uuid.UUID, date | None] = {}
    for a in rows:
        if a.path_id not in due or (a.due_on and (due[a.path_id] or date.max) > a.due_on):
            due[a.path_id] = a.due_on
    out = []
    for pid, d in due.items():
        p = await session.get(ReadingPath, pid)
        if p is not None:
            out.append((p, d))
    out.sort(key=lambda x: x[0].title.lower())
    return out


@router.get("/me/paths", response_model=list[PathOut])
async def my_paths(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[PathOut]:
    mine = await _my_paths(session, me.user)
    ids = {i.document_id for p, _ in mine for i in p.items}
    docs = await _scoped_docs(session, me.principal, ids)
    out = []
    for p, due in mine:
        done = await _done_items(session, me.user.id, p.items)
        out.append(_path_out(p, docs, done, due=due))
    return out


@router.get("/me/paths/{path_id}", response_model=PathOut)
async def my_path(
    path_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> PathOut:
    for p, due in await _my_paths(session, me.user):
        if p.id == path_id:
            docs = await _scoped_docs(session, me.principal, {i.document_id for i in p.items})
            return _path_out(p, docs, await _done_items(session, me.user.id, p.items), due=due)
    raise NOT_FOUND


@router.post("/path-items/{item_id}/done", status_code=204)
async def mark_done(
    item_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    item = await session.get(PathItem, item_id)
    mine = {p.id for p, _ in await _my_paths(session, me.user)}
    if item is None or item.path_id not in mine:
        raise NOT_FOUND
    if not await _scoped_docs(session, me.principal, {item.document_id}):
        raise NOT_FOUND
    if item.required:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this item is required reading: acknowledge it in the reader"
        )
    exists = await session.get(PathProgress, (me.user.id, item.id))
    if exists is None:
        session.add(PathProgress(user_id=me.user.id, item_id=item.id))
        await session.commit()


@router.get("/reports/path-completion", response_model=list[CompletionOut])
async def completion(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[CompletionOut]:
    """Done of total per person; no item titles (HR may not read restricted items)."""
    paths = [
        p
        for p in (await session.execute(select(ReadingPath).order_by(ReadingPath.title))).scalars()
        if _lead(me.principal, p.space) or _hr(me.principal)
    ]
    if not paths and not (
        _hr(me.principal) or any("approve" in a for a in me.principal.space_actions().values())
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only leads and HR")
    today = datetime.now(UTC).date()
    out = []
    for p in paths:
        assigned = list(
            (
                await session.execute(select(PathAssignment).where(PathAssignment.path_id == p.id))
            ).scalars()
        )
        people = []
        for u in sorted(await assignees(session, assigned), key=lambda u: u.display_name):
            dues = [a.due_on for a in assigned if a.due_on and applies_to(a, u)]
            due = min(dues) if dues else None
            # Progress counts items the learner can open; others can't be done yet.
            readable = await _scoped_docs(
                session, principal_for(u), {i.document_id for i in p.items}
            )
            items = [i for i in p.items if i.document_id in readable]
            done = len(await _done_items(session, u.id, items))
            people.append(
                PersonProgress(
                    name=u.display_name,
                    done=done,
                    total=len(p.items),
                    due_on=due,
                    overdue=due is not None and due < today and done < len(p.items),
                )
            )
        out.append(
            CompletionOut(
                path_id=str(p.id), title=p.title, space=p.space, total=len(p.items), people=people
            )
        )
    return out
