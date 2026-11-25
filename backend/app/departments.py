"""Create a department (space) from the app: Admin → Departments (manage_spaces).

A department is the same thing as a configured one in config/spaces/, kept as
a YAML file in `settings.spaces_dir`, plus:

- a `spaces` row, so grants can name it;
- two roles, `<name>-staff` (internal: ask, contribute) and `<name>-lead`
  (restricted: ask, contribute, review, approve). Nobody gets them yet: people
  are given roles in Admin → Users, where the two-person rule applies;
- a public `ask` grant on `employee`, like every other department;
- a folder rule (`<Folder>/` → the department, internal), so notes added in
  Obsidian land there too. Nothing is readable until someone writes it.

Nothing is ever loosened or deleted here, and a configured department is never
overridden.
"""

from __future__ import annotations

import os
import re
import tempfile

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.config import get_settings
from app.db.models import Grant, Role, Space
from app.identity import load_roles_config
from app.models.types import UNCLASSIFIED
from app.spaces import space_files
from app.vault.labels import vault_config

NAME = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
FOLDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &'()_-]{0,59}$")
RESERVED = {
    UNCLASSIFIED,
    "unclassified",
    "global",
    "admin",
    "all",
    "none",
    "help",
    "drafts",
    "inbox",
}


class DepartmentError(ValueError):
    def __init__(self, message: str, *, conflict: bool = False):
        super().__init__(message)
        self.conflict = conflict


def suggested_name(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:31]


async def create_department(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    contact: str,
    name: str | None = None,
    folder: str | None = None,
    actor_id=None,
) -> Space:
    title = " ".join(title.split())
    name = (name or suggested_name(title)).strip().lower()
    folder = " ".join((folder or title).split()).strip("/")
    if not title or not description.strip():
        raise DepartmentError("a department needs a name and a description")
    if not NAME.match(name) or name in RESERVED:
        raise DepartmentError("use 2-31 lowercase letters, digits or dashes for the short name")
    if not FOLDER.match(folder):
        raise DepartmentError("the folder name can't contain slashes or start with a dot")

    in_db = set((await session.execute(select(Space.name))).scalars())
    known = {n for n, _ in space_files()} | in_db
    if name in known:
        raise DepartmentError("a department with this short name exists", conflict=True)
    cfg = vault_config()
    taken = {r.path.strip("/").lower() for r in cfg.folder_rules} | {
        cfg.handover_folder.lower(),
        cfg.project_folder.lower(),
        cfg.attachments_folder.lower(),
        "help",
        "drafts",
        "inbox",
    }
    if folder.lower() in taken:
        raise DepartmentError("that folder already belongs to something else", conflict=True)
    roles = {f"{name}-staff", f"{name}-lead"}
    if (await session.execute(select(func.count()).where(Role.name.in_(roles)))).scalar():
        raise DepartmentError("roles with this department's names exist", conflict=True)

    space = Space(name=name, title=title, local_only=False)
    session.add(space)
    await session.flush()
    session.add_all(
        [
            Role(
                name=f"{name}-staff",
                description=f"{title} team members.",
                grants=[
                    Grant(space=name, max_sensitivity="internal", actions=["ask", "contribute"])
                ],
            ),
            Role(
                name=f"{name}-lead",
                description=(
                    f"Leads {title}: approves its SOPs and sees restricted {title} material."
                ),
                grants=[
                    Grant(
                        space=name,
                        max_sensitivity="restricted",
                        actions=["approve", "ask", "contribute", "review"],
                    )
                ],
            ),
        ]
    )
    employee = (await session.execute(select(Role).where(Role.name == "employee"))).scalar()
    if employee is not None:
        employee.grants.append(Grant(space=name, max_sensitivity="public", actions=["ask"]))
    # Roles that work in every department (e.g. the CEO: `new_departments` in roles.yaml).
    for role_name, spec in load_roles_config().items():
        extra = spec.get("new_departments")
        role = (await session.execute(select(Role).where(Role.name == role_name))).scalar()
        if extra and role is not None:
            role.grants.append(
                Grant(
                    space=name,
                    max_sensitivity=extra.get("max_sensitivity", "public"),
                    actions=list(extra.get("actions") or []),
                )
            )
    await session.flush()
    await audit.record(
        session,
        "space_created",
        actor_id=actor_id,
        target_type="space",
        target_id=name,
        details={"roles": 2},
    )

    path = _write_file(
        name,
        {
            "name": name,
            "title": title,
            "local_only": False,
            "description": " ".join(description.split()),
            "contact": " ".join(contact.split()) or f"Please contact {title}.",
            "folder": folder,
            "agent": {
                "persona": f"You are the {title} team's assistant. You explain its SOPs accurately."
            },
        },
    )
    try:
        await session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return space


def _write_file(name: str, data: dict):
    folder = get_settings().spaces_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.yaml"
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".new-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("# Created in the app (Admin → Departments), shaped like config/spaces/.\n")
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)
    return path
