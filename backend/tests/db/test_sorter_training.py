"""The trained sorter in the real pipeline.

- it trains on documents people filed, and keeps fingerprints only
- its vote is stored with the proposal; a disagreement waits for a person
- a suggested folder is shown only to people who can file documents there
- once placed, an Inbox note can be filed where the folder gives the same access
"""

from sqlalchemy import select

from app.classify import service as classify_service
from app.classify.sorter import Vote
from app.classify.training import latest_sorter, train_sorter
from app.db.models import ClassificationProposal, Document, TrainedSorter
from app.policy.engine import Sensitivity
from tests.db.test_classifier import CEO, IT_LEAD, _queue, scripted

INT = Sensitivity.INTERNAL
IDEAS = "Inbox/workshop ideas.md"
PRINTER = "Inbox/printer jam fix.md"


async def _relabel(sessions, monkeypatch, votes):
    monkeypatch.setattr(classify_service, "predict", lambda _m, _v, *, _votes=votes: _votes.pop(0))
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
    await classify_service.ClassifierService(sessions, scripted, use_sorter=True).run_pending(
        limit=100
    )


async def _proposal(sessions, path):
    async with sessions() as s:
        return (
            await s.execute(
                select(ClassificationProposal)
                .join(Document, Document.id == ClassificationProposal.document_id)
                .where(Document.vault_path == path, ClassificationProposal.status == "pending")
            )
        ).scalar_one()


async def test_trains_on_filed_documents_and_keeps_fingerprints_only(indexed, sessions):
    summary = await train_sorter(sessions)
    assert summary["documents"] > 20 and summary["departments"] == 3
    async with sessions() as s:
        rows = (await s.execute(select(TrainedSorter))).scalars().all()
        assert len(rows) == 1
        model = await latest_sorter(s)
        titles = {d.title for d in (await s.execute(select(Document))).scalars()}
    assert set(rows[0].data) == {"n", "spaces", "levels", "folders"}
    assert not any(t in str(rows[0].data) for t in titles if len(t) > 12)  # no text
    assert set(model.spaces) == {"core", "hr", "it"}
    assert not any(f.startswith(("Inbox", "Help")) for f in model.folders)
    await train_sorter(sessions)  # retraining replaces it
    async with sessions() as s:
        assert len((await s.execute(select(TrainedSorter))).scalars().all()) == 1


async def test_vote_is_stored_and_disagreement_waits(indexed, sessions, monkeypatch):
    await train_sorter(sessions)
    # sorted order of Inbox paths: meeting notes, printer, untitled, workshop ideas
    votes = [
        None,
        Vote("core", 0.9, INT, "Methodology"),
        None,
        Vote("core", 0.9, INT, "Programmes"),
    ]
    await _relabel(sessions, monkeypatch, votes)
    printer = await _proposal(sessions, PRINTER)
    assert printer.sorter_vote["space"] == "core" and printer.suggested_folder is None
    assert printer.confidence < 0.7 and "disagrees" in printer.rationale
    ideas = await _proposal(sessions, IDEAS)
    assert ideas.suggested_folder == "Programmes"


async def test_folder_suggestion_only_for_people_who_can_file_there_then_filing(
    indexed, sessions, monkeypatch, client, make_user, sign_in
):
    await train_sorter(sessions)
    votes = [None, Vote("it", 0.9, INT, "IT"), None, Vote("core", 0.9, INT, "Programmes")]
    await _relabel(sessions, monkeypatch, votes)
    ceo = await sign_in(await make_user(roles=CEO))
    queue = await _queue(client, ceo)
    assert queue[IDEAS]["suggested_folder"] == "Programmes"
    assert queue[PRINTER]["suggested_folder"] is None  # the CEO can't file in IT/
    it = await sign_in(await make_user(roles=IT_LEAD))
    assert PRINTER not in await _queue(client, it)  # unplaced: triage only, as before

    move = "/api/v1/library/documents/{}/move"
    doc_id = queue[IDEAS]["document_id"]
    # not placed yet: nobody can read it, so it isn't there to file
    assert (
        await client.post(move.format(doc_id), json={"folder": "Programmes"}, headers=ceo)
    ).status_code == 404
    r = await client.post(f"/api/v1/classifications/{queue[IDEAS]['id']}/approve", headers=ceo)
    assert r.status_code == 204, r.text
    # Public/ would give everyone access: refused; Programmes/ is the same access
    r = await client.post(move.format(doc_id), json={"folder": "Public"}, headers=ceo)
    assert r.status_code == 409
    r = await client.post(move.format(doc_id), json={"folder": "Programmes"}, headers=ceo)
    assert r.status_code == 200, r.text
    assert r.json()["vault_path"] == "Programmes/workshop ideas.md"
    # and it can't go back into the Inbox
    r = await client.post(move.format(doc_id), json={"folder": "Inbox"}, headers=ceo)
    assert r.status_code == 422
