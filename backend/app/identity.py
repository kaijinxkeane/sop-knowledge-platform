"""Users, roles, grants and the staff notice: logic shared by the API and the CLI."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.config import get_settings
from app.db.models import Grant, OneTimeToken, Role, Space, User
from app.models.config import load_gateway_config
from app.policy.engine import GrantRule, Principal, validate_grant
from app.security.tokens import new_opaque_token

ADMIN_ACTION = "manage_users"


def normalise_email(email: str) -> str:
    return email.strip().lower()


# --- configuration -----------------------------------------------------------


def configured_spaces(config_dir: Path | None = None) -> dict[str, tuple[str, bool]]:
    cfg = load_gateway_config(
        config_dir or get_settings().config_dir, {"OLLAMA_BASE_URL": "http://unused"}
    )
    return {name: (s.title, s.local_only) for name, s in cfg.spaces.items()}


def load_roles_config(config_dir: Path | None = None) -> dict[str, dict]:
    path = (config_dir or get_settings().config_dir) / "roles.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    roles = data.get("roles") or {}
    spaces = configured_spaces(config_dir)
    for name, role in roles.items():
        for g in role.get("grants") or []:
            validate_grant(
                g.get("space"), g.get("max_sensitivity", "public"), g.get("actions") or [], spaces
            )
        role.setdefault("description", "")
        role.setdefault("grants", [])
        roles[name] = role
    return roles


async def sync_spaces(session: AsyncSession, config_dir: Path | None = None) -> list[str]:
    changed = []
    for name, (title, local_only) in configured_spaces(config_dir).items():
        space = await session.get(Space, name)
        if space is None:
            session.add(Space(name=name, title=title, local_only=local_only))
            changed.append(name)
        elif (space.title, space.local_only) != (title, local_only):
            space.title, space.local_only = title, local_only
            changed.append(name)
    await session.flush()
    return changed


async def sync_roles(
    session: AsyncSession, *, reset: bool = False, config_dir: Path | None = None
) -> list[str]:
    """Create missing roles from config/roles.yaml. With reset, overwrite their grants."""
    created = []
    for name, spec in load_roles_config(config_dir).items():
        role = (await session.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
        if role is not None and not reset:
            continue
        if role is None:
            role = Role(name=name, description=spec["description"])
            session.add(role)
            created.append(name)
        role.description = spec["description"]
        role.grants.clear()
        for g in spec["grants"]:
            role.grants.append(
                Grant(
                    space=g.get("space"),
                    max_sensitivity=g.get("max_sensitivity", "public"),
                    actions=list(g["actions"]),
                )
            )
    await session.flush()
    return created


# --- principals --------------------------------------------------------------


def principal_for(user: User) -> Principal:
    rules = []
    for role in user.roles:
        for g in role.grants:
            try:
                rules.append(
                    validate_grant(
                        g.space, g.max_sensitivity, g.actions, [g.space] if g.space else []
                    )
                )
            except ValueError:
                continue  # a malformed stored grant grants nothing
    return Principal(
        user_id=user.id, roles=frozenset(r.name for r in user.roles), grants=tuple(rules)
    )


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == normalise_email(email)))
    ).scalar_one_or_none()


async def roles_by_name(session: AsyncSession, names: list[str]) -> list[Role]:
    if not names:
        return []
    found = (await session.execute(select(Role).where(Role.name.in_(names)))).scalars().all()
    missing = set(names) - {r.name for r in found}
    if missing:
        raise ValueError(f"unknown roles: {sorted(missing)}")
    return list(found)


async def active_admin_count(session: AsyncSession, *, excluding: uuid.UUID | None = None) -> int:
    users = (await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    return sum(1 for u in users if u.id != excluding and principal_for(u).can(ADMIN_ACTION))


# --- invites -----------------------------------------------------------------


async def issue_invite(session: AsyncSession, user: User) -> str:
    """A one-time link token to set a password. Previous unused ones stop working."""
    now = datetime.now(UTC)
    old = (
        (
            await session.execute(
                select(OneTimeToken).where(
                    OneTimeToken.user_id == user.id, OneTimeToken.used_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for t in old:
        t.used_at = now
    token, digest = new_opaque_token()
    session.add(
        OneTimeToken(
            user_id=user.id,
            purpose="invite",
            token_hash=digest,
            expires_at=now + timedelta(hours=get_settings().invite_hours),
        )
    )
    await session.flush()
    return token


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    role_names: list[str],
    home_space: str | None,
    actor_id: uuid.UUID | None,
) -> tuple[User, str]:
    email = normalise_email(email)
    if await get_user_by_email(session, email):
        raise ValueError("a user with this email already exists")
    user = User(
        email=email,
        display_name=display_name.strip(),
        home_space=home_space,
        roles=await roles_by_name(session, role_names),
    )
    session.add(user)
    await session.flush()
    token = await issue_invite(session, user)
    await audit.record(
        session,
        "user_created",
        actor_id=actor_id,
        target_type="user",
        target_id=user.id,
        details={"roles": sorted(role_names)},
    )
    return user, token


# --- staff notice ------------------------------------------------------------


@dataclass(frozen=True)
class Notice:
    version: str
    markdown: str


def load_notice(config_dir: Path | None = None) -> Notice:
    from wiki_core import parse_frontmatter_block, split_markdown_frontmatter

    raw = ((config_dir or get_settings().config_dir) / "notice.md").read_text(encoding="utf-8")
    split = split_markdown_frontmatter(raw)
    if not split:
        raise ValueError("config/notice.md needs frontmatter with a version")
    meta = parse_frontmatter_block(split[0])
    version = str(meta.get("version") or "").strip()
    if not version:
        raise ValueError("config/notice.md needs a version")
    return Notice(version=version, markdown=split[1].strip())


async def count_users(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(User))).scalar_one()


__all__ = ["GrantRule"]
