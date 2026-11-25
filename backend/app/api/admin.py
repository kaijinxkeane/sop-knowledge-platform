"""Admin: users, roles, grants, audit log (plan §8). Every change is audited.

Users, roles and grants need `manage_users`; the audit log needs `view_audit`.
Safety rails: a change that would leave no active user with `manage_users` is
refused, and admins can't deactivate themselves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import CurrentUser, get_db, require_global
from app.config import get_settings
from app.db.models import AuditEvent, Grant, RefreshToken, Role, Space, User
from app.identity import (
    active_admin_count,
    create_user,
    issue_invite,
    roles_by_name,
)
from app.policy.engine import GLOBAL_ACTIONS, SPACE_ACTIONS, GrantError, validate_grant
from app.vault.labels import vault_config

router = APIRouter(prefix="/admin", tags=["admin"])
manage_users = require_global("manage_users")
view_audit = require_global("view_audit")
manage_spaces = require_global("manage_spaces")

Sensitivity = Literal["public", "internal", "restricted"]
ROLE_NAME = r"^[a-z][a-z0-9-]{1,63}$"


# --- schemas -----------------------------------------------------------------


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    home_space: str | None
    roles: list[str]
    is_active: bool
    totp_enabled: bool
    invite_pending: bool
    locked: bool
    created_at: datetime
    last_login_at: datetime | None
    leaving_on: date | None = None


class UserCreateIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    roles: list[str] = Field(default_factory=lambda: ["employee"])
    home_space: str | None = None


class InviteOut(BaseModel):
    user: UserOut
    invite_token: str  # shown once; give it to the person (no email in v1)
    expires_in_hours: int


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    roles: list[str] | None = None
    home_space: str | None = None
    is_active: bool | None = None
    leaving_on: date | None = None  # last working day (bus-factor report)


class GrantIn(BaseModel):
    space: str | None
    max_sensitivity: Sensitivity = "public"
    actions: list[str] = Field(min_length=1)


class GrantOut(GrantIn):
    id: str


class RoleOut(BaseModel):
    id: str
    name: str
    description: str
    grants: list[GrantOut]
    user_count: int


class RoleCreateIn(BaseModel):
    name: str = Field(pattern=ROLE_NAME)
    description: str = ""
    grants: list[GrantIn] = Field(default_factory=list)


class RoleUpdateIn(BaseModel):
    description: str


class AuditOut(BaseModel):
    id: int
    ts: datetime
    actor_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict


class SpaceOption(BaseModel):
    name: str
    title: str


class OptionsOut(BaseModel):
    """What the admin screens can offer when editing grants (labels only, no content)."""

    spaces: list[SpaceOption]
    space_actions: list[str]
    global_actions: list[str]
    sensitivities: list[Sensitivity]


class ChainOut(BaseModel):
    ok: bool
    events: int
    first_bad_id: int | None


# --- helpers -----------------------------------------------------------------


def _user_out(u: User) -> UserOut:
    now = datetime.now(UTC)
    return UserOut(
        id=str(u.id),
        email=u.email,
        display_name=u.display_name,
        home_space=u.home_space,
        roles=sorted(r.name for r in u.roles),
        is_active=u.is_active,
        totp_enabled=u.totp_enabled,
        invite_pending=u.password_hash is None,
        locked=u.locked_until is not None and u.locked_until > now,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
        leaving_on=u.leaving_on,
    )


async def _role_out(session: AsyncSession, r: Role) -> RoleOut:
    users = (await session.execute(select(User))).scalars().all()
    return RoleOut(
        id=str(r.id),
        name=r.name,
        description=r.description,
        grants=[
            GrantOut(
                id=str(g.id),
                space=g.space,
                max_sensitivity=g.max_sensitivity,
                actions=sorted(g.actions),
            )
            for g in r.grants
        ],
        user_count=sum(1 for u in users if r in u.roles),
    )


async def _space_names(session: AsyncSession) -> list[str]:
    return list((await session.execute(select(Space.name))).scalars())


async def _check_space(session: AsyncSession, space: str | None) -> None:
    if space is not None and space not in await _space_names(session):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown space {space!r}")


async def _keep_an_admin(session: AsyncSession) -> None:
    await session.flush()
    if await active_admin_count(session) == 0:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this would leave no active user who can manage users"
        )


async def _load_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


async def _load_role(session: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    return role


async def _revoke_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def _grant(g: GrantIn, spaces: list[str]) -> Grant:
    try:
        rule = validate_grant(g.space, g.max_sensitivity, g.actions, spaces)
    except GrantError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return Grant(
        space=rule.space, max_sensitivity=rule.max_sensitivity.label, actions=sorted(rule.actions)
    )


# --- options -----------------------------------------------------------------


@router.get("/options", response_model=OptionsOut)
async def options(
    _: CurrentUser = Depends(manage_users), session: AsyncSession = Depends(get_db)
) -> OptionsOut:
    """Every space, even ones the admin can't read: grants are given for them."""
    spaces = (await session.execute(select(Space).order_by(Space.name))).scalars().all()
    return OptionsOut(
        spaces=[SpaceOption(name=sp.name, title=sp.title) for sp in spaces],
        space_actions=sorted(SPACE_ACTIONS),
        global_actions=sorted(GLOBAL_ACTIONS),
        sensitivities=["public", "internal", "restricted"],
    )


# --- departments -------------------------------------------------------------


class DepartmentOut(BaseModel):
    name: str
    title: str
    description: str
    contact: str
    folders: list[str]
    created_in_app: bool
    roles: list[str]


class DepartmentIn(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=1000)
    contact: str = Field(default="", max_length=200)
    name: str | None = Field(default=None, max_length=31)
    folder: str | None = Field(default=None, max_length=60)


async def _departments(session: AsyncSession) -> list[DepartmentOut]:
    from app.spaces import space_files

    rows = {sp.name: sp for sp in (await session.execute(select(Space))).scalars()}
    roles = (await session.execute(select(Role))).scalars().all()
    rules: dict[str, list[str]] = {}
    for r in vault_config().folder_rules:
        rules.setdefault(r.space, []).append(r.path.strip("/"))
    out = []
    for name, raw in space_files():
        if name not in rows:
            continue
        out.append(
            DepartmentOut(
                name=name,
                title=rows[name].title,
                description=" ".join(str(raw.get("description") or "").split()),
                contact=str(raw.get("contact") or ""),
                folders=sorted(rules.get(name, [])),
                created_in_app=bool(raw.get("created_in_app")),
                roles=sorted(
                    r.name
                    for r in roles
                    if r.name != "employee" and any(g.space == name for g in r.grants)
                ),
            )
        )
    return sorted(out, key=lambda d: d.title.lower())


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    _: CurrentUser = Depends(manage_spaces), session: AsyncSession = Depends(get_db)
) -> list[DepartmentOut]:
    return await _departments(session)


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department_endpoint(
    body: DepartmentIn,
    me: CurrentUser = Depends(manage_spaces),
    session: AsyncSession = Depends(get_db),
) -> DepartmentOut:
    """A new department with its staff and lead roles (nobody has them yet)."""
    from app.departments import DepartmentError, create_department

    try:
        space = await create_department(session, actor_id=me.user.id, **body.model_dump())
    except DepartmentError as exc:
        code = status.HTTP_409_CONFLICT if exc.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(code, str(exc)) from None
    return next(d for d in await _departments(session) if d.name == space.name)


# --- users -------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: CurrentUser = Depends(manage_users), session: AsyncSession = Depends(get_db)
) -> list[UserOut]:
    users = (await session.execute(select(User).order_by(User.display_name))).scalars().all()
    return [_user_out(u) for u in users]


@router.post("/users", response_model=InviteOut, status_code=201)
async def create(
    body: UserCreateIn,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> InviteOut:
    await _check_space(session, body.home_space)
    try:
        user, token = await create_user(
            session,
            email=body.email,
            display_name=body.display_name,
            role_names=body.roles,
            home_space=body.home_space,
            actor_id=me.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await session.commit()
    return InviteOut(
        user=_user_out(user), invite_token=token, expires_in_hours=get_settings().invite_hours
    )


@router.get("/users/{user_id}", response_model=UserOut)
async def get_one(
    user_id: uuid.UUID,
    _: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    return _user_out(await _load_user(session, user_id))


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateIn,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await _load_user(session, user_id)
    changed: dict = {}
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
        changed["display_name"] = True
    if "home_space" in body.model_fields_set:
        await _check_space(session, body.home_space)
        user.home_space = body.home_space
        changed["home_space"] = body.home_space
    if body.roles is not None:
        try:
            new_roles = await roles_by_name(session, body.roles)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        before = {r.name for r in user.roles}
        if user.id == me.user.id and set(body.roles) - before:
            # Two-person rule: managing users must not open content to yourself.
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "another administrator must add roles to your account"
            )
        user.roles = new_roles
        after = set(body.roles)
        changed["roles_added"] = sorted(after - before)
        changed["roles_removed"] = sorted(before - after)
    if "leaving_on" in body.model_fields_set:
        user.leaving_on = body.leaving_on
        changed["leaving_on"] = body.leaving_on.isoformat() if body.leaving_on else None
    if body.is_active is not None and body.is_active != user.is_active:
        if user.id == me.user.id and not body.is_active:
            raise HTTPException(status.HTTP_409_CONFLICT, "you can't deactivate yourself")
        user.is_active = body.is_active
        changed["is_active"] = body.is_active
        if not body.is_active:
            await _revoke_sessions(session, user.id)
    await _keep_an_admin(session)
    await audit.record(
        session,
        "user_updated",
        actor_id=me.user.id,
        target_type="user",
        target_id=user.id,
        details=changed,
    )
    await session.commit()
    return _user_out(user)


@router.post("/users/{user_id}/invite", response_model=InviteOut)
async def reinvite(
    user_id: uuid.UUID,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> InviteOut:
    """New set-password link (also used as a password reset). The old password stops working."""
    user = await _load_user(session, user_id)
    user.password_hash = None
    await _revoke_sessions(session, user.id)
    token = await issue_invite(session, user)
    await audit.record(
        session, "invite_issued", actor_id=me.user.id, target_type="user", target_id=user.id
    )
    await session.commit()
    return InviteOut(
        user=_user_out(user), invite_token=token, expires_in_hours=get_settings().invite_hours
    )


@router.post("/users/{user_id}/reset-totp", response_model=UserOut)
async def reset_totp(
    user_id: uuid.UUID,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    """For a lost phone: the user sets up two-factor again at next sign-in."""
    user = await _load_user(session, user_id)
    user.totp_enabled, user.totp_secret_enc, user.totp_last_step = False, None, None
    await _revoke_sessions(session, user.id)
    await audit.record(
        session, "totp_reset", actor_id=me.user.id, target_type="user", target_id=user.id
    )
    await session.commit()
    return _user_out(user)


@router.post("/users/{user_id}/unlock", response_model=UserOut)
async def unlock(
    user_id: uuid.UUID,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await _load_user(session, user_id)
    user.locked_until, user.failed_logins = None, 0
    await audit.record(
        session, "user_unlocked", actor_id=me.user.id, target_type="user", target_id=user.id
    )
    await session.commit()
    return _user_out(user)


# --- roles and grants --------------------------------------------------------


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    _: CurrentUser = Depends(manage_users), session: AsyncSession = Depends(get_db)
) -> list[RoleOut]:
    roles = (await session.execute(select(Role).order_by(Role.name))).scalars().all()
    return [await _role_out(session, r) for r in roles]


@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role(
    body: RoleCreateIn,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> RoleOut:
    if (await session.execute(select(Role).where(Role.name == body.name))).scalar():
        raise HTTPException(status.HTTP_409_CONFLICT, "a role with this name exists")
    spaces = await _space_names(session)
    role = Role(
        name=body.name,
        description=body.description,
        grants=[_grant(g, spaces) for g in body.grants],
    )
    session.add(role)
    await session.flush()
    await audit.record(
        session,
        "role_created",
        actor_id=me.user.id,
        target_type="role",
        target_id=role.id,
        details={"name": role.name, "grants": len(role.grants)},
    )
    await session.commit()
    return await _role_out(session, role)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdateIn,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> RoleOut:
    role = await _load_role(session, role_id)
    role.description = body.description
    await audit.record(
        session, "role_updated", actor_id=me.user.id, target_type="role", target_id=role.id
    )
    await session.commit()
    return await _role_out(session, role)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> None:
    role = await _load_role(session, role_id)
    name = role.name
    for u in (await session.execute(select(User))).scalars().all():
        if role in u.roles:
            u.roles.remove(role)
    await session.delete(role)
    await _keep_an_admin(session)
    await audit.record(
        session,
        "role_deleted",
        actor_id=me.user.id,
        target_type="role",
        target_id=role_id,
        details={"name": name},
    )
    await session.commit()


@router.post("/roles/{role_id}/grants", response_model=RoleOut, status_code=201)
async def add_grant(
    role_id: uuid.UUID,
    body: GrantIn,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> RoleOut:
    role = await _load_role(session, role_id)
    if role.name in me.principal.roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "another administrator must change a role you hold"
        )
    grant = _grant(body, await _space_names(session))
    role.grants.append(grant)
    await session.flush()
    await audit.record(
        session,
        "grant_added",
        actor_id=me.user.id,
        target_type="role",
        target_id=role.id,
        details={
            "space": grant.space,
            "max_sensitivity": grant.max_sensitivity,
            "actions": grant.actions,
        },
    )
    await session.commit()
    return await _role_out(session, role)


@router.delete("/grants/{grant_id}", status_code=204)
async def delete_grant(
    grant_id: uuid.UUID,
    me: CurrentUser = Depends(manage_users),
    session: AsyncSession = Depends(get_db),
) -> None:
    grant = await session.get(Grant, grant_id)
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grant not found")
    role = grant.role
    details = {
        "space": grant.space,
        "max_sensitivity": grant.max_sensitivity,
        "actions": list(grant.actions),
    }
    role.grants.remove(grant)
    await _keep_an_admin(session)
    await audit.record(
        session,
        "grant_removed",
        actor_id=me.user.id,
        target_type="role",
        target_id=role.id,
        details=details,
    )
    await session.commit()


# --- audit log ---------------------------------------------------------------


@router.get("/audit", response_model=list[AuditOut])
async def list_audit(
    me: CurrentUser = Depends(view_audit),
    session: AsyncSession = Depends(get_db),
    action: str | None = Query(default=None, max_length=64),
    actor_id: uuid.UUID | None = None,
    target_id: str | None = Query(default=None, max_length=64),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AuditOut]:
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if action:
        q = q.where(AuditEvent.action == action)
    if actor_id:
        q = q.where(AuditEvent.actor_id == actor_id)
    if target_id:
        q = q.where(AuditEvent.target_id == target_id)
    if since:
        q = q.where(AuditEvent.ts >= since)
    if until:
        q = q.where(AuditEvent.ts < until)
    rows = (await session.execute(q)).scalars().all()
    out = [
        AuditOut(
            id=e.id,
            ts=e.ts,
            actor_id=str(e.actor_id) if e.actor_id else None,
            action=e.action,
            target_type=e.target_type,
            target_id=e.target_id,
            details=e.details or {},
        )
        for e in rows
    ]
    # Looking at the audit log is itself audited (plan §11).
    await audit.record(
        session,
        "audit_viewed",
        actor_id=me.user.id,
        details={"filter_action": action, "returned": len(out)},
    )
    await session.commit()
    return out


@router.get("/audit/verify", response_model=ChainOut)
async def verify_audit(
    me: CurrentUser = Depends(view_audit), session: AsyncSession = Depends(get_db)
) -> ChainOut:
    events = (await session.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
    from app.db.models import VaultState

    anchor = await session.get(VaultState, audit.ANCHOR_KEY)
    ok, bad = audit.verify_chain(events, anchor.value if anchor else audit.GENESIS)
    await audit.record(
        session, "audit_verified", actor_id=me.user.id, details={"ok": ok, "events": len(events)}
    )
    await session.commit()
    return ChainOut(ok=ok, events=len(events), first_bad_id=bad)
