"""Answer reuse (plan §5.2 lever 5): same question + same approved passages ->
the stored answer, never across access, invalidated by any change."""

# ruff: noqa: F811  (the `model` fixture is shared from test_chat)
from __future__ import annotations

import uuid

from sqlalchemy import func, select, text

from app.agents import reuse
from app.agents.department import Section
from app.db.models import AnswerReuse, AuditEvent
from app.retention.retract import retract_document
from tests.db.test_chat import CEO, CORE_STAFF, NEW_HIRE, ask, model  # noqa: F401

Q = "How long does the Discovery Workshop last?"


def answered(rec) -> int:
    """Department answer calls (router calls carry no <sources>)."""
    return sum("<sources>" in p for p in rec.prompts)


def section(events, space="core"):
    return next(d for e, d in events if e == "section_done" and d["space"] == space)


async def test_same_question_same_passages_is_reused(model, sessions, client, make_user, sign_in):
    a, b = (
        await sign_in(await make_user(roles=CORE_STAFF)),
        await sign_in(await make_user(roles=CORE_STAFF)),
    )
    _, first = await ask(client, a, Q)
    assert answered(model) == 1 and section(first)["reused"] is False
    # someone else with the same access, written differently
    _, second = await ask(client, b, "  how long does the discovery   workshop last ")
    assert answered(model) == 1  # no model call
    sec = section(second)
    assert sec["reused"] is True and sec["confidence"] == "high"
    tokens = "".join(d["text"] for e, d in second if e == "token")
    assert "The SOP says so" in tokens
    cites = [d for e, d in second if e == "citation"]
    assert cites and cites == [d for e, d in first if e == "citation"]
    async with sessions() as s:
        row = (await s.execute(select(AnswerReuse))).scalar_one()
        assert row.hits == 1
        last = (
            (
                await s.execute(
                    select(AuditEvent)
                    .where(AuditEvent.action == "question_answered")
                    .order_by(AuditEvent.id.desc())
                )
            )
            .scalars()
            .first()
        )
        assert last.details["reused"] == ["core"]


async def test_never_reused_across_different_access(model, client, make_user, sign_in):
    """The CEO's retrieval includes restricted passages; staff's doesn't, so the
    prompts differ and so do the keys."""
    ceo, staff = (
        await sign_in(await make_user(roles=CEO)),
        await sign_in(await make_user(roles=NEW_HIRE)),
    )
    q = "What is the floor price for the Signature programme?"
    await ask(client, ceo, q)
    n = answered(model)
    _, events = await ask(client, staff, q)
    sec = section(events) if any(e == "section_done" for e, _ in events) else None
    assert sec is None or sec["reused"] is False
    joined = "".join(d.get("text", "") for e, d in events if e == "token")
    assert "7,500" not in joined
    assert answered(model) >= n  # staff got their own answer (or none)


async def test_a_changed_sop_is_a_new_answer(model, sessions, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=CORE_STAFF))
    _, events = await ask(client, h, Q)
    doc = next(d for e, d in events if e == "citation")["document_id"]
    async with sessions() as s:
        # a new approved version: different text and commit for the cited passage
        await s.execute(
            text("UPDATE chunks SET text = text || ' Updated.' WHERE document_id = :d"),
            {"d": doc},
        )
        await s.commit()
    _, again = await ask(client, h, Q)
    assert answered(model) == 2 and section(again)["reused"] is False


async def test_not_helpful_and_retract_remove_it(model, sessions, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=CORE_STAFF))
    _, events = await ask(client, h, Q)
    msg = next(d for e, d in events if e == "done")["message_id"]
    r = await client.post(f"/api/v1/messages/{msg}/feedback", headers=h, json={"helpful": False})
    assert r.status_code == 204
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(AnswerReuse)) == 0
    _, events = await ask(client, h, Q)
    assert answered(model) == 2 and section(events)["reused"] is False
    doc = uuid.UUID(next(d for e, d in events if e == "citation")["document_id"])
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(AnswerReuse)) == 1
        admin = (await s.execute(text("SELECT id FROM users LIMIT 1"))).scalar()
        await retract_document(s, doc, admin)
        await s.commit()
        assert await s.scalar(select(func.count()).select_from(AnswerReuse)) == 0


async def test_off_switch_and_what_is_never_stored(
    model, sessions, client, make_user, sign_in, monkeypatch
):
    monkeypatch.setattr(reuse, "reuse_days", lambda: 0)
    h = await sign_in(await make_user(roles=CORE_STAFF))
    await ask(client, h, Q)
    await ask(client, h, Q)
    assert answered(model) == 2
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(AnswerReuse)) == 0
    ok = Section(space="core", text="x [1]", passages=[object()])
    assert reuse._storable(ok)
    for bad in (
        {"error": "Timeout"},
        {"fallback_from": "answer"},
        {"dropped_lines": 1},
        {"invalid_citations": 1},
        {"passages": []},
    ):
        s = Section(space="core", text="x [1]", passages=[object()])
        for k, v in bad.items():
            setattr(s, k, v)
        assert not reuse._storable(s), bad
