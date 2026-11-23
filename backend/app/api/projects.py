"""Project spaces API (plan §4; access rules in app/projects/service.py).

  POST  /projects                      a space lead creates a project (names any project lead)
  GET   /projects                      projects I lead, belong to, or am asked to share into
  GET   /projects/{id}
  PATCH /projects/{id}                 project lead: rename, hand over the lead
  POST  /projects/{id}/members         project lead: add people
  DELETE /projects/{id}/members/{uid}  project lead: remove someone
  POST  /projects/{id}/shares          project lead: ask another department to share
  POST  /projects/{id}/renew           project lead: new end date (<= 6 months); leads confirm
  POST  /projects/{id}/close           project lead: end it now
  GET   /project-shares                department leads: requests for my spaces
  POST  /project-shares/{id}/approve   that department's lead: whole space or selected
                                       folders/SOPs, at internal (or restricted, by choice)
  POST  /project-shares/{id}/decline | /revoke

Sharing a department always needs that department's lead (checked on their
own roles, never on project access). Creating a project grants nothing.
Requests and approvals are one notification each; nothing else alerts.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import CurrentUser, current_user, get_db
from app.api.reviews import owner_space
from app.db.models import Document, Project, ProjectMember, ProjectShare, Space, User
from app.governance.notify import notify, users_with
from app.identity import principal_for
from app.projects.service import share_valid
from app.vault.labels import vault_config

router = APIRouter(tags=["projects"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
LEVELS = ("public", "internal", "restricted")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "project"


def _dept_lead(me: CurrentUser, space: str) -> bool:
    """A lead of that department by their own roles (project access never counts)."""
    return principal_for(me.user).can("approve", space)


def _role_based_lead_spaces(me: CurrentUser) -> list[str]:
    return [s for s, a in principal_for(me.user).space_actions().items() if "approve" in a]


# --- output ------------------------------------------------------------------------------


class PersonOut(BaseModel):
    id: str
    name: str


class ShareOut(BaseModel):
    id: str
    space: str
    status: str
    scope: str | None
    max_sensitivity: str
    folders: list[str]
    documents: int
    note: str
    approved_until: date | None
    in_force: bool
    renewal_requested: bool


class ProjectOut(BaseModel):
    id: str
    name: str
    space: str
    folder: str
    lead: PersonOut
    starts_on: date
    ends_on: date
    active: bool
    days_left: int
    members: list[PersonOut]
    shares: list[ShareOut]
    my_role: str  # lead | member | department_lead | creator


async def _names(s: AsyncSession, ids) -> dict[uuid.UUID, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = await s.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return dict(rows.all())


def _my_role(me: CurrentUser, p: Project) -> str | None:
    if p.lead_id == me.user.id:
        return "lead"
    if any(m.user_id == me.user.id for m in p.members):
        return "member"
    leads = set(_role_based_lead_spaces(me))
    if any(sh.space in leads and sh.status in ("requested", "approved") for sh in p.shares):
        return "department_lead"
    if p.created_by == me.user.id:
        return "creator"
    return None


async def _out(s: AsyncSession, me: CurrentUser, p: Project) -> ProjectOut:
    today = date.today()
    names = await _names(s, [p.lead_id, *(m.user_id for m in p.members)])
    return ProjectOut(
        id=str(p.id),
        name=p.name,
        space=p.space,
        folder=p.folder,
        lead=PersonOut(id=str(p.lead_id), name=names.get(p.lead_id, "unknown")),
        starts_on=p.starts_on,
        ends_on=p.ends_on,
        active=p.active(today),
        days_left=max((p.ends_on - today).days, 0),
        members=[
            PersonOut(id=str(m.user_id), name=names.get(m.user_id, "unknown")) for m in p.members
        ],
        shares=[
            ShareOut(
                id=str(sh.id),
                space=sh.space,
                status=sh.status,
                scope=sh.scope,
                max_sensitivity=sh.max_sensitivity,
                folders=list(sh.folders or []),
                documents=len(sh.documents or []),
                note=sh.note,
                approved_until=sh.approved_until,
                in_force=p.active(today) and share_valid(sh, today),
                renewal_requested=sh.renewal_requested,
            )
            for sh in sorted(p.shares, key=lambda x: x.space)
        ],
        my_role=_my_role(me, p) or "none",
    )


async def _load(s: AsyncSession, me: CurrentUser, project_id: uuid.UUID) -> Project:
    p = await s.get(Project, project_id)
    if p is None or _my_role(me, p) is None:
        raise NOT_FOUND
    return p


async def _lead_only(s: AsyncSession, me: CurrentUser, project_id: uuid.UUID) -> Project:
    p = await _load(s, me, project_id)
    if p.lead_id != me.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the project lead")
    return p


def _end_date(ends_on: date) -> date:
    today = date.today()
    limit = today + timedelta(days=vault_config().project_max_days)
    if not today < ends_on <= limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"the end date must be after today and no later than {limit.isoformat()}",
        )
    return ends_on


async def _active_users(s: AsyncSession, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    found = set(
        (
            await s.execute(select(User.id).where(User.id.in_(ids), User.is_active.is_(True)))
        ).scalars()
    )
    if set(ids) - found:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown or inactive user")
    return list(dict.fromkeys(ids))


async def _request_share(
    s: AsyncSession, me: CurrentUser, p: Project, space: str, note: str
) -> ProjectShare:
    known = set((await s.execute(select(Space.name))).scalars())
    if space not in known or space.startswith("p-"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown department '{space}'")
    sh = next((x for x in p.shares if x.space == space), None)
    if sh is None:
        sh = ProjectShare(project_id=p.id, space=space, requested_by=me.user.id, status="requested")
        s.add(sh)
        p.shares.append(sh)
    elif sh.status in ("declined", "revoked"):
        sh.status, sh.scope, sh.approved_until = "requested", None, None
    elif sh.status == "approved":
        return sh
    sh.note, sh.requested_by = note.strip()[:1000], me.user.id
    await s.flush()
    await notify(
        s, await users_with(s, "approve", space), "project_share_requested", ref_id=str(sh.id)
    )
    return sh


# --- projects ------------------------------------------------------------------------------


class ShareRequestIn(BaseModel):
    space: str = Field(max_length=64)
    note: str = Field(default="", max_length=1000)  # what the project needs from them


class ProjectIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    ends_on: date
    lead_id: uuid.UUID | None = None  # default: you
    members: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    shares: list[ShareRequestIn] = Field(default_factory=list, max_length=20)


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    if not _role_based_lead_spaces(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only space leads can create projects")
    ends_on = _end_date(body.ends_on)
    lead = body.lead_id or me.user.id
    people = await _active_users(session, [lead, *body.members])
    slug, n = _slug(body.name), 2
    base = slug
    while await session.get(Space, f"p-{slug}") is not None:
        slug, n = f"{base}-{n}", n + 1
    space = f"p-{slug}"
    session.add(Space(name=space, title=body.name.strip(), local_only=True))
    await session.flush()
    p = Project(
        name=body.name.strip(),
        space=space,
        folder=f"{vault_config().project_folder}/{slug}",
        lead_id=lead,
        created_by=me.user.id,
        starts_on=date.today(),
        ends_on=ends_on,
        members=[],
        shares=[],
    )
    session.add(p)
    await session.flush()
    for uid in people:
        p.members.append(ProjectMember(project_id=p.id, user_id=uid, added_by=me.user.id))
    await session.flush()
    for req in body.shares:
        await _request_share(session, me, p, req.space, req.note)
    await notify(session, [u for u in people if u != me.user.id], "project_added", ref_id=str(p.id))
    await audit.record(
        session,
        "project_created",
        actor_id=me.user.id,
        target_type="project",
        target_id=p.id,
        details={
            "members": len(people),
            "shares_requested": sorted(r.space for r in body.shares),
            "ends_on": ends_on.isoformat(),
        },
    )
    await session.commit()
    return await _out(session, me, p)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ProjectOut]:
    rows = (await session.execute(select(Project).order_by(Project.ends_on.desc()))).scalars()
    return [await _out(session, me, p) for p in rows if _my_role(me, p) is not None]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    return await _out(session, me, await _load(session, me, project_id))


class ProjectUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    lead_id: uuid.UUID | None = None  # hand the project to someone else


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdateIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    p = await _lead_only(session, me, project_id)
    changed = {}
    if body.name:
        p.name, changed["name"] = body.name.strip(), True
    if body.lead_id and body.lead_id != p.lead_id:
        (new,) = await _active_users(session, [body.lead_id])
        p.lead_id, changed["lead_changed"] = new, True
        if not any(m.user_id == new for m in p.members):
            p.members.append(ProjectMember(project_id=p.id, user_id=new, added_by=me.user.id))
        await notify(session, [new], "project_lead", ref_id=str(p.id))
    await audit.record(
        session,
        "project_updated",
        actor_id=me.user.id,
        target_type="project",
        target_id=p.id,
        details=changed,
    )
    await session.commit()
    return await _out(session, me, p)


class MembersIn(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


@router.post("/projects/{project_id}/members", response_model=ProjectOut)
async def add_members(
    project_id: uuid.UUID,
    body: MembersIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    p = await _lead_only(session, me, project_id)
    if not p.active(date.today()):
        raise HTTPException(status.HTTP_409_CONFLICT, "the project has ended; renew it first")
    have = {m.user_id for m in p.members}
    new = [u for u in await _active_users(session, body.user_ids) if u not in have]
    for uid in new:
        p.members.append(ProjectMember(project_id=p.id, user_id=uid, added_by=me.user.id))
    await notify(session, new, "project_added", ref_id=str(p.id))
    await audit.record(
        session,
        "project_members_added",
        actor_id=me.user.id,
        target_type="project",
        target_id=p.id,
        details={"added": len(new)},
    )
    await session.commit()
    return await _out(session, me, p)


@router.delete("/projects/{project_id}/members/{user_id}", response_model=ProjectOut)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    p = await _lead_only(session, me, project_id)
    if user_id == p.lead_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "hand the lead to someone else first")
    p.members = [m for m in p.members if m.user_id != user_id]
    await audit.record(
        session,
        "project_member_removed",
        actor_id=me.user.id,
        target_type="project",
        target_id=p.id,
        details={"user": str(user_id)},
    )
    await session.commit()
    return await _out(session, me, p)


@router.post("/projects/{project_id}/shares", response_model=ProjectOut)
async def request_share(
    project_id: uuid.UUID,
    body: ShareRequestIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    p = await _lead_only(session, me, project_id)
    if not p.active(date.today()):
        raise HTTPException(status.HTTP_409_CONFLICT, "the project has ended; renew it first")
    sh = await _request_share(session, me, p, body.space, body.note)
    await audit.record(
        session,
        "project_share_requested",
        actor_id=me.user.id,
        target_type="project_share",
        target_id=sh.id,
        details={"space": sh.space},
    )
    await session.commit()
    return await _out(session, me, p)


class RenewIn(BaseModel):
    ends_on: date


@router.post("/projects/{project_id}/renew", response_model=ProjectOut)
async def renew(
    project_id: uuid.UUID,
    body: RenewIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """New end date (at most 6 months from today). Department shares stay as
    approved until their old date; each lead is asked once to confirm."""
    p = await _lead_only(session, me, project_id)
    p.ends_on, p.closed_at = _end_date(body.ends_on), None
    asked = []
    for sh in p.shares:
        if sh.status == "approved" and (sh.approved_until or date.min) < p.ends_on:
            sh.renewal_requested = True
            asked.append(sh)
            await notify(
                session,
                await users_with(session, "approve", sh.space),
                "project_share_renewal",
                ref_id=str(sh.id),
                dedupe=f"project_share_renewal:{sh.id}:{p.ends_on.isoformat()}",
            )
    await audit.record(
        session,
        "project_renewed",
        actor_id=me.user.id,
        target_type="project",
        target_id=p.id,
        details={"ends_on": p.ends_on.isoformat(), "shares_to_confirm": len(asked)},
    )
    await session.commit()
    return await _out(session, me, p)


@router.post("/projects/{project_id}/close", response_model=ProjectOut)
async def close(
    project_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjectOut:
    p = await _lead_only(session, me, project_id)
    p.closed_at = datetime.now(UTC)
    await audit.record(
        session, "project_closed", actor_id=me.user.id, target_type="project", target_id=p.id
    )
    await session.commit()
    return await _out(session, me, p)


# --- department leads: share requests -------------------------------------------------------


class ShareRequestOut(BaseModel):
    id: str
    project_id: str
    project: str
    project_lead: str
    members: int
    ends_on: date
    space: str
    status: str
    note: str
    renewal_requested: bool


@router.get("/project-shares", response_model=list[ShareRequestOut])
async def share_requests(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ShareRequestOut]:
    spaces = _role_based_lead_spaces(me)
    if not spaces:
        return []
    rows = (
        await session.execute(
            select(ProjectShare, Project)
            .join(Project, Project.id == ProjectShare.project_id)
            .where(ProjectShare.space.in_(spaces))
            .order_by(ProjectShare.created_at.desc())
        )
    ).all()
    return [await _share_out(session, sh, p) for sh, p in rows]


async def _share_out(session: AsyncSession, sh: ProjectShare, p: Project) -> ShareRequestOut:
    names = await _names(session, [p.lead_id])
    return ShareRequestOut(
        id=str(sh.id),
        project_id=str(p.id),
        project=p.name,
        project_lead=names.get(p.lead_id, "unknown"),
        members=len(p.members),
        ends_on=p.ends_on,
        space=sh.space,
        status=sh.status,
        note=sh.note,
        renewal_requested=sh.renewal_requested,
    )


class ApproveShareIn(BaseModel):
    scope: str = Field(pattern="^(space|selected)$")
    folders: list[str] = Field(default_factory=list, max_length=100)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    max_sensitivity: str = Field(default="internal", pattern="^(public|internal|restricted)$")


async def _share_for_lead(
    session: AsyncSession, me: CurrentUser, share_id: uuid.UUID
) -> tuple[ProjectShare, Project]:
    sh = await session.get(ProjectShare, share_id)
    if sh is None or not _dept_lead(me, sh.space):
        raise NOT_FOUND
    return sh, await session.get(Project, sh.project_id)


def _folder(path: str) -> str:
    f = path.replace("\\", "/").strip().strip("/")
    if not f or ".." in f.split("/") or f.startswith("."):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid folder")
    return f + "/"


@router.post("/project-shares/{share_id}/approve", response_model=ShareRequestOut)
async def approve_share(
    share_id: uuid.UUID,
    body: ApproveShareIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ShareRequestOut:
    """The department lead decides what the project may read: the whole space or
    selected folders/SOPs, until the project's end date. Read-only."""
    sh, p = await _share_for_lead(session, me, share_id)
    if sh.status in ("declined", "revoked") and not sh.renewal_requested:
        sh.status = "requested"
    folders = [_folder(f) for f in body.folders] if body.scope == "selected" else []
    docs: list[str] = []
    if body.scope == "selected":
        for d in body.document_ids:
            doc = await session.get(Document, d)
            if doc is None or owner_space(doc) != sh.space:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "that SOP is not in this department"
                )
            docs.append(str(d))
        if not folders and not docs:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "choose folders or SOPs to share"
            )
    sh.status, sh.scope = "approved", body.scope
    sh.folders, sh.documents, sh.max_sensitivity = folders, docs, body.max_sensitivity
    sh.decided_by, sh.decided_at = me.user.id, datetime.now(UTC)
    sh.approved_until, sh.renewal_requested = p.ends_on, False
    await notify(session, [p.lead_id], "project_share_approved", ref_id=str(sh.id))
    await audit.record(
        session,
        "project_share_approved",
        actor_id=me.user.id,
        target_type="project_share",
        target_id=sh.id,
        details={
            "space": sh.space,
            "scope": sh.scope,
            "level": sh.max_sensitivity,
            "folders": len(folders),
            "documents": len(docs),
            "until": p.ends_on.isoformat(),
        },
    )
    await session.commit()
    return await _share_out(session, sh, p)


async def _decide(session, me, share_id, new_status: str, action: str) -> dict:
    sh, p = await _share_for_lead(session, me, share_id)
    sh.status, sh.decided_by, sh.decided_at = new_status, me.user.id, datetime.now(UTC)
    sh.approved_until, sh.renewal_requested = None, False
    await notify(session, [p.lead_id], f"project_share_{new_status}", ref_id=str(sh.id))
    await audit.record(
        session,
        action,
        actor_id=me.user.id,
        target_type="project_share",
        target_id=sh.id,
        details={"space": sh.space},
    )
    await session.commit()
    return {"status": new_status}


@router.post("/project-shares/{share_id}/decline")
async def decline_share(
    share_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await _decide(session, me, share_id, "declined", "project_share_declined")


@router.post("/project-shares/{share_id}/revoke")
async def revoke_share(
    share_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Stop sharing now (any time, by that department's lead)."""
    return await _decide(session, me, share_id, "revoked", "project_share_revoked")
