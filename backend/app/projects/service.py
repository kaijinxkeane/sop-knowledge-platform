"""Project spaces (plan §4): who can read what through a project.

A project has its own space (`p-<slug>`, notes under `Projects/<slug>/`), a
project lead, members, and shares of department spaces. Access is worked out
on every request from the project rows (like roles), so it takes effect and
ends at once, with no clean-up job:

While the project is active (start <= today <= end, not closed):
- members: ask + contribute + review on the project space, up to restricted
  (they need the key details and each other's drafts); only the project lead
  approves its notes
- each *approved* share, until its `approved_until`: the whole department space
  (ask, at the level its lead chose: internal unless they picked restricted),
  or selected folders/SOPs (a PartialShare, checked by RLS and the policy
  engine with the safeguard floor). Read-only, published SOPs only.
After it ends (or is closed):
- members: read-only, internal level, approved notes only, on the project
  space (authors keep their own notes, as everywhere): restricted notes
  and anything a safeguard flags (client names, pricing, contracts, personal
  data) are hidden; department shares stop
- the project lead keeps read-only access at restricted
Always: leads of the departments the project asked to share from can read the
project space (read-only), so they know what they're sharing into.

Nobody can share a department without that department's lead, and creating a
project grants nothing by itself (red-team rule, 2026-11-22).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db.models import Project, ProjectMember, ProjectShare, User
from app.policy.engine import GrantRule, PartialShare, Principal, Sensitivity, resolve_sensitivity
from app.spaces import SpaceProfile

READ = frozenset({"ask"})
WRITE = frozenset({"ask", "contribute", "review"})  # members see each other's drafts
LEAD = frozenset({"ask", "contribute", "review", "approve"})


def share_valid(share: ProjectShare, today: date) -> bool:
    return (
        share.status == "approved"
        and share.approved_until is not None
        and today <= share.approved_until
    )


def share_grants(share: ProjectShare) -> tuple[list[GrantRule], list[PartialShare]]:
    level = resolve_sensitivity(share.max_sensitivity)
    if share.scope == "space":
        return [GrantRule(share.space, level, READ)], []
    return [], [
        PartialShare(
            share.space,
            level,
            folders=tuple(str(f) for f in share.folders or ()),
            documents=tuple(str(d) for d in share.documents or ()),
        )
    ]


async def project_access(
    s: AsyncSession, user: User, base: Principal, today: date | None = None
) -> tuple[list[GrantRule], list[PartialShare]]:
    today = today or clock.today()
    if user.leaving_on is not None and user.leaving_on < today:
        return [], []
    approves = [sp for sp, acts in base.space_actions().items() if "approve" in acts]
    member_of = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    conds = [Project.lead_id == user.id, Project.id.in_(member_of)]
    if approves:
        conds.append(
            Project.id.in_(
                select(ProjectShare.project_id).where(
                    ProjectShare.space.in_(approves),
                    ProjectShare.status.in_(("requested", "approved")),
                )
            )
        )
    projects = (await s.execute(select(Project).where(or_(*conds)))).scalars().all()
    grants: list[GrantRule] = []
    partial: list[PartialShare] = []
    for p in projects:
        is_lead = p.lead_id == user.id
        is_member = is_lead or any(m.user_id == user.id for m in p.members)
        active = p.active(today)
        if is_member and active:
            grants.append(GrantRule(p.space, Sensitivity.RESTRICTED, LEAD if is_lead else WRITE))
            for share in p.shares:
                if share_valid(share, today):
                    g, ps = share_grants(share)
                    grants += g
                    partial += ps
        elif is_member:
            level = Sensitivity.RESTRICTED if is_lead else Sensitivity.INTERNAL
            grants.append(GrantRule(p.space, level, READ))
        if any(sh.space in approves and sh.status in ("requested", "approved") for sh in p.shares):
            grants.append(GrantRule(p.space, Sensitivity.RESTRICTED, READ))
    return grants, partial


async def principal_with_projects(
    s: AsyncSession, user: User, base: Principal, today: date | None = None
) -> Principal:
    grants, partial = await project_access(s, user, base, today)
    if not grants and not partial:
        return base
    return Principal(
        user_id=base.user_id,
        roles=base.roles,
        grants=base.grants + tuple(grants),
        partial=base.partial + tuple(partial),
    )


async def project_profiles(s: AsyncSession) -> dict[str, SpaceProfile]:
    """Chat profiles for project spaces. Always local-only: a project can hold
    material from several departments, including local-only ones."""
    rows = (await s.execute(select(Project))).scalars().all()
    return {
        p.space: SpaceProfile(
            name=p.space,
            title=p.name,
            description=f"Project notes for {p.name}",
            contact="Ask the project lead.",
            local_only=True,
        )
        for p in rows
    }


async def ending_reminders(s: AsyncSession, reminder_days: int, today: date | None = None) -> int:
    """One quiet reminder to the project lead before the project (and its
    sharing) ends."""
    from app.governance.notify import notify

    today = today or clock.today()
    n = 0
    for p in (await s.execute(select(Project).where(Project.closed_at.is_(None)))).scalars():
        left = (p.ends_on - today).days
        if 0 <= left <= reminder_days:
            n += await notify(
                s,
                [p.lead_id],
                "project_ending",
                ref_id=str(p.id),
                dedupe=f"project_ending:{p.id}:{p.ends_on.isoformat()}",
            )
    return n
