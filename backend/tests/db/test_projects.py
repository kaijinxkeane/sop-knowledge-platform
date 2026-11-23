"""Project spaces: cross-department projects, lead-approved sharing, expiry."""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from sqlalchemy import select, text

from app.agents.concierge import retrieve
from app.db.models import Document, Notification, Project
from app.db.scoped import apply_reader_scope, visible
from app.identity import get_user, principal_for
from app.projects.service import ending_reminders, principal_with_projects, project_profiles
from app.spaces import space_profiles
from tests.db.conftest import fake_query

API = "/api/v1"
STAFF = ("employee", "core-staff")
CORE_LEAD = ("employee", "core-lead")
HR_LEAD = ("employee", "hr-staff", "hr-lead")
ONBOARDING = "HR/New Hire Onboarding Checklist.md"
DISCIPLINARY = "HR/Disciplinary Process.md"


async def doc_id(sessions, path) -> str:
    async with sessions() as s:
        return str(
            (await s.execute(select(Document.id).where(Document.vault_path == path))).scalar_one()
        )


async def principal(sessions, person):
    async with sessions() as s:
        user = await get_user(s, person.user.id)
        return await principal_with_projects(s, user, principal_for(user))


async def setup(client, make_user, sign_in, shares=("hr",)):
    lead, member, other = (
        await make_user(roles=CORE_LEAD),
        await make_user(roles=STAFF),
        await make_user(roles=STAFF),
    )
    hr = await make_user(roles=HR_LEAD)
    h = {p: await sign_in(p) for p in (lead, member, other, hr)}
    r = await client.post(
        f"{API}/projects",
        headers=h[lead],
        json={
            "name": "Leadership Offsite 2027",
            "ends_on": (date.today() + timedelta(days=90)).isoformat(),
            "members": [str(member.user.id)],
            "shares": [{"space": s, "note": "onboarding steps for new trainers"} for s in shares],
        },
    )
    assert r.status_code == 201, r.text
    return r.json(), lead, member, other, hr, h


async def test_only_space_leads_create_and_six_months_max(indexed, client, make_user, sign_in):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=CORE_LEAD)
    body = {"name": "Offsite", "ends_on": (date.today() + timedelta(days=30)).isoformat()}
    assert (
        await client.post(f"{API}/projects", headers=await sign_in(staff), json=body)
    ).status_code == 403
    hl = await sign_in(lead)
    late = body | {"ends_on": (date.today() + timedelta(days=200)).isoformat()}
    assert (await client.post(f"{API}/projects", headers=hl, json=late)).status_code == 422
    r = await client.post(
        f"{API}/projects", headers=hl, json=body | {"lead_id": str(staff.user.id)}
    )
    assert r.status_code == 201
    p = r.json()
    assert p["space"] == "p-offsite" and p["folder"] == "Projects/offsite"
    assert p["lead"]["id"] == str(staff.user.id) and p["my_role"] == "creator"


async def test_project_notes_and_members(indexed, sessions, client, make_user, sign_in):
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in, shares=())
    r = await client.post(
        f"{API}/notes",
        headers=h[member],
        json={
            "title": "Venue options",
            "space": p["space"],
            "sensitivity": "restricted",
            "body": "# Venue\n\nShortlist and quotes.",
            "folder": "Drafts/core",
        },
    )
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["vault_path"].startswith("Projects/leadership-offsite-2027/")
    async with sessions() as s:
        d = await s.get(Document, uuid.UUID(note["id"]))
        assert {a.space for a in d.access} == {p["space"]}
    # members read restricted project notes while it's active; others don't
    assert (await client.get(f"{API}/documents/{note['id']}", headers=h[lead])).status_code == 200
    assert (await client.get(f"{API}/documents/{note['id']}", headers=h[other])).status_code == 404
    assert (await client.get(f"{API}/projects/{p['id']}", headers=h[other])).status_code == 404
    # the project lead manages members; nobody else does
    r = await client.post(
        f"{API}/projects/{p['id']}/members",
        headers=h[member],
        json={"user_ids": [str(other.user.id)]},
    )
    assert r.status_code == 403


async def test_nothing_is_shared_until_that_departments_lead_approves(
    indexed, sessions, client, make_user, sign_in
):
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in)
    onboarding = await doc_id(sessions, ONBOARDING)
    share = p["shares"][0]
    assert share["status"] == "requested" and not share["in_force"]
    assert (await client.get(f"{API}/documents/{onboarding}", headers=h[member])).status_code == 404
    # the core lead who made the project can't approve HR's share; HR's lead can
    r = await client.post(
        f"{API}/project-shares/{share['id']}/approve", headers=h[lead], json={"scope": "space"}
    )
    assert r.status_code == 404
    reqs = (await client.get(f"{API}/project-shares", headers=h[hr])).json()
    assert [x["id"] for x in reqs] == [share["id"]]
    async with sessions() as s:
        n = (
            (await s.execute(select(Notification).where(Notification.user_id == hr.user.id)))
            .scalars()
            .all()
        )
        assert [x.kind for x in n] == ["project_share_requested"]
    r = await client.post(
        f"{API}/project-shares/{share['id']}/approve", headers=h[hr], json={"scope": "space"}
    )
    assert r.status_code == 200, r.text
    dis = await doc_id(sessions, DISCIPLINARY)
    assert (await client.get(f"{API}/documents/{onboarding}", headers=h[member])).status_code == 200
    assert (await client.get(f"{API}/documents/{dis}", headers=h[member])).status_code == 404
    assert (await client.get(f"{API}/documents/{onboarding}", headers=h[other])).status_code == 404
    # read-only: no editing HR's SOPs through a project
    src = await client.get(f"{API}/notes/{onboarding}/source", headers=h[member])
    r = await client.put(
        f"{API}/notes/{onboarding}",
        headers=h[member],
        json={"base_version": src.json()["version"], "content": src.json()["content"] + "x"},
    )
    assert r.status_code == 403
    # HR's lead can stop it at any time, at once
    assert (
        await client.post(f"{API}/project-shares/{share['id']}/revoke", headers=h[hr])
    ).status_code == 200
    assert (await client.get(f"{API}/documents/{onboarding}", headers=h[member])).status_code == 404


async def test_selected_sops_only_and_rls_agrees(indexed, sessions, client, make_user, sign_in):
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in)
    onboarding, dis = await doc_id(sessions, ONBOARDING), await doc_id(sessions, DISCIPLINARY)
    # an HR internal SOP that is *not* selected
    r = await client.post(
        f"{API}/notes",
        headers=h[hr],
        json={"title": "Payroll Calendar", "space": "hr", "body": "# Payroll\n\nRuns on the 25th."},
    )
    payroll = r.json()["id"]
    review = (await client.post(f"{API}/notes/{payroll}/submit", headers=h[hr])).json()
    assert (
        await client.post(f"{API}/reviews/{review['id']}/approve", headers=h[hr], json={})
    ).status_code == 200
    share = p["shares"][0]
    r = await client.post(
        f"{API}/project-shares/{share['id']}/approve",
        headers=h[hr],
        # one SOP by id, and a folder that holds the restricted Disciplinary Process
        json={"scope": "selected", "document_ids": [onboarding], "folders": ["HR/Disciplinary"]},
    )
    assert r.status_code == 200, r.text
    member_p = await principal(sessions, member)
    expect = {onboarding: True, payroll: False, dis: False}
    for d, want in expect.items():
        async with sessions() as s:
            doc = await s.get(Document, uuid.UUID(d))
            py = visible(member_p, doc)
            await apply_reader_scope(s, member_p)
            sql = await s.scalar(text("SELECT sop_doc_visible(:d)"), {"d": d})
        assert (py, sql) == (want, want), (d, py, sql)
    r = await client.get(f"{API}/documents", headers=h[member], params={"space": "hr"})
    titles = {x["title"] for x in r.json()}
    assert "New Hire Onboarding Checklist" in titles and "Payroll Calendar" not in titles
    # chat can use the shared SOP (HR stays local-only through the gateway's rules)
    _, per_space = await retrieve(
        sessions,
        member_p,
        "new hire onboarding checklist",
        await fake_query("new hire onboarding"),
        space_profiles(),
        None,
    )
    got = {str(x.document_id) for hs in per_space.values() for x in hs}
    assert onboarding in got and not got & {payroll, dis}


async def test_after_expiry_key_details_and_shares_close(
    indexed, sessions, client, make_user, sign_in
):
    """Notes written by someone else; an author always keeps their own notes."""
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in)
    onboarding = await doc_id(sessions, ONBOARDING)
    share = p["shares"][0]
    await client.post(
        f"{API}/project-shares/{share['id']}/approve", headers=h[hr], json={"scope": "space"}
    )
    notes = {}
    for title, level in (("Agenda", "internal"), ("Client budget", "restricted")):
        r = await client.post(
            f"{API}/notes",
            headers=h[lead],
            json={"title": title, "space": p["space"], "sensitivity": level, "body": f"# {title}"},
        )
        notes[level] = r.json()["id"]
        review = (await client.post(f"{API}/notes/{notes[level]}/submit", headers=h[lead])).json()
        r = await client.post(f"{API}/reviews/{review['id']}/approve", headers=h[lead], json={})
        assert r.status_code == 200, r.text
    async with sessions() as s:
        proj = await s.get(Project, uuid.UUID(p["id"]))
        proj.starts_on, proj.ends_on = (
            date.today() - timedelta(days=100),
            date.today() - timedelta(days=1),
        )
        for sh in proj.shares:  # approved until the project's (old) end
            sh.approved_until = proj.ends_on
        await s.commit()
    get = lambda d, who: client.get(f"{API}/documents/{d}", headers=h[who])  # noqa: E731
    assert (await get(onboarding, member)).status_code == 404  # HR's SOPs: gone
    assert (await get(notes["internal"], member)).status_code == 200  # project notes: still open
    assert (await get(notes["restricted"], member)).status_code == 404  # key details: hidden
    assert (await get(notes["restricted"], lead)).status_code == 200  # the project lead keeps them
    assert (await get(notes["restricted"], hr)).status_code == 200  # and the department's lead
    r = await client.post(
        f"{API}/notes",
        headers=h[member],
        json={"title": "Late", "space": p["space"], "body": "# x"},
    )
    assert r.status_code == 403  # read-only
    # renewing brings it back; HR's lead confirms the share for the new period
    r = await client.post(
        f"{API}/projects/{p['id']}/renew",
        headers=h[lead],
        json={"ends_on": (date.today() + timedelta(days=60)).isoformat()},
    )
    assert r.status_code == 200
    share = r.json()["shares"][0]
    assert share["renewal_requested"] and not share["in_force"]
    assert (await get(onboarding, member)).status_code == 404
    await client.post(
        f"{API}/project-shares/{share['id']}/approve", headers=h[hr], json={"scope": "space"}
    )
    assert (await get(onboarding, member)).status_code == 200


async def test_leaving_members_lose_project_access(indexed, sessions, client, make_user, sign_in):
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in)
    async with sessions() as s:
        u = await get_user(s, member.user.id)
        u.leaving_on = date.today() - timedelta(days=1)
        await s.commit()
    assert (await principal(sessions, member)).can("ask", p["space"]) is False


async def test_ending_reminder_once_and_project_profiles_local(
    indexed, sessions, client, make_user, sign_in
):
    p, lead, *_ = await setup(client, make_user, sign_in)
    async with sessions() as s:
        proj = await s.get(Project, uuid.UUID(p["id"]))
        proj.ends_on = date.today() + timedelta(days=10)
        await s.commit()
    for _ in range(2):
        async with sessions() as s, s.begin():
            await ending_reminders(s, 14)
    async with sessions() as s:
        kinds = [
            n.kind
            for n in (
                await s.execute(select(Notification).where(Notification.user_id == lead.user.id))
            ).scalars()
        ]
        profiles = await project_profiles(s)
    assert kinds.count("project_ending") == 1
    assert profiles[p["space"]].local_only
    assert json.dumps(p)  # serialisable


async def test_frontmatter_cannot_move_a_project_note_into_a_department(
    indexed, sessions, client, make_user, sign_in
):
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in, shares=())
    r = await client.post(
        f"{API}/notes",
        headers=h[member],
        json={"title": "Plan", "space": p["space"], "body": "# P"},
    )
    note = r.json()
    src = (await client.get(f"{API}/notes/{note['id']}/source", headers=h[member])).json()
    moved = src["content"].replace(f"space: {p['space']}", "space: hr\nshared_with: [it]")
    r = await client.put(
        f"{API}/notes/{note['id']}",
        headers=h[member],
        json={"base_version": src["version"], "content": moved},
    )
    async with sessions() as s:
        d = await s.get(Document, uuid.UUID(note["id"]))
        assert {a.space for a in d.access} == {p["space"]}, r.text


async def test_project_reviews_go_to_the_project_lead(
    indexed, sessions, client, make_user, sign_in
):
    """Not to department approvers, who hold nothing on the project space."""
    p, lead, member, other, hr, h = await setup(client, make_user, sign_in, shares=())
    core_lead = await make_user(roles=CORE_LEAD)
    note = (
        await client.post(
            f"{API}/notes",
            headers=h[member],
            json={"title": "Run sheet", "space": p["space"], "body": "# Run sheet"},
        )
    ).json()
    r = await client.post(f"{API}/notes/{note['id']}/submit", headers=h[member])
    assert r.status_code in (200, 201), r.text
    async with sessions() as s:
        got = {
            n.user_id
            for n in (
                await s.execute(select(Notification).where(Notification.kind == "review_requested"))
            ).scalars()
        }
    assert lead.user.id in got
    assert not got & {core_lead.user.id, hr.user.id, other.user.id, member.user.id}
    # once the project has ended, nobody is asked
    async with sessions() as s:
        proj = await s.get(Project, uuid.UUID(p["id"]))
        proj.ends_on = date.today() - timedelta(days=1)
        proj.starts_on = date.today() - timedelta(days=30)
        await s.commit()
        from app.governance.notify import users_with

        assert await users_with(s, "approve", p["space"]) == []
