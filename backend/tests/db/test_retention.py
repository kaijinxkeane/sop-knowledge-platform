"""Phase 5 acceptance: knowledge retention (plan §7, §11)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app import audit
from app.agents.concierge import retrieve
from app.classify.service import ClassifierService
from app.db.models import (
    AuditEvent,
    ChatMessage,
    Conflict,
    Conversation,
    Document,
    GapEvent,
    GapTopic,
    MessageCitation,
    Notification,
    Retraction,
    SearchEvent,
)
from app.identity import get_user, principal_for
from app.models.types import ChatResult, Usage
from app.retention.conflicts import detect_conflicts
from app.retention.gaps import group_gaps
from app.retention.retention import apply_retention
from app.spaces import space_profiles
from app.vault.indexer import Indexer
from tests.db.conftest import fake_embed, fake_query, no_names

API = "/api/v1"
STAFF = ("employee", "core-staff")
LEAD = ("employee", "core-lead")
HR = ("employee", "hr-staff")
CLIENT = "Quillfeather Partners"
RATE_CARD = "Commercial/Rate Card 2026.md"


def handover_body(receivers, **over):
    fields = {
        "client": CLIENT,
        "programme": "Signature Personal Brand Programme",
        "stage": "strategy",
        "done": "Discovery workshop done; pillars drafted.",
        "actions": [
            {"text": "Send pillar summary", "owner": "Jamie", "due": "2026-12-01"},
            {"text": "Book photographer"},
        ],
        "sessions": [{"when": "2026-12-04", "what": "Brand pillars workshop"}],
        "preferences": "Prefers mornings. Camera-shy.",
        "files": "",
        "contacts": "PA: via the shared inbox",
        "risks": "",
    } | over
    return {
        "title": "Quillfeather strategy handover",
        "space": "core",
        "receivers": [str(r) for r in receivers],
        "fields": fields,
    }


# --- handovers --------------------------------------------------------------------------


async def test_handover_is_readable_only_by_named_people(
    indexed, sessions, client, make_user, sign_in
):
    author, receiver = await make_user(roles=STAFF), await make_user(roles=STAFF)
    lead, other = await make_user(roles=LEAD), await make_user(roles=STAFF)
    ha, hr, hl, ho = [await sign_in(p) for p in (author, receiver, lead, other)]

    r = await client.post(f"{API}/handovers", headers=ha, json=handover_body([receiver.user.id]))
    assert r.status_code == 201, r.text
    h = r.json()
    assert any("no owner" in i["message"] for i in h["issues"])
    assert any("no date" in i["message"] for i in h["issues"])

    for who in (ha, hr, hl):
        assert (await client.get(f"{API}/handovers/{h['id']}", headers=who)).status_code == 200
        assert [x["id"] for x in (await client.get(f"{API}/handovers", headers=who)).json()] == [
            h["id"]
        ]
    # A colleague in the same space, with the same rights as the receiver: nothing.
    assert (await client.get(f"{API}/handovers/{h['id']}", headers=ho)).status_code == 404
    assert (await client.get(f"{API}/handovers", headers=ho)).json() == []
    assert (await client.get(f"{API}/documents/{h['document_id']}", headers=ho)).status_code == 404
    found = await client.get(f"{API}/search", params={"q": CLIENT}, headers=ho)
    assert found.json()["results"] == []
    # Never used in answers, not even for the lead who can read it.
    async with sessions() as s:
        principal = principal_for(await get_user(s, lead.user.id))
    _, per_space = await retrieve(
        sessions, principal, f"{CLIENT} pillars", await fake_query(CLIENT), space_profiles(), None
    )
    assert all(str(x.document_id) != h["document_id"] for hs in per_space.values() for x in hs)
    # No space row: RLS alone blocks the colleague, and lets the receiver in.
    for person, expect in ((other, 0), (receiver, 1)):
        async with sessions() as s, s.begin():
            await s.execute(text("SET LOCAL ROLE sop_reader"))
            await s.execute(
                text(
                    "SELECT set_config('sop.scopes', :sc, true), "
                    "set_config('sop.user_id', :u, true)"
                ),
                {"sc": json.dumps({"core": "internal"}), "u": str(person.user.id)},
            )
            n = await s.scalar(
                text("SELECT count(*) FROM documents WHERE id = :d"), {"d": h["document_id"]}
            )
        assert n == expect

    # Send, acknowledge, comment.
    assert (
        await client.post(f"{API}/handovers/{h['id']}/acknowledge", headers=hr)
    ).status_code == 409
    assert (await client.post(f"{API}/handovers/{h['id']}/send", headers=hr)).status_code == 403
    assert (await client.post(f"{API}/handovers/{h['id']}/send", headers=ha)).json()[
        "status"
    ] == "sent"
    assert (
        await client.post(f"{API}/handovers/{h['id']}/acknowledge", headers=hl)
    ).status_code == 403
    r = await client.post(f"{API}/handovers/{h['id']}/acknowledge", headers=hr)
    assert r.json()["status"] == "acknowledged"
    r = await client.post(
        f"{API}/handovers/{h['id']}/comments", headers=hr, json={"body": "Who books the room?"}
    )
    assert r.status_code == 201
    async with sessions() as s:
        kinds = {(n.user_id, n.kind) for n in (await s.execute(select(Notification))).scalars()}
    assert (receiver.user.id, "handover_received") in kinds
    assert (author.user.id, "handover_acknowledged") in kinds
    assert (author.user.id, "handover_comment") in kinds


async def test_handover_fix_clears_the_issues(indexed, client, make_user, sign_in):
    author, receiver = await make_user(roles=STAFF), await make_user(roles=STAFF)
    ha = await sign_in(author)
    h = (
        await client.post(f"{API}/handovers", headers=ha, json=handover_body([receiver.user.id]))
    ).json()
    fixed = handover_body([receiver.user.id])["fields"]
    fixed["actions"][1] |= {"owner": "Jamie", "due": "2026-12-08"}
    r = await client.put(f"{API}/handovers/{h['id']}", headers=ha, json={"fields": fixed})
    assert r.status_code == 200 and r.json()["issues"] == []
    detail = (await client.get(f"{API}/handovers/{h['id']}", headers=ha)).json()
    assert "Book photographer — owner: Jamie — due: 2026-12-08" in detail["markdown"]


# --- gap topics -------------------------------------------------------------------------


async def _ask(sessions, person, question, space="core", reason="no_answer"):
    async with sessions() as s:
        conv = Conversation(user_id=person.user.id, title=question[:40])
        s.add(conv)
        await s.flush()
        q = ChatMessage(conversation_id=conv.id, role="user", content=question)
        a = ChatMessage(conversation_id=conv.id, role="assistant", content="no SOP")
        s.add_all([q, a])
        await s.flush()
        s.add(
            GapEvent(
                space=space,
                message_id=a.id,
                question_id=q.id,
                user_id=person.user.id,
                reason=reason,
            )
        )
        await s.commit()


CAMERA = [
    "how do we coach camera shy clients for video content",
    "tips for camera shy clients recording video content",
    "camera shy clients video content coaching",
]


async def test_gap_topics_for_leads_and_anonymous_for_hr(
    indexed, sessions, client, make_user, sign_in
):
    askers = [await make_user(roles=STAFF) for _ in range(3)]
    for p, q in zip(askers, CAMERA, strict=True):
        await _ask(sessions, p, q)
    report = await group_gaps(sessions, fake_query, None, topic_distance=0.7)
    assert report.events == 3 and report.new_topics == 1

    lead, hr, staff = await make_user(roles=LEAD), await make_user(roles=HR), askers[0]
    hl, hh, hs = await sign_in(lead), await sign_in(hr), await sign_in(staff)
    topics = (await client.get(f"{API}/spaces/core/gaps", headers=hl)).json()
    assert len(topics) == 1 and topics[0]["people"] == 3 and topics[0]["questions"] == 3
    assert set(topics[0]["examples"]) <= set(CAMERA) and topics[0]["examples"]
    assert all(p.email not in json.dumps(topics) for p in askers)
    assert (await client.get(f"{API}/spaces/core/gaps", headers=hs)).status_code == 403

    hr_view = (await client.get(f"{API}/reports/gaps", headers=hh)).json()
    assert len(hr_view) == 1 and hr_view[0]["people"] == 3
    assert hr_view[0]["by_role"] == {"core-staff": 3}
    assert "examples" not in hr_view[0]
    assert (await client.get(f"{API}/reports/gaps", headers=hs)).status_code == 403
    r = await client.patch(
        f"{API}/gap-topics/{topics[0]['id']}", headers=hh, json={"status": "training_planned"}
    )
    assert r.status_code == 204


async def test_hr_never_sees_a_topic_two_people_asked(
    indexed, sessions, client, make_user, sign_in
):
    for q in CAMERA[:2]:
        await _ask(sessions, await make_user(roles=STAFF), q)
    await group_gaps(sessions, fake_query, None, topic_distance=0.7)
    hr = await make_user(roles=HR)
    assert (await client.get(f"{API}/reports/gaps", headers=await sign_in(hr))).json() == []


async def test_access_gap_shown_to_the_lead_only(indexed, sessions, client, make_user, sign_in):
    question = "What is the floor price on the rate card for 2026 workshops?"
    people = [await make_user(roles=("employee",)) for _ in range(3)]
    for p in people:
        await _ask(sessions, p, question)
    # offline bag-of-words vectors are far coarser than the real model's
    await group_gaps(sessions, fake_query, None, topic_distance=0.7, access_distance=0.9)
    async with sessions() as s:
        rate = (await s.execute(select(Document).where(Document.vault_path == RATE_CARD))).scalar()
        topic = (await s.execute(select(GapTopic))).scalar_one()
    assert topic.access_gap_document_id == rate.id
    lead = await make_user(roles=LEAD)
    gaps = (await client.get(f"{API}/spaces/core/gaps", headers=await sign_in(lead))).json()
    assert gaps[0]["access_gap"]["document_id"] == str(rate.id)
    # The people asking are never told that a restricted SOP exists.
    mine = (await client.get(f"{API}/me/gaps", headers=await sign_in(people[0]))).json()
    assert mine and str(rate.id) not in json.dumps(mine) and "Rate Card" not in json.dumps(mine)
    assert "no SOP you can access covers it" in mine[0]["message"]


async def test_personal_gaps_and_request(indexed, sessions, client, make_user, sign_in):
    me, other, lead = (
        await make_user(roles=STAFF),
        await make_user(roles=STAFF),
        await make_user(roles=LEAD),
    )
    hm, ho = await sign_in(me), await sign_in(other)
    for q in ("zorbing team offsite rules", "zorbing offsite team rules"):
        await client.get(f"{API}/search", params={"q": q}, headers=hm)
    mine = (await client.get(f"{API}/me/gaps", headers=hm)).json()
    assert len(mine) == 1 and mine[0]["count"] == 2
    assert (await client.get(f"{API}/me/gaps", headers=ho)).json() == []
    r = await client.post(
        f"{API}/me/gaps/request", headers=ho, json={"key": mine[0]["key"], "space": "core"}
    )
    assert r.status_code == 404  # someone else's search
    r = await client.post(
        f"{API}/me/gaps/request", headers=hm, json={"key": mine[0]["key"], "space": "core"}
    )
    assert r.status_code == 202
    async with sessions() as s:
        n = (
            await s.execute(select(Notification).where(Notification.user_id == lead.user.id))
        ).scalar_one()
        e = (await s.execute(select(GapEvent).where(GapEvent.reason == "requested"))).scalar_one()
    assert n.kind == "sop_requested" and n.ref_id == str(e.id) and n.document_id is None
    await group_gaps(sessions, fake_query, None)
    gaps = (await client.get(f"{API}/spaces/core/gaps", headers=await sign_in(lead))).json()
    assert gaps[0]["reasons"] == {"requested": 1}


# --- coverage, stale, bus factor --------------------------------------------------------


async def test_coverage_titles_for_leads_counts_for_hr(indexed, client, make_user, sign_in):
    lead = await make_user(roles=LEAD)
    hr = await make_user(roles=HR)
    staff = await make_user(roles=STAFF)
    cells = (await client.get(f"{API}/reports/coverage", headers=await sign_in(lead))).json()
    sig = {c["stage"]: c for c in cells if "Signature Personal Brand Programme" in c["programme"]}
    assert sig["discovery"]["published"] >= 2 and sig["discovery"]["titles"]
    hr_cells = (await client.get(f"{API}/reports/coverage", headers=await sign_in(hr))).json()
    assert all(c["titles"] is None for c in hr_cells)
    assert [c["published"] for c in hr_cells] == [c["published"] for c in cells]
    gaps = [c for c in cells if c["published"] == 0]
    assert gaps  # e.g. Executive Presence has no strategy-stage SOP
    assert (
        await client.get(f"{API}/reports/coverage", headers=await sign_in(staff))
    ).status_code == 403


async def test_stale_list(indexed, sessions, client, make_user, sign_in):
    async with sessions() as s:
        doc = (
            (await s.execute(select(Document).where(Document.vault_path.like("Programmes/%"))))
            .scalars()
            .first()
        )
        doc.review_due = date.today() - timedelta(days=2)
        await s.commit()
    lead = await make_user(roles=LEAD)
    rows = (await client.get(f"{API}/spaces/core/stale", headers=await sign_in(lead))).json()
    assert {"document_id": str(doc.id), "overdue": True}.items() <= next(
        r for r in rows if r["document_id"] == str(doc.id)
    ).items()


async def test_bus_factor_flags_sole_authors_who_are_leaving(
    indexed, sessions, client, make_user, sign_in
):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    admin = await make_user(roles=("employee", "platform-admin"))
    hs, hl, hadm = await sign_in(staff), await sign_in(lead), await sign_in(admin)
    r = await client.post(
        f"{API}/notes",
        headers=hs,
        json={"title": "Venue walk-through", "space": "core", "body": "# Venue\n\nCheck exits."},
    )
    note = r.json()["id"]
    await ClassifierService(sessions, no_names).run_pending(limit=100)
    review = (await client.post(f"{API}/notes/{note}/submit", headers=hs)).json()["id"]
    assert (
        await client.post(f"{API}/reviews/{review}/approve", headers=hl, json={})
    ).status_code == 200
    r = await client.patch(
        f"{API}/admin/users/{staff.user.id}", headers=hadm, json={"leaving_on": "2027-01-31"}
    )
    assert r.status_code == 200 and r.json()["leaving_on"] == "2027-01-31"
    report = (await client.get(f"{API}/reports/bus-factor", headers=hl)).json()
    mine = next(i for i in report["single_author"] if i["document_id"] == note)
    assert mine["only_author"] == staff.user.display_name
    assert mine["author_leaving_on"] == "2027-01-31"
    assert report["leaving"][0]["name"] == staff.user.display_name
    assert (await client.get(f"{API}/reports/bus-factor", headers=hs)).status_code == 403


# --- conflicts --------------------------------------------------------------------------


class SaysConflict:
    def __init__(self):
        self.calls = 0

    async def chat(self, tier, *, system, messages, scope, json_mode=False, **_):
        self.calls += 1
        return ChatResult(
            '{"conflict": true, "explanation": "Different lead times."}',
            tier,
            "fake",
            "fake-model",
            "stop",
            Usage(),
            1,
        )


async def test_conflicts_checked_once_and_shown_to_leads(
    indexed, sessions, client, make_user, sign_in
):
    gw = SaysConflict()
    first = await detect_conflicts(sessions, gw, max_pairs=3, maxd=0.95)
    assert first["checked"] == 3 and gw.calls == 3
    again = await detect_conflicts(sessions, gw, max_pairs=3, maxd=0.95)
    assert gw.calls == 3 + again["checked"]  # new pairs only, never the same ones
    lead, staff = await make_user(roles=LEAD), await make_user(roles=("employee",))
    shown = (await client.get(f"{API}/reports/conflicts", headers=await sign_in(lead))).json()
    assert shown and shown[0]["explanation"] == "Different lead times."
    assert (await client.get(f"{API}/reports/conflicts", headers=await sign_in(staff))).json() == []
    r = await client.post(f"{API}/conflicts/{shown[0]['id']}/dismiss", headers=await sign_in(lead))
    assert r.status_code == 204
    async with sessions() as s:
        assert (await s.get(Conflict, uuid.UUID(shown[0]["id"]))).status == "dismissed"


# --- retract ----------------------------------------------------------------------------

PII = "Marisol Okonkwo-Brandt"


async def test_retract_value_everywhere_and_verify(
    indexed, sessions, client, make_user, sign_in, vault
):
    staff = await make_user(roles=STAFF)
    admin = await make_user(roles=("employee", "platform-admin"))
    hs, hadm = await sign_in(staff), await sign_in(admin)
    r = await client.post(
        f"{API}/notes",
        headers=hs,
        json={
            "title": "Client notes",
            "space": "core",
            "body": f"# Notes\n\nCall {PII} on Monday.",
        },
    )
    note = r.json()
    async with sessions() as s:
        conv = Conversation(user_id=staff.user.id, title=f"About {PII}")
        s.add(conv)
        await s.flush()
        s.add_all(
            [
                ChatMessage(conversation_id=conv.id, role="user", content=f"Who is {PII}?"),
                ChatMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=f"{PII} is a client.",
                    sections=[{"space": "core", "text": f"{PII} is a client."}],
                ),
                SearchEvent(user_id=staff.user.id, query=PII.lower(), results=0),
            ]
        )
        await s.commit()

    assert (
        await client.post(f"{API}/retractions", headers=hs, json={"value": PII})
    ).status_code == 403
    r = await client.post(f"{API}/retractions", headers=hadm, json={"value": PII})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["clean"] and sum(out["remaining"].values()) == 0
    assert out["documents"] == 1 and out["vault_files_with_term"] == 1  # owners must edit it
    assert out["redacted"]["messages"] == 2 and out["deleted"]["searches"] == 1

    async with sessions() as s:
        msgs = (await s.execute(select(ChatMessage))).scalars().all()
        assert all(PII not in m.content and PII not in json.dumps(m.sections) for m in msgs)
        assert await s.get(Document, uuid.UUID(note["id"])) is None
        rows = (await s.execute(select(Retraction))).scalars().all()
        assert all(PII not in json.dumps(x.result) for x in rows)
        assert {x.term_hash for x in rows} == {hashlib.sha256(PII.lower().encode()).hexdigest()}
        assert not any(
            PII in json.dumps(e.details) for e in (await s.execute(select(AuditEvent))).scalars()
        )
    # Re-indexing the unchanged file does not bring it back; editing it out does.
    report = await Indexer(vault, sessions, fake_embed).index_paths([note["vault_path"]])
    assert report.skipped == [note["vault_path"]]
    full = vault.root / note["vault_path"]
    full.write_text(full.read_text().replace(PII, "the client"))
    report = await Indexer(vault, sessions, fake_embed).index_paths([note["vault_path"]])
    assert report.indexed == [note["vault_path"]]


async def test_retract_document_removes_answers_that_cited_it(
    indexed, sessions, client, make_user, sign_in
):
    staff = await make_user(roles=STAFF)
    admin = await make_user(roles=("employee", "platform-admin"))
    async with sessions() as s:
        doc = (await s.execute(select(Document).where(Document.vault_path == RATE_CARD))).scalar()
        conv = Conversation(user_id=staff.user.id, title="pricing")
        s.add(conv)
        await s.flush()
        ans = ChatMessage(conversation_id=conv.id, role="assistant", content="The floor is X [1].")
        s.add(ans)
        await s.flush()
        s.add(MessageCitation(message_id=ans.id, space="core", n=1, document_id=doc.id))
        await s.commit()
    r = await client.post(
        f"{API}/retractions", headers=await sign_in(admin), json={"document_id": str(doc.id)}
    )
    assert r.json()["answers_removed"] == 1 and r.json()["clean"]
    async with sessions() as s:
        assert "removed" in (await s.get(ChatMessage, ans.id)).content


# --- retention --------------------------------------------------------------------------


async def test_retention_deletes_old_records_and_keeps_the_audit_chain(
    sessions, client, make_user, sign_in
):
    old = datetime.now(UTC) - timedelta(days=800)
    async with sessions() as s:
        prev = audit.GENESIS
        for action in ("old_one", "old_two"):
            h = audit.compute_hash(prev, old, None, action, None, None, {})
            s.add(AuditEvent(ts=old, action=action, details={}, prev_hash=prev, hash=h))
            prev = h
        await s.commit()
    admin = await make_user(roles=("employee", "platform-admin"))
    ha = await sign_in(admin)  # records recent audit events on top of the old ones
    async with sessions() as s:
        s.add(Conversation(user_id=admin.user.id, title="old", updated_at=old))
        s.add(Conversation(user_id=admin.user.id, title="new"))
        await s.commit()
    assert (await client.get(f"{API}/admin/audit/verify", headers=ha)).json()["ok"]

    out = await apply_retention(sessions, 24)
    assert out["conversations"] == 1 and out["audit_events"] == 2
    async with sessions() as s:
        titles = set((await s.execute(select(Conversation.title))).scalars())
        actions = set((await s.execute(select(AuditEvent.action))).scalars())
    assert titles == {"new"} and not {"old_one", "old_two"} & actions
    verify = (await client.get(f"{API}/admin/audit/verify", headers=ha)).json()
    assert verify["ok"], verify
    with pytest.raises(Exception, match="append-only"):
        async with sessions() as s:
            await s.execute(text("DELETE FROM audit_events"))
            await s.commit()


async def test_opened_results_but_used_none_is_a_personal_gap(
    indexed, sessions, client, make_user, sign_in
):
    me, other = await make_user(roles=STAFF), await make_user(roles=STAFF)
    hm, ho = await sign_in(me), await sign_in(other)
    r = await client.get(f"{API}/search", params={"q": "Discovery Workshop agenda"}, headers=hm)
    sid = r.json()["search_id"]
    assert r.json()["results"]
    assert (await client.get(f"{API}/me/gaps", headers=hm)).json() == []  # good results
    out = f"{API}/search/{sid}/outcome"
    assert (
        await client.post(out, headers=ho, json={"opened": 3, "used": False})
    ).status_code == 404
    assert (
        await client.post(out, headers=hm, json={"opened": 1, "used": False})
    ).status_code == 204
    assert (await client.get(f"{API}/me/gaps", headers=hm)).json() == []  # one look isn't a gap
    await client.post(out, headers=hm, json={"opened": 3, "used": False})
    mine = (await client.get(f"{API}/me/gaps", headers=hm)).json()
    assert len(mine) == 1 and mine[0]["count"] == 1
    # once something helped, it stays helped
    await client.post(out, headers=hm, json={"opened": 4, "used": True})
    await client.post(out, headers=hm, json={"opened": 4, "used": False})
    assert (await client.get(f"{API}/me/gaps", headers=hm)).json() == []
    async with sessions() as s:
        ev = await s.get(SearchEvent, uuid.UUID(sid))
        assert (ev.opened, ev.used) == (4, True)


class TwoModels:
    """8B flags every pair; the 14B (confirm tier) clears, flags or fails by turn."""

    def __init__(self, confirm_answers):
        self.config = type("C", (), {"tiers": {"background": None, "conflict-confirm": None}})()
        self.answers, self.calls = list(confirm_answers), []

    async def chat(self, tier, *, system, messages, scope, json_mode=False, **_):
        self.calls.append(tier)
        if tier == "background":
            text, model = '{"conflict": true, "explanation": "8B says so."}', "fake-8b"
        else:
            text, model = self.answers.pop(0), "fake-14b"
            if text is None:
                raise RuntimeError("14B not available")
        return ChatResult(text, tier, "fake", model, "stop", Usage(), 1)


async def test_conflicts_need_the_second_opinion_too(indexed, sessions):
    gw = TwoModels(
        ['{"conflict": false}', '{"conflict": true, "explanation": "Different owners."}', None]
    )
    report = await detect_conflicts(sessions, gw, max_pairs=3, maxd=0.95)
    # All 8B checks first, then the 14B on its flags: each model loads once.
    assert gw.calls == ["background"] * 3 + ["conflict-confirm"] * 3
    assert report == {"checked": 2, "conflicts": 1, "unconfirmed": 1}
    async with sessions() as s:
        q = select(Conflict.conflict, Conflict.model, Conflict.explanation)
        rows = (await s.execute(q)).all()
    assert sorted(rows) == [
        (False, "fake-8b → fake-14b", ""),
        (True, "fake-8b → fake-14b", "Different owners."),
    ]  # the failed second check is not stored, so the pair is tried again next night
    gw.answers = ['{"conflict": false}']
    again = await detect_conflicts(sessions, gw, max_pairs=1, maxd=0.95, max_confirms=0)
    assert again == {"checked": 0, "conflicts": 0, "unconfirmed": 1}  # over the cap: wait


async def test_checked_pairs_never_crowd_out_new_ones(indexed, sessions):
    # A tiny row limit: before the fix the closest (already checked) pairs filled
    # it on every run, so later pairs were never reached.
    gw = SaysConflict()
    seen = set()
    for _ in range(3):
        await detect_conflicts(sessions, gw, max_pairs=1, maxd=0.95, row_limit=2)
        async with sessions() as s:
            rows = (await s.execute(select(Conflict.document_a, Conflict.document_b))).all()
        seen = {tuple(r) for r in rows}
    assert gw.calls == 3 and len(seen) == 3
