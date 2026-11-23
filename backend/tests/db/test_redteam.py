"""Red-team: try to get information a user shouldn't have (2026-11-22).

Each test is an attack by a low-privilege user against the real API, Postgres
RLS and the demo vault. A failing test means the attack worked.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from sqlalchemy import select

from app.agents.concierge import retrieve
from app.classify.service import ClassifierService
from app.db.models import ChatMessage, Conversation, Document
from app.governance.access import overlap
from app.identity import get_user, principal_for
from app.spaces import space_profiles
from tests.db.conftest import fake_query, no_names

API = "/api/v1"
EMPLOYEE = ("employee",)
STAFF = ("employee", "core-staff")
LEAD = ("employee", "core-lead")
HR = ("employee", "hr-staff")
ADMIN = ("employee", "platform-admin")
RATE = "Commercial/Rate Card 2026.md"
DISCIPLINARY = "HR/Disciplinary Process.md"
PILLARS = "Methodology/Brand Pillars Framework.md"
SECRETS = ["7,500", "1,600", "Floor price", "written warning", "30-day improvement"]


async def doc_id(sessions, path) -> str:
    async with sessions() as s:
        return str(
            (await s.execute(select(Document.id).where(Document.vault_path == path))).scalar_one()
        )


def leaks(resp) -> list[str]:
    body = resp.text
    return [x for x in SECRETS if x in body]


# --- 1. IDOR: every document endpoint, with the id of a document I can't read ------------


async def test_hidden_document_is_404_on_every_endpoint(
    indexed, sessions, client, make_user, sign_in
):
    h = await sign_in(await make_user(roles=STAFF))
    rate = await doc_id(sessions, RATE)
    calls = [
        ("GET", f"/documents/{rate}", None),
        ("GET", f"/documents/{rate}/parts", None),
        ("GET", f"/documents/{rate}/versions", None),
        ("GET", f"/documents/{rate}/file", None),
        ("GET", f"/notes/{rate}/source", None),
        ("GET", f"/notes/{rate}/diff", None),
        ("POST", f"/notes/{rate}/submit", None),
        ("POST", f"/notes/{rate}/approve", {"version": "0" * 64}),
        ("POST", f"/notes/{rate}/retire", None),
        ("PUT", f"/notes/{rate}", {"base_version": "0" * 64, "content": "x"}),
        ("POST", f"/documents/{rate}/names", {"names": []}),
    ]
    odd = {}
    for method, path, body in calls:
        r = await client.request(method, API + path, headers=h, json=body)
        if r.status_code != 404 or leaks(r):
            odd[f"{method} {path.replace(rate, '<id>')}"] = (r.status_code, leaks(r))
    assert odd == {}, odd


# --- 2. Search and Library: restricted text, titles, SQL injection ---------------------------


@pytest.mark.parametrize(
    "q",
    [
        "floor price 7,500",
        "written warning improvement plan",
        "Rate Card",
        "' OR 1=1 --",
        "%",
        "_",
        "\\",
        "'); RESET ROLE; SELECT * FROM chunks; --",
        "floor\x00price",
    ],
)
async def test_search_never_returns_restricted(indexed, sessions, client, make_user, sign_in, q):
    h = await sign_in(await make_user(roles=EMPLOYEE))
    r = await client.get(f"{API}/search", params={"q": q}, headers=h)
    assert r.status_code in (200, 422), r.text
    assert not leaks(r) and "Rate Card" not in r.text and "Disciplinary" not in r.text


async def test_library_filters_never_list_restricted(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=EMPLOYEE))
    for params in (
        {},
        {"space": "hr"},
        {"space": "core"},
        {"doc_type": "reference"},
        {"kind": "note"},
        {"doc_type": "policy"},
    ):
        r = await client.get(f"{API}/documents", params=params, headers=h)
        titles = {d["title"] for d in r.json()}
        assert not titles & {"Rate Card 2026", "Disciplinary Process", "Brand Pillars Framework"}


# --- 3. Widening access by editing frontmatter ------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        ("sensitivity: internal", "sensitivity: public"),
        (
            "sensitivity: internal",
            "sensitivity: internal\nshared_with: [it]",
        ),
        ("sensitivity: internal", "sensitivity: internal\nspace: it"),
        ("sensitivity: internal", "sensitivity: internal\nstatus: published"),
    ],
)
async def test_staff_cannot_widen_a_note(indexed, sessions, client, make_user, sign_in, change):
    staff = await make_user(roles=STAFF)
    h = await sign_in(staff)
    r = await client.post(
        f"{API}/notes", headers=h, json={"title": "Widen me", "space": "core", "body": "# W\n\nx"}
    )
    note = r.json()
    src = (await client.get(f"{API}/notes/{note['id']}/source", headers=h)).json()
    assert change[0] in src["content"]
    r = await client.put(
        f"{API}/notes/{note['id']}",
        headers=h,
        json={"base_version": src["version"], "content": src["content"].replace(*change, 1)},
    )
    assert r.status_code == 403, (change, r.status_code, r.text)


async def test_note_body_cannot_smuggle_its_own_frontmatter(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=STAFF))
    body = "---\nsensitivity: public\nspace: it\n---\n# Smuggled"
    r = await client.post(
        f"{API}/notes", headers=h, json={"title": "Smuggle", "space": "core", "body": body}
    )
    assert r.status_code == 201
    staff_it = await sign_in(await make_user(roles=EMPLOYEE))
    r = await client.get(f"{API}/documents/{r.json()['id']}", headers=staff_it)
    assert r.status_code == 404  # still core/internal: an employee can't see it


@pytest.mark.parametrize(
    "folder",
    ["../outside", "/etc", "HR", "Handovers/core", ".git/hooks", "Commercial/../../x", "..\\x"],
)
async def test_note_folder_cannot_escape_or_jump_spaces(
    indexed, sessions, client, make_user, sign_in, vault, folder
):
    h = await sign_in(await make_user(roles=STAFF))
    r = await client.post(
        f"{API}/notes",
        headers=h,
        json={"title": "Escape", "space": "core", "folder": folder, "body": "# E"},
    )
    if r.status_code == 201:
        path = r.json()["vault_path"]
        assert (vault.root / path).resolve().is_relative_to(vault.root)
        async with sessions() as s:
            d = (await s.execute(select(Document).where(Document.vault_path == path))).scalar_one()
            spaces = {a.space for a in d.access}
        assert spaces <= {"core"}, (folder, spaces)
    else:
        assert r.status_code in (403, 422), (folder, r.status_code)


async def test_name_collision_does_not_reveal_hidden_files(indexed, client, make_user, sign_in):
    """Creating a note at a hidden note's path must not confirm that the path exists."""
    h = await sign_in(await make_user(roles=STAFF))
    replies = []
    for title in ("Rate Card 2026", "rate card 2026", "Rate Card 2031"):
        r = await client.post(
            f"{API}/notes",
            headers=h,
            json={"title": title, "space": "core", "folder": "Commercial", "body": "# x"},
        )
        replies.append(r.status_code)
    assert set(replies) == {201}, replies


# --- 4. Old versions: content from before a note was made less restricted --------------------


async def test_old_restricted_version_is_not_readable_after_downgrade(
    indexed, sessions, client, make_user, sign_in
):
    """A lead cleans up a restricted note and makes it internal. Until that new
    version is approved, the old (restricted) text is what is live: staff must
    not get it through the file, answers or diffs; after approval, still not
    through diffs of old versions."""
    lead, staff = await make_user(roles=LEAD), await make_user(roles=STAFF)
    hl, hs = await sign_in(lead), await sign_in(staff)
    pillars = await doc_id(sessions, PILLARS)
    src = (await client.get(f"{API}/notes/{pillars}/source", headers=hl)).json()
    secret = src["content"].split("---", 2)[2].strip().splitlines()[-1].strip()
    assert secret
    fm = (
        src["content"]
        .split("---", 2)[1]
        .replace("sensitivity: restricted", "sensitivity: internal")
    )
    cleaned = f"---{fm}---\n\n# Brand Pillars (summary)\n\nThree pillars.\n"
    r = await client.put(
        f"{API}/notes/{pillars}",
        headers=hl,
        json={"base_version": src["version"], "content": cleaned},
    )
    assert r.status_code == 200, r.text
    await ClassifierService(sessions, no_names).run_pending(limit=100)

    # Before approval: the live text is still the restricted one.
    seen = []
    for path in (
        f"/documents/{pillars}",
        f"/documents/{pillars}/file",
        f"/notes/{pillars}/source",
        f"/notes/{pillars}/diff",
    ):
        r = await client.get(API + path, headers=hs)
        if r.status_code == 200 and (secret in r.text or path == f"/documents/{pillars}"):
            seen.append(path)
    async with sessions() as s:
        principal = principal_for(await get_user(s, staff.user.id))
    _, per_space = await retrieve(
        sessions, principal, secret, await fake_query(secret), space_profiles(), None
    )
    if any(str(x.document_id) == pillars for hs_ in per_space.values() for x in hs_):
        seen.append("answers")
    assert seen == [], f"before approval, staff reached the restricted version via {seen}"

    # The lead approves the cleaned version: staff can read it, but not old versions.
    review = (await client.post(f"{API}/notes/{pillars}/submit", headers=hl)).json()
    r = await client.post(f"{API}/reviews/{review['id']}/approve", headers=hl, json={})
    assert r.status_code == 200, r.text
    await ClassifierService(sessions, no_names).run_pending(limit=100)  # core is name-checked
    assert (await client.get(f"{API}/documents/{pillars}", headers=hs)).status_code == 200
    versions = (await client.get(f"{API}/documents/{pillars}/versions", headers=hs)).json()
    oldest = versions[-1]["commit"]
    for path in (f"/notes/{pillars}/diff?from={oldest}", f"/notes/{pillars}/diff?to={oldest}"):
        r = await client.get(API + path, headers=hs)
        if r.status_code == 200 and secret in r.text:
            seen.append(path)
    assert seen == [], f"after approval, old restricted text readable via {seen}"
    # The lead (who could read the old version) still can.
    r = await client.get(f"{API}/notes/{pillars}/diff?from={oldest}", headers=hl)
    assert r.status_code == 200 and secret in r.text


# --- 5. Admin: content access by granting yourself a role -------------------------------------


async def test_admin_cannot_grant_themselves_content(indexed, sessions, client, make_user, sign_in):
    admin = await make_user(roles=ADMIN)
    h = await sign_in(admin)
    rate = await doc_id(sessions, RATE)
    r = await client.post(
        f"{API}/admin/roles",
        headers=h,
        json={
            "name": "sneaky",
            "description": "x",
            "grants": [{"space": "core", "max_sensitivity": "restricted", "actions": ["ask"]}],
        },
    )
    made = r.status_code
    r = await client.patch(
        f"{API}/admin/users/{admin.user.id}",
        headers=h,
        json={"roles": ["employee", "platform-admin", "sneaky", "core-lead"]},
    )
    self_assign = r.status_code
    h = await sign_in(admin)
    r = await client.get(f"{API}/documents/{rate}/file", headers=h)
    assert r.status_code == 404, (
        f"admin read the rate card after creating a role ({made}) and assigning it to "
        f"themselves ({self_assign})"
    )


# --- 6. Other people's conversations, notifications, reviews, handovers ----------------------


async def test_other_peoples_records_are_404(indexed, sessions, client, make_user, sign_in):
    alice, bob = await make_user(roles=STAFF), await make_user(roles=STAFF)
    ha, hb = await sign_in(alice), await sign_in(bob)
    async with sessions() as s:
        conv = Conversation(user_id=alice.user.id, title="mine")
        s.add(conv)
        await s.flush()
        msg = ChatMessage(conversation_id=conv.id, role="assistant", content="private")
        s.add(msg)
        await s.commit()
    odd = {}
    for method, path, body in [
        ("GET", f"/conversations/{conv.id}/messages", None),
        ("POST", f"/conversations/{conv.id}/messages", {"content": "hello there"}),
        ("POST", f"/messages/{msg.id}/feedback", {"helpful": False, "comment": "x"}),
        ("POST", f"/notifications/{uuid.uuid4()}/read", None),
    ]:
        r = await client.request(method, API + path, headers=hb, json=body)
        if r.status_code != 404:
            odd[f"{method} {path}"] = r.status_code
    # a review Alice opened: Bob (same rights) can't withdraw it
    note = (
        await client.post(
            f"{API}/notes", headers=ha, json={"title": "A", "space": "core", "body": "# A"}
        )
    ).json()
    await ClassifierService(sessions, no_names).run_pending(limit=100)
    review = (await client.post(f"{API}/notes/{note['id']}/submit", headers=ha)).json()
    r = await client.post(f"{API}/reviews/{review['id']}/withdraw", headers=hb)
    if r.status_code not in (403, 404):
        odd["withdraw someone else's review"] = r.status_code
    r = await client.post(f"{API}/reviews/{review['id']}/approve", headers=hb, json={})
    if r.status_code not in (403, 404):
        odd["staff approving a review"] = r.status_code
    assert odd == {}, odd


async def test_handover_receiver_cannot_rewrite_it_and_other_leads_cannot_read(
    indexed, client, make_user, sign_in
):
    author, receiver = await make_user(roles=STAFF), await make_user(roles=STAFF)
    it_lead = await make_user(roles=("employee", "it-lead"))
    ha, hr, hi = await sign_in(author), await sign_in(receiver), await sign_in(it_lead)
    body = {
        "title": "H",
        "space": "core",
        "receivers": [str(receiver.user.id)],
        "fields": {"client": "Quillfeather", "stage": "strategy", "done": "x", "contacts": "y"},
    }
    h = (await client.post(f"{API}/handovers", headers=ha, json=body)).json()
    r = await client.put(f"{API}/handovers/{h['id']}", headers=hr, json={"fields": body["fields"]})
    assert r.status_code in (403, 404), r.status_code
    assert (await client.get(f"{API}/handovers/{h['id']}", headers=hi)).status_code == 404


# --- 7. Tokens ---------------------------------------------------------------------------


async def test_forged_and_stale_tokens_are_rejected(indexed, sessions, client, make_user, sign_in):
    victim, me = await make_user(roles=LEAD), await make_user(roles=EMPLOYEE)
    good = (await sign_in(me))["Authorization"].split()[1]
    head, payload, sig = good.split(".")
    pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
    claims = json.loads(base64.urlsafe_b64decode(pad(payload)))
    claims["sub"] = str(victim.user.id)
    forged_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    none_head = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    for token in (
        f"{head}.{forged_payload}.{sig}",
        f"{none_head}.{forged_payload}.",
        f"{head}.{payload}.{sig[:-2]}AA",
    ):
        r = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token
    # deactivated: the old token stops working at once
    admin = await sign_in(await make_user(roles=ADMIN))
    await client.patch(f"{API}/admin/users/{me.user.id}", headers=admin, json={"is_active": False})
    r = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {good}"})
    assert r.status_code == 401


# --- 8. Reports: what HR / leads learn about documents they can't read -----------------------


async def test_coverage_report_does_not_reveal_hidden_programmes(
    indexed, sessions, client, make_user, sign_in
):
    async with sessions() as s:
        d = (await s.execute(select(Document).where(Document.vault_path == RATE))).scalar_one()
        d.programme, d.doc_type, d.stage = "Project Falcon (confidential)", "sop", "strategy"
        await s.commit()
    hr = await sign_in(await make_user(roles=HR))
    r = await client.get(f"{API}/reports/coverage", headers=hr)
    assert "Falcon" not in r.text, "HR learned the name of a programme only in a restricted SOP"


async def test_staff_cannot_open_lead_and_hr_reports(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=STAFF))
    odd = {}
    for path in (
        "/reports/gaps",
        "/spaces/hr/gaps",
        "/spaces/core/gaps",
        "/reports/governance",
        "/reports/bus-factor",
        "/spaces/core/stale",
        "/reports/coverage",
        "/admin/audit",
        "/admin/users",
        "/reports/classification-accuracy",
    ):
        r = await client.get(API + path, headers=h)
        if r.status_code not in (403, 404):
            odd[path] = r.status_code
    r = await client.get(f"{API}/reports/conflicts", headers=h)
    if r.status_code == 200 and r.json():
        odd["/reports/conflicts"] = "non-empty"
    assert odd == {}, odd


# --- 9. History after access is taken away ------------------------------------------------


async def test_old_answers_after_access_is_removed(indexed, sessions, client, make_user, sign_in):
    """Someone moves out of HR; their chat history still holds restricted HR answers."""
    person = await make_user(roles=("employee", "hr-staff", "hr-lead"))
    dis = await doc_id(sessions, DISCIPLINARY)
    async with sessions() as s:
        conv = Conversation(user_id=person.user.id, title="disciplinary")
        s.add(conv)
        await s.flush()
        s.add(
            ChatMessage(
                conversation_id=conv.id,
                role="assistant",
                content="A formal written warning is issued with a 30-day improvement plan [1].",
                sections=[
                    {
                        "space": "hr",
                        "text": "written warning",
                        "citations": [
                            {"n": 1, "document_id": dis, "title": "Disciplinary Process"}
                        ],
                    }
                ],
            )
        )
        await s.commit()
    admin = await sign_in(await make_user(roles=ADMIN))
    await client.patch(
        f"{API}/admin/users/{person.user.id}", headers=admin, json={"roles": ["employee"]}
    )
    h = await sign_in(person)
    r = await client.get(f"{API}/conversations/{conv.id}/messages", headers=h)
    assert not leaks(r) and "Disciplinary Process" not in r.text, "old answer still readable"


async def test_nul_bytes_are_rejected_cleanly(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=STAFF))
    r = await client.post(
        f"{API}/notes", headers=h, json={"title": "Nul", "space": "core", "body": "# a\x00b"}
    )
    assert r.status_code in (201, 422), r.status_code  # never a 500


async def test_admin_role_changes_show_in_the_leads_report(
    indexed, sessions, client, make_user, sign_in
):
    """Two-person rule: an admin can't add roles to their own account or change a
    role they hold; what they do for others is visible to the space's lead."""
    a1, a2 = await make_user(roles=ADMIN), await make_user(roles=ADMIN)
    h1, h2 = await sign_in(a1), await sign_in(a2)
    r = await client.patch(
        f"{API}/admin/users/{a1.user.id}",
        headers=h1,
        json={"roles": ["employee", "platform-admin", "core-lead"]},
    )
    assert r.status_code == 403
    roles = (await client.get(f"{API}/admin/roles", headers=h1)).json()
    pa = next(x for x in roles if x["name"] == "platform-admin")
    r = await client.post(
        f"{API}/admin/roles/{pa['id']}/grants",
        headers=h1,
        json={"space": "core", "max_sensitivity": "restricted", "actions": ["ask"]},
    )
    assert r.status_code == 403
    # a second admin can do it, and the core lead sees who did what
    r = await client.patch(
        f"{API}/admin/users/{a1.user.id}",
        headers=h2,
        json={"roles": ["employee", "platform-admin", "core-lead"]},
    )
    assert r.status_code == 200
    lead = await sign_in(await make_user(roles=LEAD))
    report = (await client.get(f"{API}/reports/governance", headers=lead)).json()
    change = next(c for c in report["access_changes"] if c.get("person") == a1.user.display_name)
    assert change["by"] == a2.user.display_name and change["roles_added"] == ["core-lead"]


def test_overlap_never_widens():
    approved = [("core", "owner", "restricted", "frontmatter")]
    assert overlap(
        [("core", "owner", "internal", "frontmatter"), ("it", "shared", "internal", "frontmatter")],
        approved,
    ) == [("core", "owner", "restricted", "frontmatter")]
    # tightening applies at once
    assert overlap(
        [("core", "owner", "restricted", "x")], [("core", "owner", "internal", "x")]
    ) == [("core", "owner", "restricted", "x")]
    # a move to another space waits for approval: the approved access stays
    assert overlap([("it", "owner", "internal", "x")], approved) == approved


async def test_a_project_share_cannot_reach_another_departments_sops(
    indexed, sessions, client, make_user, sign_in
):
    """HR's lead approves HR's share with a *core* folder and a core SOP id: the
    project must still see nothing of core's restricted material."""
    from datetime import date, timedelta

    lead, member = await make_user(roles=LEAD), await make_user(roles=STAFF)
    hr = await make_user(roles=("employee", "hr-staff", "hr-lead"))
    hl, hm, hh = await sign_in(lead), await sign_in(member), await sign_in(hr)
    p = (
        await client.post(
            f"{API}/projects",
            headers=hl,
            json={
                "name": "Cross team",
                "ends_on": (date.today() + timedelta(days=30)).isoformat(),
                "members": [str(member.user.id)],
                "shares": [{"space": "hr"}],
            },
        )
    ).json()
    share = p["shares"][0]["id"]
    rate = await doc_id(sessions, RATE)
    r = await client.post(
        f"{API}/project-shares/{share}/approve",
        headers=hh,
        json={"scope": "selected", "document_ids": [rate]},
    )
    assert r.status_code == 422  # not an HR SOP
    r = await client.post(
        f"{API}/project-shares/{share}/approve",
        headers=hh,
        json={
            "scope": "selected",
            "folders": ["Commercial", "HR"],
            "max_sensitivity": "restricted",
        },
    )
    assert r.status_code == 200
    staff_only = await sign_in(await make_user(roles=EMPLOYEE))
    assert (await client.get(f"{API}/documents/{rate}/file", headers=hm)).status_code == 404
    assert (await client.get(f"{API}/documents/{rate}/file", headers=staff_only)).status_code == 404
    r = await client.get(f"{API}/search", params={"q": "floor price"}, headers=hm)
    assert not leaks(r) and "Rate Card" not in r.text
