"""Phase 2 slice 3: version history for readers, bookmarks, Ctrl+K quick search."""

from __future__ import annotations

from sqlalchemy import delete, select

from app.classify.service import ClassifierService
from app.db.models import Conversation, Document, Role, UserRole
from tests.db.conftest import no_names

API = "/api/v1"
EMPLOYEE = ("employee",)
STAFF = ("employee", "core-staff")
LEAD = ("employee", "core-lead")
ROOM = "Public/How to Book a Training Room.md"
DISCOVERY = "Programmes/Signature Personal Brand Programme/01 Discovery/Discovery Workshop SOP.md"
RATE = "Commercial/Rate Card 2026.md"


async def doc_id(sessions, path) -> str:
    async with sessions() as s:
        return str(
            (await s.execute(select(Document.id).where(Document.vault_path == path))).scalar_one()
        )


async def _edit(client, sessions, h, did, old, new):
    src = (await client.get(f"{API}/notes/{did}/source", headers=h)).json()
    assert old in src["content"]
    r = await client.put(
        f"{API}/notes/{did}",
        headers=h,
        json={"base_version": src["version"], "content": src["content"].replace(old, new)},
    )
    assert r.status_code == 200, r.text
    await ClassifierService(sessions, no_names).run_pending(limit=100)  # the name check
    return r.json()["commit"]


# --- version history ---------------------------------------------------------------------


async def test_readers_get_approved_versions_only(indexed, sessions, client, make_user, sign_in):
    staff, reader = await make_user(roles=STAFF), await make_user(roles=EMPLOYEE)
    hs, hr = await sign_in(staff), await sign_in(reader)
    room = await doc_id(sessions, ROOM)
    approved = (await client.get(f"{API}/documents/{room}/versions", headers=hr)).json()
    assert approved and all(v["approved"] for v in approved)
    live = next(v for v in approved if v["live"])

    wip = await _edit(client, sessions, hs, room, "Book", "Reserve (unreviewed)")

    # The editor sees the new version, marked as latest and not approved.
    r = await client.get(f"{API}/documents/{room}/versions", headers=hs)
    assert r.status_code == 200, r.text
    mine = r.json()
    top = mine[0]
    assert (top["commit"], top["latest"], top["approved"]) == (wip, True, False)
    r = await client.get(f"{API}/documents/{room}/versions/{wip}", headers=hs)
    assert r.status_code == 200 and "Reserve (unreviewed)" in r.json()["content"]

    # A reader neither lists it nor can open it by commit.
    theirs = (await client.get(f"{API}/documents/{room}/versions", headers=hr)).json()
    assert wip not in {v["commit"] for v in theirs}
    r = await client.get(f"{API}/documents/{room}/versions/{wip}", headers=hr)
    assert r.status_code == 404 and "unreviewed" not in r.text
    # ...but can read the approved one.
    r = await client.get(f"{API}/documents/{room}/versions/{live['commit']}", headers=hr)
    assert r.status_code == 200 and r.json()["approved"] is True
    assert "unreviewed" not in r.json()["content"]


async def test_version_ids_must_be_full_known_commits(
    indexed, sessions, client, make_user, sign_in
):
    staff = await make_user(roles=STAFF)
    h = await sign_in(staff)
    room = await doc_id(sessions, ROOM)
    live = (await client.get(f"{API}/documents/{room}/versions", headers=h)).json()[0]["commit"]
    for bad in (live[:10], "0" * 40, "HEAD", "../../etc", live.upper()):
        r = await client.get(f"{API}/documents/{room}/versions/{bad}", headers=h)
        assert r.status_code in (404, 422), (bad, r.status_code)
    # A commit that changed only this note is not a version of another one.
    edit = await _edit(client, sessions, h, room, "Book", "Reserve")
    other = await doc_id(sessions, "Public/Training Day Dress Code.md")
    r = await client.get(f"{API}/documents/{other}/versions/{edit}", headers=h)
    assert r.status_code == 404


# --- bookmarks ---------------------------------------------------------------------------


async def test_bookmarks_are_private_and_idempotent(indexed, sessions, client, make_user, sign_in):
    a, b = await make_user(roles=EMPLOYEE), await make_user(roles=EMPLOYEE)
    ha, hb = await sign_in(a), await sign_in(b)
    room = await doc_id(sessions, ROOM)
    body = {"target_type": "document", "target_id": room}
    first = await client.post(f"{API}/me/bookmarks", headers=ha, json=body)
    again = await client.post(f"{API}/me/bookmarks", headers=ha, json=body)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["title"] == "How to Book a Training Room"
    slide = await client.post(f"{API}/me/bookmarks", headers=ha, json={**body, "part": 2})
    assert slide.json()["id"] != first.json()["id"]
    assert len((await client.get(f"{API}/me/bookmarks", headers=ha)).json()) == 2

    # Someone else sees none of them and can't delete them.
    assert (await client.get(f"{API}/me/bookmarks", headers=hb)).json() == []
    r = await client.delete(f"{API}/me/bookmarks/{first.json()['id']}", headers=hb)
    assert r.status_code == 404
    r = await client.delete(f"{API}/me/bookmarks/{first.json()['id']}", headers=ha)
    assert r.status_code == 204
    assert len((await client.get(f"{API}/me/bookmarks", headers=ha)).json()) == 1


async def test_cannot_bookmark_what_you_cannot_open(indexed, sessions, client, make_user, sign_in):
    a, b = await make_user(roles=EMPLOYEE), await make_user(roles=EMPLOYEE)
    ha = await sign_in(a)
    rate = await doc_id(sessions, RATE)
    async with sessions() as s:
        conv = Conversation(user_id=b.user.id, title="b's private question")
        s.add(conv)
        await s.commit()
    for body in (
        {"target_type": "document", "target_id": rate},
        {"target_type": "conversation", "target_id": str(conv.id)},
        {"target_type": "document", "target_id": "00000000-0000-0000-0000-000000000000"},
    ):
        r = await client.post(f"{API}/me/bookmarks", headers=ha, json=body)
        assert r.status_code == 404, body
        assert "Rate Card" not in r.text and "private question" not in r.text


async def test_bookmark_disappears_when_access_is_removed(
    indexed, sessions, client, make_user, sign_in
):
    staff = await make_user(roles=STAFF)
    h = await sign_in(staff)
    discovery = await doc_id(sessions, DISCOVERY)
    r = await client.post(
        f"{API}/me/bookmarks", headers=h, json={"target_type": "document", "target_id": discovery}
    )
    assert r.status_code == 201
    async with sessions() as s:
        await s.execute(
            delete(UserRole).where(
                UserRole.user_id == staff.user.id,
                UserRole.role_id.in_(select(Role.id).where(Role.name == "core-staff")),
            )
        )
        await s.commit()
    listed = (await client.get(f"{API}/me/bookmarks", headers=h)).json()
    assert listed == []  # no title, no hint it was there


# --- quick search ------------------------------------------------------------------------


async def test_quick_search_returns_only_readable_titles(
    indexed, sessions, client, make_user, sign_in
):
    reader, staff = await make_user(roles=EMPLOYEE), await make_user(roles=STAFF)
    hr, hs = await sign_in(reader), await sign_in(staff)
    for q in ("rate", "Rate Card", "floor", "disciplinary"):
        r = await client.get(f"{API}/quick-search", params={"q": q}, headers=hs)
        assert r.status_code == 200
        assert "Rate Card" not in r.text and "Disciplinary" not in r.text, q
    r = (await client.get(f"{API}/quick-search", params={"q": "discovery"}, headers=hs)).json()
    assert "Running the Discovery Workshop" in {d["title"] for d in r["documents"]}
    assert r["stages"] == ["discovery"]
    r = (await client.get(f"{API}/quick-search", params={"q": "signature"}, headers=hs)).json()
    assert r["programmes"] == ["Signature Personal Brand Programme"]
    # The reader can't see core's internal SOPs, so neither their titles nor the programme.
    r = (await client.get(f"{API}/quick-search", params={"q": "discovery"}, headers=hr)).json()
    assert r["documents"] == []
    r = (await client.get(f"{API}/quick-search", params={"q": "signature"}, headers=hr)).json()
    assert r["programmes"] == []


async def test_quick_search_wildcards_are_literal(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=("employee", "core-lead")))
    for q in ("%", "_", "\\", "' OR 1=1 --"):
        r = await client.get(f"{API}/quick-search", params={"q": q}, headers=h)
        assert r.status_code == 200, q
        assert r.json()["documents"] == [], q
    r = await client.get(f"{API}/quick-search", params={"q": "   "}, headers=h)
    assert r.status_code == 422


async def test_quick_search_conversations_are_your_own(
    indexed, sessions, client, make_user, sign_in
):
    a, b = await make_user(roles=EMPLOYEE), await make_user(roles=EMPLOYEE)
    async with sessions() as s:
        s.add(Conversation(user_id=a.user.id, title="Dress code for workshops"))
        await s.commit()
    ra = (
        await client.get(f"{API}/quick-search", params={"q": "dress"}, headers=await sign_in(a))
    ).json()
    rb = (
        await client.get(f"{API}/quick-search", params={"q": "dress"}, headers=await sign_in(b))
    ).json()
    assert [c["title"] for c in ra["conversations"]] == ["Dress code for workshops"]
    assert rb["conversations"] == []
    assert "Training Day Dress Code" in {d["title"] for d in rb["documents"]}
