"""Folders put to use: search/Ask inside one folder, and "similar notes" when writing.

- a folder filter only narrows: it never shows what RLS and the policy hide
- similar notes are titles the writer can already read, never anything else
"""

import re

import pytest

from app.api import notes as notes_api
from tests.db.test_chat import CEO, CORE_STAFF, NEW_HIRE
from tests.db.test_chat import model as model  # the fake-model fixture

HR_STAFF = ("employee", "hr-staff")


async def _search(client, h, q, **params):
    r = await client.get("/api/v1/search", params={"q": q, **params}, headers=h)
    assert r.status_code == 200, r.text
    return [x["vault_path"] for x in r.json()["results"]]


async def test_search_inside_a_folder_only_narrows(indexed, client, make_user, sign_in):
    ceo = await sign_in(await make_user(roles=CEO))
    everywhere = await _search(client, ceo, "client")
    assert any(not p.startswith("Commercial/") for p in everywhere)
    inside = await _search(client, ceo, "client", folder="Commercial")
    assert inside and all(p.startswith("Commercial/") for p in inside)
    # Someone who can't read Commercial/ gets nothing, not a hint it exists.
    staff = await sign_in(await make_user(roles=CORE_STAFF))
    assert await _search(client, staff, "client", folder="Commercial") == []
    # Wildcards are literal: "%" matches no folder, so no results.
    assert await _search(client, ceo, "client", folder="%") == []
    assert await _search(client, ceo, "client", folder="Comm_rcial") == []


async def test_ask_inside_a_folder(model, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=CEO))
    conv = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["id"]
    r = await client.post(
        f"/api/v1/conversations/{conv}/messages",
        headers=h,
        json={
            "content": "What are the payment terms and the cancellation clause?",
            "folder": "Commercial",
        },
    )
    assert r.status_code == 200, r.text
    prompt = model.prompts[-1]
    titles = set(re.findall(r'<source id="S\d+" title="([^"]+)"', prompt))
    assert titles and titles <= {"Client Contract Checklist", "Rate Card 2026"}
    # outside the asker's reach the folder gives the model nothing
    staff = await sign_in(await make_user(roles=CORE_STAFF))
    model.prompts.clear()
    conv2 = (await client.post("/api/v1/conversations", json={}, headers=staff)).json()["id"]
    await client.post(
        f"/api/v1/conversations/{conv2}/messages",
        headers=staff,
        json={
            "content": "What are the payment terms and the cancellation clause?",
            "folder": "Commercial",
        },
    )
    assert not any("Client Contract Checklist" in p or "Rate Card" in p for p in model.prompts)


@pytest.fixture
def loose(monkeypatch):
    # the fake embedder isn't calibrated; test the access rules, not the cut-off
    monkeypatch.setattr(notes_api, "SIMILAR_DISTANCE", 2.0)


async def test_similar_notes_show_only_what_the_writer_can_read(
    indexed, loose, client, make_user, sign_in
):
    url = "/api/v1/notes/similar"
    hr = await sign_in(await make_user(roles=HR_STAFF))
    got = (await client.post(url, json={"title": "Disciplinary Process"}, headers=hr)).json()
    assert len(got) <= 3 and all(set(g) == {"id", "title", "folder"} for g in got)
    for role in (NEW_HIRE, CORE_STAFF):
        h = await sign_in(await make_user(roles=role))
        r = await client.post(url, json={"title": "Disciplinary Process"}, headers=h)
        assert r.status_code == 200
        assert "Disciplinary Process" not in {g["title"] for g in r.json()}
        r = await client.post(url, json={"title": "Rate Card 2026"}, headers=h)
        assert not any(g["folder"].startswith("Commercial") for g in r.json())
    assert not any(g["folder"].startswith("Help") for g in got)
    assert (await client.post(url, json={"title": "x"}, headers=hr)).status_code == 422


async def test_folder_coverage_for_leads(indexed, sessions, client, make_user, sign_in):
    from app.db.models import GapTopic

    folder = "Programmes/Signature Personal Brand Programme/01 Discovery"
    async with sessions() as s:
        s.add(GapTopic(space="core", label="Rescheduling workshops", folder=folder, size=2))
        s.add(GapTopic(space="core", label="Done", folder=folder, status="addressed"))
        s.add(GapTopic(space="hr", label="Leave carry-over", folder="HR"))
        await s.commit()
    url = "/api/v1/spaces/core/folder-coverage"
    ceo = await sign_in(await make_user(roles=CEO))
    r = await client.get(url, headers=ceo)
    assert r.status_code == 200, r.text
    rows = {x["folder"]: x for x in r.json()}
    assert folder in rows and rows[folder]["documents"] >= 1
    assert rows[folder]["open_gaps"] == 1
    assert "Commercial" in rows  # the CEO reads restricted core
    assert not any(f.startswith(("HR", "IT", "Help", "Inbox")) for f in rows)
    for roles in (CORE_STAFF, NEW_HIRE, ("employee", "hr-staff", "hr-lead")):
        h = await sign_in(await make_user(roles=roles))
        assert (await client.get(url, headers=h)).status_code == 403
