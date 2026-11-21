"""Phase 2b acceptance (with a scripted fake model; the real one is in eval-classifier):

- core notes stay restricted until the name check has run
- the AI applies `restricted` by itself, anything looser waits in the queue
- the queue shows each proposal only to people who could read the note
- approvals follow who-may-approve-what; personal data can't be loosened
- a stale proposal (note changed) can't be approved
- a looser re-classification after an edit doesn't take effect without approval
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.classify.rules import Proposal
from app.classify.service import ClassifierService
from app.db.models import ClassificationProposal, Document
from app.policy.engine import Sensitivity
from app.vault.indexer import Indexer
from tests.db.conftest import _git, fake_embed

P, I, R = Sensitivity.PUBLIC, Sensitivity.INTERNAL, Sensitivity.RESTRICTED  # noqa: E741
SCRIPT = {
    "Inbox/printer jam fix.md": ("it", P, 0.9, ()),
    "Inbox/workshop ideas.md": ("core", I, 0.85, ()),
    "Inbox/untitled.md": (None, R, 0.2, ()),
    "Inbox/meeting notes 2026-10-14.md": ("core", R, 0.95, ("Jamie Rivera", "Avery Tan")),
}
EMPLOYEE = ("employee",)
CORE_STAFF = ("employee", "core-staff")
CEO = ("employee", "core-lead")
IT_LEAD = ("employee", "it-lead")


async def scripted(doc):
    space, sens, conf, names = SCRIPT.get(doc.vault_path, (None, R, 0.0, ()))
    return Proposal(
        space=space,
        sensitivity=sens,
        confidence=conf,
        names=names,
        rationale="scripted",
        evidence=("quote",),
        model="fake",
    )


@pytest.fixture
async def classified(vault, sessions, client, indexed):
    # `indexed` ran the no-names fake; now script the Inbox proposals
    async with sessions() as s:
        for d in (await s.execute(select(Document))).scalars():
            if d.vault_path.startswith("Inbox/"):
                await s.execute(
                    ClassificationProposal.__table__.delete().where(
                        ClassificationProposal.document_id == d.id
                    )
                )
                d.name_check_hash = None
        await s.commit()
    await ClassifierService(sessions, scripted).run_pending(limit=100)
    return vault


async def _titles(client, h):
    return {d["vault_path"] for d in (await client.get("/api/v1/documents", headers=h)).json()}


async def _queue(client, h):
    groups = (await client.get("/api/v1/classifications/queue", headers=h)).json()
    return {i["vault_path"]: i for g in groups for i in g["items"]}


async def test_core_notes_wait_for_the_name_check(vault, sessions, client, make_user, sign_in):
    await Indexer(vault, sessions, fake_embed).sync()
    h = await sign_in(await make_user(roles=CORE_STAFF))
    assert not [p for p in await _titles(client, h) if p.startswith("Programmes/")]

    async def none(doc):
        return Proposal(space=None, sensitivity=R, model="fake")

    await ClassifierService(sessions, none).run_pending(limit=100)
    assert [p for p in await _titles(client, h) if p.startswith("Programmes/")]


async def test_one_way_rule_on_first_run(classified, sessions):
    async with sessions() as s:
        rows = {
            d.vault_path: (d, [(a.space, a.sensitivity) for a in d.access])
            for d in (await s.execute(select(Document))).scalars()
            if d.vault_path.startswith("Inbox/")
        }
        props = {
            p.document_id: p for p in (await s.execute(select(ClassificationProposal))).scalars()
        }

    def info(path):
        doc, access = rows[path]
        return props[doc.id].decision, access, doc

    # Unplaced notes get no access from the AI, whatever it proposes.
    assert info("Inbox/printer jam fix.md")[:2] == ("queued", [])
    assert info("Inbox/untitled.md")[:2] == ("quarantined", [])
    decision, access, doc = info("Inbox/meeting notes 2026-10-14.md")
    assert decision == "queued" and access == []
    assert doc.name_hits == ["jamie rivera"]  # staff name Avery Tan was dropped
    # no space yet, so no name flag; the hits are kept and flag it once placed
    assert {"email", "phone"} <= set(doc.safeguards)


async def test_unplaced_proposals_go_to_triage_not_the_proposed_space(
    classified, client, make_user, sign_in
):
    # The proposed space's reviewers never see an unplaced note's quotes: the AI
    # may have picked the wrong space (author unknown here, so the triage lead).
    assert await _queue(client, await sign_in(await make_user(roles=EMPLOYEE))) == {}
    assert await _queue(client, await sign_in(await make_user(roles=CORE_STAFF))) == {}
    assert await _queue(client, await sign_in(await make_user(roles=IT_LEAD))) == {}
    ceo = await _queue(client, await sign_in(await make_user(roles=CEO)))
    assert set(ceo) == set(SCRIPT)
    assert ceo["Inbox/workshop ideas.md"]["needs"] == "review"
    assert ceo["Inbox/printer jam fix.md"]["needs"] == "approve"  # public = lead only


async def test_triage_places_then_the_space_decides(classified, client, make_user, sign_in):
    reader = await sign_in(await make_user(roles=EMPLOYEE))
    assert "Inbox/printer jam fix.md" not in await _titles(client, reader)
    ceo = await sign_in(await make_user(roles=CEO))
    pid = (await _queue(client, ceo))["Inbox/printer jam fix.md"]["id"]
    # the CEO can't approve IT public: approving places it at it/restricted
    r = await client.post(f"/api/v1/classifications/{pid}/approve", headers=ceo)
    assert r.status_code == 204, r.text
    assert "Inbox/printer jam fix.md" not in await _titles(client, reader)
    assert "Inbox/printer jam fix.md" not in await _queue(client, ceo)
    it = await sign_in(await make_user(roles=IT_LEAD))
    item = (await _queue(client, it))["Inbox/printer jam fix.md"]
    assert item["decision"] == "forwarded" and item["current"]["sensitivity"] == "restricted"
    r = await client.post(f"/api/v1/classifications/{item['id']}/approve", headers=it)
    assert r.status_code == 204, r.text
    assert "Inbox/printer jam fix.md" in await _titles(client, reader)
    again = await client.post(f"/api/v1/classifications/{item['id']}/approve", headers=it)
    assert again.status_code == 409


async def test_staff_cannot_approve_and_personal_data_stays_restricted(
    classified, client, make_user, sign_in, sessions
):
    ceo = await sign_in(await make_user(roles=CEO))
    q = await _queue(client, ceo)
    staff = await sign_in(await make_user(roles=CORE_STAFF))
    pid = q["Inbox/workshop ideas.md"]["id"]
    assert (
        await client.post(f"/api/v1/classifications/{pid}/approve", headers=staff)
    ).status_code == 404  # can't even see it
    pid = q["Inbox/meeting notes 2026-10-14.md"]["id"]
    r = await client.post(
        f"/api/v1/classifications/{pid}/approve",
        headers=ceo,
        json={"space": "core", "sensitivity": "internal"},
    )
    assert r.status_code == 422 and "personal data" in r.json()["detail"]


async def test_edit_on_approval_and_bulk(classified, client, make_user, sign_in):
    ceo = await sign_in(await make_user(roles=CEO))
    q = await _queue(client, ceo)
    ideas, untitled = q["Inbox/workshop ideas.md"]["id"], q["Inbox/untitled.md"]["id"]
    r = await client.post(
        f"/api/v1/classifications/{untitled}/approve",
        headers=ceo,
        json={"space": "core", "sensitivity": "internal"},
    )
    assert r.status_code == 204, r.text
    r = await client.post(
        "/api/v1/classifications/bulk-approve", headers=ceo, json={"ids": [ideas, untitled]}
    )
    assert [x["ok"] for x in r.json()] == [True, False]  # untitled already decided
    staff = await sign_in(await make_user(roles=CORE_STAFF))
    assert {"Inbox/workshop ideas.md", "Inbox/untitled.md"} <= await _titles(client, staff)


async def test_stale_proposal_and_looser_reclassification(
    classified, client, make_user, sign_in, sessions
):
    ceo = await sign_in(await make_user(roles=CEO))
    pid = (await _queue(client, ceo))["Inbox/workshop ideas.md"]["id"]
    note = classified.root / "Inbox/workshop ideas.md"
    note.write_text(note.read_text() + "\nOne more idea.\n")
    _git(
        classified.root,
        "-c",
        "user.name=A",
        "-c",
        "user.email=a@example.com",
        "commit",
        "-qam",
        "edit",
    )
    await Indexer(classified, sessions, fake_embed).sync()
    r = await client.post(f"/api/v1/classifications/{pid}/approve", headers=ceo)
    assert r.status_code == 409

    # approve the fresh proposal at internal, then an edit makes the AI say public
    await ClassifierService(sessions, scripted).run_pending(limit=100)
    pid = (await _queue(client, ceo))["Inbox/workshop ideas.md"]["id"]
    assert (
        await client.post(f"/api/v1/classifications/{pid}/approve", headers=ceo)
    ).status_code == 204
    SCRIPT["Inbox/workshop ideas.md"] = ("core", P, 0.95, ())
    try:
        note.write_text(note.read_text() + "\nAnd another.\n")
        _git(
            classified.root,
            "-c",
            "user.name=A",
            "-c",
            "user.email=a@example.com",
            "commit",
            "-qam",
            "edit 2",
        )
        await Indexer(classified, sessions, fake_embed).sync()
        await ClassifierService(sessions, scripted).run_pending(limit=100)
    finally:
        SCRIPT["Inbox/workshop ideas.md"] = ("core", I, 0.85, ())
    item = (await _queue(client, ceo))["Inbox/workshop ideas.md"]
    assert item["decision"] == "queued" and item["current"]["sensitivity"] == "internal"
    reader = await sign_in(await make_user(roles=EMPLOYEE))
    assert "Inbox/workshop ideas.md" not in await _titles(client, reader)


async def test_names_review(classified, client, make_user, sign_in, sessions):
    ceo = await sign_in(await make_user(roles=CEO))
    pid = (await _queue(client, ceo))["Inbox/meeting notes 2026-10-14.md"]["id"]
    r = await client.post(f"/api/v1/classifications/{pid}/approve", headers=ceo)
    assert r.status_code == 204, r.text  # placed at core/restricted first
    async with sessions() as s:
        doc_id = await s.scalar(
            select(Document.id).where(Document.vault_path == "Inbox/meeting notes 2026-10-14.md")
        )
        assert "names_unconfirmed" in (await s.get(Document, doc_id)).safeguards
    r = await client.post(
        f"/api/v1/documents/{doc_id}/names", headers=ceo, json={"safe": ["someone else"]}
    )
    assert r.status_code == 422
    r = await client.post(
        f"/api/v1/documents/{doc_id}/names", headers=ceo, json={"client": ["Jamie Rivera"]}
    )
    assert r.status_code == 204
    staff = await sign_in(await make_user(roles=CORE_STAFF))
    r = await client.post(
        f"/api/v1/documents/{doc_id}/names", headers=staff, json={"safe": ["jamie rivera"]}
    )
    assert r.status_code == 404


async def test_moving_a_placed_note_is_not_shown_to_the_target_space(
    classified, client, make_user, sign_in, sessions
):
    ceo = await sign_in(await make_user(roles=CEO))
    pid = (await _queue(client, ceo))["Inbox/workshop ideas.md"]["id"]
    assert (
        await client.post(f"/api/v1/classifications/{pid}/approve", headers=ceo)
    ).status_code == 204  # now core/internal
    async with sessions() as s:
        doc = (
            await s.execute(
                select(Document).where(Document.vault_path == "Inbox/workshop ideas.md")
            )
        ).scalar_one()
        s.add(
            ClassificationProposal(
                document_id=doc.id,
                content_hash=doc.content_hash,
                proposed_space="hr",
                proposed_sensitivity="internal",
                confidence=0.9,
                model="fake",
                status="pending",
                decision="queued",
                group_key="Inbox|hr|internal",
            )
        )
        await s.commit()
    hr = await sign_in(await make_user(roles=("employee", "hr-staff", "hr-lead")))
    assert "Inbox/workshop ideas.md" not in await _queue(client, hr)
    moved = (await _queue(client, ceo))["Inbox/workshop ideas.md"]
    assert moved["proposed"]["space"] == "hr"
    r = await client.post(f"/api/v1/classifications/{moved['id']}/approve", headers=ceo)
    assert r.status_code == 403  # the CEO can't place things in HR


async def test_examples_come_only_from_notes_people_labelled(classified, sessions):
    from app.classify.service import similar_labelled

    async with sessions() as s:
        inbox = (
            (await s.execute(select(Document).where(Document.vault_path.like("Inbox/%"))))
            .scalars()
            .all()
        )
        by_title = {d.title: d for d in (await s.execute(select(Document))).scalars()}
        seen = 0
        for doc in inbox:
            for e in await similar_labelled(s, doc.id):
                src = by_title[e.title]
                assert src.id != doc.id
                assert src.label_source in ("frontmatter", "folder_rule", "approved_ai")
                seen += 1
    assert seen > 0
