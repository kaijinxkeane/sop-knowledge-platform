"""Required reading and sign-off (frontend spec §9.2)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.db.test_governance import API, LEAD, STAFF, checked, doc_id, edit

SECRET = "Methodology/Brand Pillars Framework.md"  # core restricted: staff can't read it


async def test_assign_acknowledge_and_reread_after_material_change(
    indexed, sessions, client, make_user, sign_in
):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    other = await make_user(roles=STAFF)
    hs, hl, ho = await sign_in(staff), await sign_in(lead), await sign_in(other)
    note = await doc_id(sessions)
    due = (date.today() - timedelta(days=1)).isoformat()

    roles = (await client.get(f"{API}/reading-assignments/roles", headers=hl)).json()
    assert "core-staff" in {r["name"] for r in roles} and set(roles[0]) == {"name", "description"}
    assert (await client.get(f"{API}/reading-assignments/roles", headers=hs)).status_code == 403

    # Only the space's lead assigns.
    body = {"document_id": str(note), "roles": ["core-staff"], "due_on": due}
    assert (
        await client.post(f"{API}/reading-assignments", headers=hs, json=body)
    ).status_code == 403
    r = await client.post(f"{API}/reading-assignments", headers=hl, json=body)
    assert r.status_code == 201, r.text

    mine = (await client.get(f"{API}/me/required-reading", headers=hs)).json()
    assert [m["document_id"] for m in mine] == [str(note)] and mine[0]["overdue"]
    assert (await client.get(f"{API}/notifications", headers=hs)).json()[0][
        "kind"
    ] == "reading_assigned"

    st = (await client.post(f"{API}/documents/{note}/acknowledge", headers=hs)).json()
    assert st["acknowledged_version"] == st["current_version"] == 1 and not st["overdue"]
    # Acknowledging twice records nothing new.
    await client.post(f"{API}/documents/{note}/acknowledge", headers=hs)

    report = (await client.get(f"{API}/reports/read-status", headers=hl)).json()
    people = {p["name"]: p for p in report[0]["people"]}
    assert people[staff.user.display_name]["version"] == 1
    assert people[other.user.display_name]["overdue"]
    assert (await client.get(f"{API}/reports/read-status", headers=hs)).status_code == 403

    # A minor edit: the acknowledgement still counts.
    await edit(client, hs, note, lambda t: t + "\nTypo fix.\n", sessions=sessions)
    rid = (await client.post(f"{API}/notes/{note}/submit", headers=hs)).json()["id"]
    assert (
        await client.post(f"{API}/reviews/{rid}/approve", headers=hl, json={})
    ).status_code == 200
    await checked(sessions)
    st = (await client.get(f"{API}/documents/{note}/reading", headers=hs)).json()
    assert st["acknowledged_version"] == 1 and st["current_version"] == 2 and not st["reread"]

    # A material change: read it again.
    await edit(client, hs, note, lambda t: t + "\nNew safety step.\n", sessions=sessions)
    rid = (await client.post(f"{API}/notes/{note}/submit", headers=hs)).json()["id"]
    r = await client.post(
        f"{API}/reviews/{rid}/approve", headers=hl, json={"material_change": True}
    )
    assert r.status_code == 200, r.text
    await checked(sessions)
    st = (await client.get(f"{API}/documents/{note}/reading", headers=hs)).json()
    assert st["acknowledged_version"] is None and st["reread"] and st["current_version"] == 3
    kinds = [n["kind"] for n in (await client.get(f"{API}/notifications", headers=ho)).json()]
    assert "reading_reread" in kinds
    st = (await client.post(f"{API}/documents/{note}/acknowledge", headers=hs)).json()
    assert st["acknowledged_version"] == 3

    # Append-only in the database itself.
    async with sessions() as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE read_acknowledgements SET version = 9"))


async def test_hidden_documents_stay_hidden(indexed, sessions, client, make_user, sign_in):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    hs, hl = await sign_in(staff), await sign_in(lead)
    secret = await doc_id(sessions, SECRET)
    # The lead may assign it to staff who can't read it: the report shows the gap,
    # the assignee sees nothing (no title), and acknowledging is a 404.
    r = await client.post(
        f"{API}/reading-assignments",
        headers=hl,
        json={"document_id": str(secret), "user_ids": [str(staff.user.id)]},
    )
    assert r.status_code == 201, r.text
    assert (await client.get(f"{API}/me/required-reading", headers=hs)).json() == []
    assert (
        await client.post(f"{API}/documents/{secret}/acknowledge", headers=hs)
    ).status_code == 404
    assert (await client.get(f"{API}/documents/{secret}/reading", headers=hs)).status_code == 404
    assert (
        await client.get(f"{API}/documents/{uuid.uuid4()}/reading", headers=hs)
    ).status_code == 404
    report = (await client.get(f"{API}/reports/read-status", headers=hl)).json()
    gap = next(d for d in report if d["document_id"] == str(secret))
    assert gap["people"][0]["can_read"] is False
    # Staff can't assign a document they can't see (404, not 403).
    r = await client.post(
        f"{API}/reading-assignments",
        headers=hs,
        json={"document_id": str(secret), "roles": ["core-staff"]},
    )
    assert r.status_code == 404
