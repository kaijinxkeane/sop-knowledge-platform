"""Phase 4 acceptance: SOP governance (plan §6).

Exit criterion: staff A edits an SOP -> lead B approves it in the platform ->
answers cite it "written by A, approved by B"; an edit after approval is not
cited until it is approved again.
"""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text

from app import clock
from app.agents.concierge import retrieve
from app.classify.service import ClassifierService
from app.db.models import (
    Document,
    Grant,
    Notification,
    Role,
    SopApproval,
    WebhookDelivery,
)
from app.db.scoped import apply_reader_scope
from app.governance import webhooks
from app.governance.jobs import review_reminders
from app.governance.versions import governed_hash
from app.identity import get_user, principal_for
from app.spaces import space_profiles
from app.vault.labels import vault_config
from tests.db.conftest import fake_query, no_names

API = "/api/v1"
SOP = "Programmes/Signature Personal Brand Programme/01 Discovery/Discovery Workshop SOP.md"
NEW_STEP = "Hand every participant a zebra-striped name card before the opening."
STAFF = ("employee", "core-staff")
LEAD = ("employee", "core-lead")


@pytest.fixture
async def reader_role(sessions):
    """Reads core internal SOPs, can't edit or review them."""
    async with sessions() as s:
        s.add(
            Role(
                name="core-reader",
                grants=[Grant(space="core", max_sensitivity="internal", actions=["ask"])],
            )
        )
        await s.commit()
    return ("employee", "core-reader")


async def doc_id(sessions, path=SOP):
    async with sessions() as s:
        return (await s.execute(select(Document.id).where(Document.vault_path == path))).scalar()


async def edit(client, h, note_id, change, sessions=None):
    src = (await client.get(f"{API}/notes/{note_id}/source", headers=h)).json()
    r = await client.put(
        f"{API}/notes/{note_id}",
        headers=h,
        json={"base_version": src["version"], "content": change(src["content"])},
    )
    assert r.status_code == 200, r.text
    if sessions is not None:
        # core is name-checked: a new version stays restricted until checked
        await ClassifierService(sessions, no_names).run_pending(limit=100)


async def answer_text(sessions, person, question="discovery workshop opening brand story"):
    """What the department agents would be given (approved text only)."""
    async with sessions() as s:
        principal = principal_for(await get_user(s, person.user.id))
    _, per_space = await retrieve(
        sessions, principal, question, await fake_query(question), space_profiles(), None
    )
    return [h for hs in per_space.values() for h in hs]


async def checked(sessions):
    await ClassifierService(sessions, no_names).run_pending(limit=100)


async def test_baseline_counts_published_notes_once(indexed, sessions):
    assert indexed.baseline > 0
    async with sessions() as s:
        docs = {d.vault_path: d for d in (await s.execute(select(Document))).scalars()}
        methods = set((await s.execute(select(SopApproval.method))).scalars())
    assert docs[SOP].approved_hash == docs[SOP].governed_hash
    assert docs[SOP].status == "published"
    assert docs[SOP].review_due is not None
    template = docs["Shared Templates/SOP Template.md"]  # no status: never approved
    assert template.approved_hash is None and template.status == "unreviewed"
    assert methods == {"baseline"}


async def test_edit_is_cited_only_after_approval(
    indexed, sessions, client, make_user, sign_in, reader_role, vault
):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    reader = await make_user(roles=reader_role)
    hs, hl, hr = await sign_in(staff), await sign_in(lead), await sign_in(reader)
    note = await doc_id(sessions)

    await edit(
        client,
        hs,
        note,
        lambda t: t.replace("## 2. Opening", f"{NEW_STEP}\n\n## 2. Opening"),
        sessions=sessions,
    )
    await checked(sessions)

    # Not cited yet: answers still use the approved version, for everyone.
    for who in (reader, staff, lead):
        passages = await answer_text(sessions, who)
        assert passages and not any("zebra" in h.text for h in passages)
        assert any(h.document_id == note for h in passages)
    # The reader's Library shows the approved version; the editor's shows the change.
    f = await client.get(f"{API}/documents/{note}/file", headers=hr)
    assert f.status_code == 200 and "zebra" not in f.text
    f = await client.get(f"{API}/documents/{note}/file", headers=hs)
    assert "zebra" in f.text
    found = (await client.get(f"{API}/search", params={"q": "zebra striped"}, headers=hr)).json()
    assert all(r["document_id"] != str(note) for r in found["results"])
    found = (await client.get(f"{API}/search", params={"q": "zebra striped"}, headers=hs)).json()
    assert any(r["document_id"] == str(note) for r in found["results"])
    meta = (await client.get(f"{API}/documents/{note}", headers=hs)).json()
    assert meta["approved"] and meta["pending_change"]
    assert not (await client.get(f"{API}/documents/{note}", headers=hr)).json()["pending_change"]

    # Staff A submits; lead B sees it with the diff and approves.
    r = await client.post(f"{API}/notes/{note}/submit", headers=hs)
    assert r.status_code == 201, r.text
    review = r.json()["id"]
    queue = (await client.get(f"{API}/reviews", headers=hl)).json()
    assert [q["id"] for q in queue] == [review] and not queue[0]["self_review"]
    d = (await client.get(f"{API}/notes/{note}/diff", headers=hl)).json()
    assert "+" + NEW_STEP in d["diff"] and d["added"] >= 1
    assert (await client.get(f"{API}/notes/{note}/diff", headers=hr)).status_code == 404
    # The Review screen shows exactly the submitted version against its base.
    sub, base = queue[0]["git_commit"], queue[0]["base_commit"]
    assert sub and base and sub != base
    v = await client.get(f"{API}/documents/{note}/versions/{sub}", headers=hl)
    assert v.status_code == 200 and NEW_STEP in v.json()["content"]
    v = await client.get(f"{API}/documents/{note}/versions/{base}", headers=hl)
    assert v.status_code == 200 and NEW_STEP not in v.json()["content"]
    assert (
        await client.get(f"{API}/documents/{note}/versions/{sub}", headers=hr)
    ).status_code == 404
    assert (
        await client.post(f"{API}/reviews/{review}/approve", headers=hs, json={})
    ).status_code == 403
    r = await client.post(f"{API}/reviews/{review}/approve", headers=hl, json={"comment": "ok"})
    assert r.status_code == 200 and r.json() == {"approval": "review"}
    await checked(sessions)

    passages = await answer_text(sessions, reader)
    cited = [h for h in passages if h.document_id == note]
    assert any("zebra" in h.text for h in cited)
    assert cited[0].provenance["written_by"] == staff.user.display_name
    assert cited[0].provenance["approved_by"] == lead.user.display_name
    assert cited[0].provenance["approval"] == "review"

    # Write-back: the approval is recorded in the note, and still holds.
    raw = (vault.root / SOP).read_text()
    assert f"approved_by: {lead.user.display_name}" in raw and "approved_on:" in raw
    async with sessions() as s:
        doc = await s.get(Document, note)
        assert doc.approved_hash == doc.governed_hash == governed_hash(SOP, raw.encode())
    # Notifications: B was asked to review, A heard it was approved.
    async with sessions() as s:
        kinds = {(n.user_id, n.kind) for n in (await s.execute(select(Notification))).scalars()}
    assert (lead.user.id, "review_requested") in kinds
    assert (staff.user.id, "sop_approved") in kinds


async def test_approval_covers_exactly_the_submitted_version(
    indexed, sessions, client, make_user, sign_in
):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    hs, hl = await sign_in(staff), await sign_in(lead)
    note = await doc_id(sessions)
    await edit(client, hs, note, lambda t: t + "\nFirst change.\n", sessions=sessions)
    review = (await client.post(f"{API}/notes/{note}/submit", headers=hs)).json()["id"]
    await edit(
        client, hs, note, lambda t: t + "\nSecond change, after submitting.\n", sessions=sessions
    )
    assert (await client.get(f"{API}/reviews/{review}", headers=hl)).json()["stale"]
    r = await client.post(f"{API}/reviews/{review}/approve", headers=hl, json={})
    assert r.status_code == 409
    # Typing approved_by / status by hand changes nothing that was approved.
    async with sessions() as s:
        before = (await s.get(Document, note)).governed_hash
    await edit(
        client,
        hs,
        note,
        lambda t: t.replace("status: published", "status: published\napproved_by: Someone"),
        sessions=sessions,
    )
    async with sessions() as s:
        assert (await s.get(Document, note)).governed_hash == before


async def test_self_approval_is_allowed_for_leads_and_recorded(
    indexed, sessions, client, make_user, sign_in
):
    lead = await make_user(roles=LEAD)
    hl = await sign_in(lead)
    note = await doc_id(sessions)
    await edit(client, hl, note, lambda t: t + "\nA lead's own change.\n", sessions=sessions)
    review = (await client.post(f"{API}/notes/{note}/submit", headers=hl)).json()
    assert review["self_review"]
    r = await client.post(f"{API}/reviews/{review['id']}/approve", headers=hl, json={})
    assert r.json() == {"approval": "self"}
    report = (await client.get(f"{API}/reports/governance", headers=hl)).json()
    assert str(note) in {i["document_id"] for i in report["self_approved"]}
    assert report["published_outside_platform"]  # the rest of the demo vault (baseline)


async def test_staff_cannot_publish_or_see_others_reports(
    indexed, sessions, client, make_user, sign_in
):
    staff = await make_user(roles=STAFF)
    hs = await sign_in(staff)
    note = await doc_id(sessions)
    await edit(client, hs, note, lambda t: t + "\nchange\n", sessions=sessions)
    async with sessions() as s:
        version = (await s.get(Document, note)).governed_hash
    r = await client.post(f"{API}/notes/{note}/approve", headers=hs, json={"version": version})
    assert r.status_code == 403
    assert (await client.get(f"{API}/reports/governance", headers=hs)).status_code == 403


async def test_unapproved_text_is_hidden_by_rls(indexed, sessions, client, make_user, sign_in):
    staff = await make_user(roles=STAFF)
    hs = await sign_in(staff)
    note = await doc_id(sessions)
    await edit(client, hs, note, lambda t: t + "\nQuokka protocol applies.\n", sessions=sessions)
    await checked(sessions)

    async def chunks(edit_spaces):
        async with sessions() as s, s.begin():
            await s.execute(text("SET LOCAL ROLE sop_reader"))
            await s.execute(
                text(
                    "SELECT set_config('sop.scopes', :sc, true), "
                    "set_config('sop.edit_spaces', :ed, true)"
                ),
                {"sc": json.dumps({"core": "internal"}), "ed": json.dumps(edit_spaces)},
            )
            return list(
                (
                    await s.execute(
                        text("SELECT text FROM chunks WHERE document_id = :d"), {"d": note}
                    )
                ).scalars()
            )

    assert not any("Quokka" in t for t in await chunks([]))
    assert await chunks([])  # the approved version is still readable
    assert any("Quokka" in t for t in await chunks(["core"]))


async def test_retired_notes_are_not_cited(indexed, sessions, client, make_user, sign_in):
    lead = await make_user(roles=LEAD)
    hl = await sign_in(lead)
    note = await doc_id(sessions)
    assert any(
        h.document_id == note for h in await answer_text(sessions, lead, "discovery workshop")
    )
    r = await client.post(f"{API}/notes/{note}/retire", headers=hl)
    assert r.status_code == 204, r.text
    await checked(sessions)
    assert not any(
        h.document_id == note for h in await answer_text(sessions, lead, "discovery workshop")
    )
    assert (await client.get(f"{API}/documents/{note}", headers=hl)).json()["status"] == "retired"


async def test_review_reminders_are_sent_once(indexed, sessions, make_user, monkeypatch):
    lead = await make_user(roles=LEAD)
    note = await doc_id(sessions)
    async with sessions() as s:
        doc = await s.get(Document, note)
        doc.review_due = clock.today() + timedelta(days=3)
        await s.commit()
    subs = (webhooks.Subscriber("https://hooks.example.com/x", webhooks.EVENTS),)
    monkeypatch.setattr(webhooks, "subscribers", lambda: subs)
    first = await review_reminders(sessions, vault_config())
    second = await review_reminders(sessions, vault_config())
    assert first["reminders"] >= 1 and second["reminders"] == 0
    async with sessions() as s:
        mine = (
            (await s.execute(select(Notification).where(Notification.user_id == lead.user.id)))
            .scalars()
            .all()
        )
        hooks = (await s.execute(select(WebhookDelivery))).scalars().all()
    assert [n.kind for n in mine] == ["review_due"]
    assert len(hooks) == 1 and set(hooks[0].payload) <= {
        "event",
        "document_id",
        "space",
        "due",
        "at",
    }


async def test_webhook_delivery_is_signed(sessions, monkeypatch):
    monkeypatch.setenv("HOOK_SECRET", "s3cret")
    async with sessions() as s:
        sub = webhooks.Subscriber("https://hooks.example.com/x", webhooks.EVENTS, "HOOK_SECRET")
        await webhooks.emit(s, "sop_published", subs=(sub,), document_id="d1", space="core")
        await s.commit()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        assert await webhooks.deliver_pending(sessions, client=c) == {"sent": 1, "failed": 0}
    body = seen[0].content
    assert seen[0].headers["X-SOP-Signature"] == webhooks.sign("s3cret", body)
    assert json.loads(body)["document_id"] == "d1"
    with pytest.raises(AssertionError):
        async with sessions() as s:
            await webhooks.emit(s, "sop_published", subs=(sub,), title="leaks content")


async def test_reader_scope_function_matches_python(indexed, sessions, make_user, reader_role):
    """sop_doc_wip_visible() and db.scoped.sees_latest agree for every document."""
    from app.db.scoped import sees_latest

    people = [await make_user(roles=r) for r in (STAFF, LEAD, reader_role, ("employee",))]
    async with sessions() as s:
        docs = (await s.execute(select(Document))).scalars().all()
        doc = next(d for d in docs if d.vault_path == SOP)
        doc.approved_hash = "x" * 64  # pretend there is an unapproved change
        await s.commit()
    for p in people:
        async with sessions() as s:
            principal = principal_for(await get_user(s, p.user.id))
        async with sessions() as s:
            await apply_reader_scope(s, principal)
            sql = dict(
                (await s.execute(text("SELECT id, sop_doc_wip_visible(id) FROM documents"))).all()
            )
            seen = {d.id: d for d in (await s.execute(select(Document))).scalars()}
            for doc_id_, d in seen.items():
                assert sql[doc_id_] == sees_latest(principal, d), (p.user.email, d.vault_path)
            await s.rollback()
