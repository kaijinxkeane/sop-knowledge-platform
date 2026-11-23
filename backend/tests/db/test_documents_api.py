"""Phase 1 acceptance: a note with missing or invalid sensitivity is never
returned to a public-only user, through the API or through raw reads."""

import pytest

from app.db.models import Document, DocumentAccess

API = "/api/v1/documents"


@pytest.fixture
async def docs(sessions):
    rows = {
        "Booking a Training Room": [("core", "public")],
        "Discovery Workshop SOP": [("core", "internal")],
        "Rate Card": [("core", "restricted")],
        "No Label": [("core", None)],
        "Bad Label": [("core", "Public")],
        "Typo Label": [("core", "pubic")],
        "Leave Policy": [("hr", "public")],
        "Inbox note": [],
    }
    ids = {}
    async with sessions() as s:
        for title, access in rows.items():
            d = Document(
                vault_path=f"{title}.md",
                title=title,
                access=[DocumentAccess(space=sp, sensitivity=v) for sp, v in access],
            )
            s.add(d)
            await s.flush()
            ids[title] = str(d.id)
        await s.commit()
    return ids


async def _titles(client, headers):
    r = await client.get(API, headers=headers)
    assert r.status_code == 200
    return {d["title"] for d in r.json()}


async def test_public_only_user_sees_only_public(client, docs, make_user, sign_in):
    h = await sign_in(await make_user(roles=("employee",)))
    assert await _titles(client, h) == {"Booking a Training Room", "Leave Policy"}
    for hidden in ("No Label", "Bad Label", "Typo Label", "Rate Card", "Inbox note"):
        r = await client.get(f"{API}/{docs[hidden]}", headers=h)
        assert r.status_code == 404  # same as "doesn't exist"


async def test_core_staff_sees_internal_but_not_unlabelled(client, docs, make_user, sign_in):
    h = await sign_in(await make_user(roles=("employee", "core-staff")))
    assert await _titles(client, h) == {
        "Booking a Training Room",
        "Discovery Workshop SOP",
        "Leave Policy",
    }


async def test_core_lead_sees_bad_labels_as_restricted(client, docs, make_user, sign_in):
    h = await sign_in(await make_user(roles=("employee", "core-lead")))
    seen = await _titles(client, h)
    assert {"Rate Card", "No Label", "Bad Label", "Typo Label"} <= seen
    assert "Inbox note" not in seen  # unassigned: only the review queue (Phase 2b)
    r = await client.get(f"{API}/{docs['Bad Label']}", headers=h)
    assert r.json()["access"] == [{"space": "core", "sensitivity": "restricted"}]


async def test_requires_sign_in(client, docs):
    assert (await client.get(API)).status_code == 401


async def test_stages_come_from_vault_config(client, make_user, sign_in):
    h = await sign_in(await make_user(roles=("employee",)))
    r = await client.get(f"{API}/stages", headers=h)
    assert r.status_code == 200 and r.json()[0] == "discovery"


async def test_backlinks_leave_out_notes_the_reader_cannot_see(
    client, docs, sessions, make_user, sign_in
):
    from app.db.models import DocumentLink

    target = docs["Booking a Training Room"]
    async with sessions() as s:
        for source in ("Discovery Workshop SOP", "Rate Card", "Leave Policy"):
            s.add(DocumentLink(from_id=docs[source], target="Booking", to_id=target))
        await s.commit()

    def titles(r):
        assert r.status_code == 200
        return [b["title"] for b in r.json()]

    public = await sign_in(await make_user(roles=("employee",)))
    staff = await sign_in(await make_user(roles=("employee", "core-staff")))
    lead = await sign_in(await make_user(roles=("employee", "core-lead")))
    url = f"{API}/{target}/backlinks"
    assert titles(await client.get(url, headers=public)) == ["Leave Policy"]
    staff_sees = titles(await client.get(url, headers=staff))
    assert staff_sees == ["Discovery Workshop SOP", "Leave Policy"]
    assert "Rate Card" in titles(await client.get(url, headers=lead))
    # Backlinks of a hidden note: 404, like the note itself.
    hidden = await client.get(f"{API}/{docs['Rate Card']}/backlinks", headers=staff)
    assert hidden.status_code == 404
