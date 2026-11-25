"""Onboarding paths (frontend spec §9.1)."""

from __future__ import annotations

import uuid

from tests.db.test_governance import API, LEAD, SOP, STAFF, doc_id

PILLARS = "Methodology/Brand Pillars Framework.md"  # core restricted: staff can't read it
HR_ROLES = ("employee", "hr-staff")


async def test_build_assign_and_complete_a_path(indexed, sessions, client, make_user, sign_in):
    lead, staff = await make_user(roles=LEAD), await make_user(roles=STAFF)
    hl, hs = await sign_in(lead), await sign_in(staff)
    sop, pillars = await doc_id(sessions, SOP), await doc_id(sessions, PILLARS)
    docs = (await client.get(f"{API}/documents", headers=hs)).json()
    extra = next(d["id"] for d in docs if d["id"] != str(sop))

    body = {
        "space": "core",
        "title": "New trainer",
        "description": "Your first two weeks.",
        "steps": [
            {"title": "Week 1", "items": [{"document_id": str(sop), "required": True}]},
            {
                "title": "Week 2",
                "items": [{"document_id": extra}, {"document_id": str(pillars)}],
            },
        ],
    }
    assert (await client.post(f"{API}/paths", headers=hs, json=body)).status_code == 403
    # Staff can't put a document they can't see on a path; a random id looks the same.
    ghost = {**body, "steps": [{"title": "x", "items": [{"document_id": str(uuid.uuid4())}]}]}
    assert (await client.post(f"{API}/paths", headers=hl, json=ghost)).status_code == 422
    r = await client.post(f"{API}/paths", headers=hl, json=body)
    assert r.status_code == 201, r.text
    path = r.json()
    assert path["total"] == 3 and path["can_edit"]

    r = await client.post(
        f"{API}/paths/{path['id']}/assign", headers=hl, json={"roles": ["core-staff"]}
    )
    assert r.status_code == 200, r.text
    kinds = [n["kind"] for n in (await client.get(f"{API}/notifications", headers=hs)).json()]
    assert "path_assigned" in kinds

    mine = (await client.get(f"{API}/me/paths", headers=hs)).json()
    assert [p["id"] for p in mine] == [path["id"]]
    items = [i for s in mine[0]["steps"] for i in s["items"]]
    # The restricted item: counted, but no title, link or type.
    hidden = items[2]
    assert hidden["readable"] is False and hidden["title"] is None and hidden["document_id"] is None
    assert "Pillars" not in str(mine)
    assert mine[0]["next_item"] == items[0]["id"]

    # A required item is done by signing off the SOP, not by a click.
    r = await client.post(f"{API}/path-items/{items[0]['id']}/done", headers=hs)
    assert r.status_code == 409
    assert (await client.post(f"{API}/documents/{sop}/acknowledge", headers=hs)).status_code == 200
    assert (
        await client.post(f"{API}/path-items/{items[1]['id']}/done", headers=hs)
    ).status_code == 204
    # The hidden item can't be marked either (404, like a missing one).
    assert (
        await client.post(f"{API}/path-items/{hidden['id']}/done", headers=hs)
    ).status_code == 404
    mine = (await client.get(f"{API}/me/paths/{path['id']}", headers=hs)).json()
    assert mine["done"] == 2 and mine["next_item"] is None

    # Someone not assigned sees nothing.
    other = await sign_in(await make_user(roles=("employee",)))
    assert (await client.get(f"{API}/me/paths/{path['id']}", headers=other)).status_code == 404
    assert (
        await client.post(f"{API}/path-items/{items[1]['id']}/done", headers=other)
    ).status_code == 404

    # Leads and HR see progress; HR can't read core SOPs, so no item titles.
    report = (await client.get(f"{API}/reports/path-completion", headers=hl)).json()
    person = next(p for p in report[0]["people"] if p["name"] == staff.user.display_name)
    assert person == {**person, "done": 2, "total": 3}
    hh = await sign_in(await make_user(roles=HR_ROLES))
    report = (await client.get(f"{API}/reports/path-completion", headers=hh)).json()
    assert report and "Discovery" not in str(report) and "Pillars" not in str(report)
    hr_view = (await client.get(f"{API}/paths/{path['id']}", headers=hh)).json()
    assert all(i["title"] is None for s in hr_view["steps"] for i in s["items"])
    assert hr_view["can_edit"] is False
    r = await client.put(f"{API}/paths/{path['id']}", headers=hh, json=body)
    assert r.status_code == 403
    assert (await client.get(f"{API}/reports/path-completion", headers=hs)).status_code == 403
