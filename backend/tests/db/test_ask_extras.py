"""Phase 3 slice 2: conversation search, rename and hide; programme/stage
filters; follow-up chips; the Home cards (recent, waiting)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AuditEvent, Conversation, Document, SopApproval
from tests.db.test_chat import CEO, CORE_STAFF, NEW_HIRE, ask, model  # noqa: F401

API = "/api/v1"
SIGNATURE = "Signature Personal Brand Programme"  # stored without [[ ]]
EXECUTIVE = "Executive Presence Workshop"


async def _post(client, h, conv, content, **filters):
    import json

    r = await client.post(
        f"{API}/conversations/{conv}/messages", headers=h, json={"content": content, **filters}
    )
    assert r.status_code == 200, r.text
    return [
        (b.split("\n")[0][7:], json.loads(b.split("\n")[1][6:]))
        for b in r.text.strip().split("\n\n")
    ]


@pytest.mark.usefixtures("model")
async def test_search_rename_and_hide(client, make_user, sign_in, sessions):
    alice = await make_user(roles=CORE_STAFF)
    h, hb = await sign_in(alice), await sign_in(await make_user(roles=CORE_STAFF))
    conv, _ = await ask(client, h, "How long does the Discovery Workshop last?")
    other, _ = await ask(client, h, "Who runs the values card sort?")

    def ids(r):
        assert r.status_code == 200, r.text
        return [c["id"] for c in r.json()]

    assert ids(await client.get(f"{API}/conversations?q=discovery", headers=h)) == [conv]
    # wildcards are literal; someone else's search never finds your questions
    assert ids(await client.get(f"{API}/conversations?q=%25", headers=h)) == []
    assert ids(await client.get(f"{API}/conversations?q=discovery", headers=hb)) == []

    r = await client.patch(f"{API}/conversations/{conv}", headers=h, json={"title": "Workshop"})
    assert r.status_code == 200 and r.json()["title"] == "Workshop"
    assert (
        await client.patch(f"{API}/conversations/{conv}", headers=h, json={"title": ""})
    ).status_code == 422

    # someone else can't rename or hide it
    for method, path, body in (
        ("PATCH", f"/conversations/{conv}", {"title": "x"}),
        ("POST", f"/conversations/{conv}/hide", None),
    ):
        assert (await client.request(method, API + path, headers=hb, json=body)).status_code == 404

    assert (await client.post(f"{API}/conversations/{conv}/hide", headers=h)).status_code == 204
    assert ids(await client.get(f"{API}/conversations", headers=h)) == [other]
    for method, path, body in (
        ("GET", f"/conversations/{conv}/messages", None),
        ("POST", f"/conversations/{conv}/messages", {"content": "and then?"}),
        ("PATCH", f"/conversations/{conv}", {"title": "back"}),
    ):
        assert (await client.request(method, API + path, headers=h, json=body)).status_code == 404
    quick = (await client.get(f"{API}/quick-search?q=workshop", headers=h)).json()
    assert quick["conversations"] == []
    # hidden, not deleted: the record and an ids-only audit event remain
    async with sessions() as s:
        row = await s.get(Conversation, conv)
        assert row is not None and row.hidden_at is not None
        ev = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "conversation_hidden"))
        ).scalar_one()
        assert ev.target_id == str(conv) and not ev.details


@pytest.mark.usefixtures("model")
async def test_filters_narrow_the_answer(client, make_user, sign_in):
    h = await sign_in(await make_user(roles=CORE_STAFF))
    conv = (await client.post(f"{API}/conversations", json={}, headers=h)).json()["id"]
    q = "How long does the Discovery Workshop last?"
    events = await _post(client, h, conv, q, programme=SIGNATURE, stage="discovery")
    cites = [d for k, d in events if k == "citation"]
    assert cites and all(c["vault_path"].startswith("Programmes/Signature") for c in cites)
    # another programme's filter: the Signature SOP can't be cited
    events = await _post(client, h, conv, q, programme=EXECUTIVE)
    assert not any(
        d["vault_path"].startswith("Programmes/Signature") for k, d in events if k == "citation"
    )
    # a filter can't widen access: nothing restricted for a new hire
    hn = await sign_in(await make_user(roles=NEW_HIRE))
    conv2 = (await client.post(f"{API}/conversations", json={}, headers=hn)).json()["id"]
    events = await _post(client, hn, conv2, "rate card floor price", programme=SIGNATURE)
    assert not [d for k, d in events if k == "citation"]


@pytest.mark.usefixtures("model")
async def test_follow_ups_are_other_sections_of_cited_sops(client, make_user, sign_in):
    h = await sign_in(await make_user(roles=CORE_STAFF))
    conv = (await client.post(f"{API}/conversations", json={}, headers=h)).json()["id"]
    events = await _post(
        client, h, conv, "How long does the Discovery Workshop last?", programme=SIGNATURE
    )
    done = events[-1][1]
    cited = [d for k, d in events if k == "citation"]
    chips = done["followups"]
    assert 1 <= len(chips) <= 3
    cited_docs = {c["document_id"] for c in cited}
    assert {c["document_id"] for c in chips} <= cited_docs
    # chips are plain section names: no "Title › " path, never the cited section itself
    assert all("›" not in c["heading"] and ">" not in c["heading"] for c in chips)
    assert all(c["heading"] != c["title"] for c in chips)
    cited_leaf = {(c["heading"] or "").split("›")[-1].strip() for c in cited}
    assert not {c["heading"] for c in chips} & cited_leaf
    # the stored history offers the same chips on the latest answer only
    history = (await client.get(f"{API}/conversations/{conv}/messages", headers=h)).json()
    assert history[-1]["followups"] == chips
    assert all(m["followups"] == [] for m in history[:-1])


async def _approve_everything(sessions):
    async with sessions() as s:
        for d in (await s.execute(select(Document))).scalars():
            s.add(
                SopApproval(
                    document_id=d.id, content_hash=d.approved_hash or "x", method="baseline"
                )
            )
        await s.commit()


async def test_recent_lists_only_what_you_can_read(indexed, client, make_user, sign_in, sessions):
    await _approve_everything(sessions)
    lead = await sign_in(await make_user(roles=CEO))
    hire = await sign_in(await make_user(roles=NEW_HIRE))
    seen_lead = {
        d["title"] for d in (await client.get(f"{API}/me/recent?limit=20", headers=lead)).json()
    }
    seen_hire = {
        d["title"] for d in (await client.get(f"{API}/me/recent?limit=20", headers=hire)).json()
    }

    def readable(h):
        return client.get(f"{API}/documents", headers=h)

    hire_docs = {d["title"] for d in (await readable(hire)).json()}
    lead_docs = {d["title"] for d in (await readable(lead)).json()}
    assert seen_hire and seen_hire <= hire_docs
    assert seen_lead <= lead_docs and seen_lead - hire_docs  # the lead sees more
    assert not any("Rate Card" in t for t in seen_hire)


async def test_waiting_counts(indexed, client, make_user, sign_in, sessions):
    from app.classify.service import ClassifierService
    from tests.db.test_redteam import no_names

    author = await sign_in(await make_user(roles=CORE_STAFF))
    lead = await sign_in(await make_user(roles=CEO))
    note = (
        await client.post(
            f"{API}/notes",
            headers=author,
            json={"title": "Draft A", "space": "core", "body": "# A"},
        )
    ).json()
    await ClassifierService(sessions, no_names).run_pending(limit=100)
    w = (await client.get(f"{API}/me/waiting", headers=author)).json()
    assert w["drafts"] == 1 and w["reviews"] == 0
    before = (await client.get(f"{API}/me/waiting", headers=lead)).json()["reviews"]
    assert (
        await client.post(f"{API}/notes/{note['id']}/submit", headers=author)
    ).status_code == 201
    assert (await client.get(f"{API}/me/waiting", headers=lead)).json()["reviews"] == before + 1
    # your own request isn't waiting for you
    assert (await client.get(f"{API}/me/waiting", headers=author)).json()["reviews"] == 0
