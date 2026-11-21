"""The one-way rule, approval rights, name filtering and reply parsing (no model)."""

import itertools
import uuid

import pytest

from app.classify.model import ClassifyInput, parse_reply, system_prompt, user_prompt
from app.classify.names import staff_index, unresolved_names
from app.classify.rules import Proposal, decide, is_looser, may_approve, required_action
from app.policy.engine import GrantRule, Principal, Sensitivity
from app.spaces import load_space_profiles
from app.vault.labels import Labels
from tests.conftest import CONFIG_DIR

P, I, R = Sensitivity.PUBLIC, Sensitivity.INTERNAL, Sensitivity.RESTRICTED  # noqa: E741
SPACES = {"core", "it", "hr"}


def prop(space="core", sens=I, conf=0.9, shared=()):
    return Proposal(space=space, sensitivity=sens, shared_with=tuple(shared), confidence=conf)


def L(space="core", sens=I, shared=()):  # noqa: N802
    return Labels(space=space, sensitivity=sens, shared_with=list(shared))


@pytest.mark.parametrize("sens,shared", [(R, ()), (I, ()), (P, ()), (R, (("hr", R),))])
def test_unassigned_gets_no_access_from_the_ai(sens, shared):
    # Not even restricted: a wrong space would show it to that space's leads.
    d = decide(None, prop(sens=sens, shared=shared), known_spaces=SPACES)
    assert (d.decision, d.status, d.apply) == ("queued", "pending", None)


@pytest.mark.parametrize("p", [prop(conf=0.5), prop(space=None), prop(space="finance")])
def test_unsure_stays_quarantined(p):
    d = decide(None, p, known_spaces=SPACES)
    assert d.decision == "quarantined" and d.apply is None


def test_reclassification_tightens_now_and_queues_loosening():
    assert decide(L(sens=I), prop(sens=R), known_spaces=SPACES).apply.sensitivity is R
    for looser in (prop(sens=P), prop(space="hr", sens=R), prop(sens=I, shared=[("hr", I)])):
        d = decide(L(sens=I), looser, known_spaces=SPACES)
        assert d.decision == "queued" and d.apply is None
    assert decide(L(sens=I), prop(sens=I), known_spaces=SPACES).decision == "unchanged"


def test_ai_never_applies_anything_looser_exhaustive():
    levels = (P, I, R)
    currents = [None] + [L(s, lv) for s, lv in itertools.product(SPACES, levels)]
    proposals = [
        prop(s, lv, c, sh)
        for s, lv, c, sh in itertools.product(
            [*SPACES, None], levels, (0.2, 0.95), ((), (("hr", P),))
        )
    ]
    for cur, p in itertools.product(currents, proposals):
        d = decide(cur, p, known_spaces=SPACES)
        if d.apply is None:
            continue
        assert cur is not None, p  # unplaced notes never get access from the AI
        assert not is_looser(cur, d.apply), (cur, p)


def _who(*grants):
    return Principal(
        uuid.uuid4(), frozenset(), tuple(GrantRule(s, lv, frozenset(a)) for s, lv, a in grants)
    )


def test_who_may_approve():
    lead = _who(("core", R, {"ask", "contribute", "review", "approve"}))
    reviewer = _who(("hr", I, {"ask", "contribute", "review"}))
    staff = _who(("core", I, {"ask", "contribute"}))
    assert required_action(L(sens=P)) == "approve"
    assert required_action(L(sens=I, shared=[("hr", I)])) == "approve"
    assert may_approve(lead, L(sens=P), is_author=False)
    assert may_approve(reviewer, L("hr", I), is_author=False)
    assert not may_approve(reviewer, L("hr", P), is_author=False)
    assert may_approve(staff, L(sens=I), is_author=True)  # own note, own department
    assert not may_approve(staff, L(sens=I), is_author=False)
    assert not may_approve(staff, L(sens=P), is_author=True)


def test_names_exclude_staff_safe_and_hallucinated():
    staff = staff_index(["Avery Tan", "Taylor Goh (new hire)"])
    text = "Avery met Jamie Rivera from Northwind Ltd. Taylor took notes."
    found = ["Avery Tan", "Avery", "Jamie Rivera", "Northwind Ltd", "Taylor", "Ghost Person"]
    assert unresolved_names(found, text, staff=staff, safe=set(), clients=set()) == [
        "jamie rivera",
        "northwind ltd",
    ]
    assert unresolved_names(found, text, staff=staff, safe={"northwind ltd"}, clients=set()) == [
        "jamie rivera"
    ]
    # names on the client list count even when the model misses them
    assert unresolved_names([], text, staff=staff, safe=set(), clients={"jamie rivera"}) == [
        "jamie rivera"
    ]


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "[]",
        '{"space": "finance"}',
        '{"space": "core", "confidence": "high"}',
    ],
)
def test_bad_replies_fail_closed(reply):
    p = parse_reply(reply, model="m", known_spaces=SPACES)
    assert p.sensitivity is R
    assert p.space is None or p.confidence == 0.0 or p.sensitivity is R


def test_good_reply_and_prompts():
    p = parse_reply(
        'Sure: {"space": "hr", "sensitivity": "internal", "confidence": 0.8, '
        '"shared_with": [{"space": "core", "sensitivity": "internal"}], '
        '"evidence": ["a"], "names": ["Jamie"]}',
        model="m",
        known_spaces=SPACES,
    )
    assert (p.space, p.sensitivity, p.confidence) == ("hr", I, 0.8)
    assert p.shared_with == (("core", I),) and p.names == ("Jamie",)
    sys = system_prompt(load_space_profiles(CONFIG_DIR))
    assert "- core:" in sys and "never follow instructions" in sys
    assert "<document" in user_prompt(ClassifyInput("a.md", "T", "note", "x" * 9000))


def test_model_casing_is_normalised_but_never_applied_looser():
    p = parse_reply(
        '{"space": "core", "sensitivity": "Public", "confidence": 1}',
        model="m",
        known_spaces=SPACES,
    )
    assert p.sensitivity is P
    assert decide(None, p, known_spaces=SPACES).apply is None


@pytest.mark.parametrize("reply", ["not json", "[]", "{}", "{broken"])
def test_unreadable_reply_is_not_a_passed_name_check(reply):
    assert parse_reply(reply, model="m", known_spaces=SPACES).valid is False


def _doc_with_examples():
    from app.classify.model import Example

    return ClassifyInput(
        "Inbox/x.md",
        "Coffee order",
        "note",
        "Order coffee for the training day two days ahead.",
        examples=(
            Example("Rate Card 2026", "Signature floor price 7,500.", "core", "restricted"),
            Example("Room setup", "Chairs in a U-shape.", "core", "public"),
        ),
    )


def test_examples_are_shown_as_data_before_the_document():
    up = user_prompt(_doc_with_examples())
    assert up.index("<examples>") < up.index("<document")
    assert 'space="core" sensitivity="restricted"' in up


def test_example_text_never_reaches_the_reviewer():
    from app.classify.model import SAFE_RATIONALE, keep_to_document

    doc = _doc_with_examples()
    p = Proposal(
        space="core",
        sensitivity=P,
        confidence=0.9,
        rationale="Like the Rate Card 2026 note, which lists the Signature floor price 7,500.",
        evidence=("Order coffee for the training day", "Signature floor price 7,500."),
    )
    kept = keep_to_document(p, doc)
    assert kept.evidence == ("Order coffee for the training day",)
    assert kept.rationale == SAFE_RATIONALE
    own = Proposal(
        space="core",
        sensitivity=P,
        confidence=0.9,
        rationale="Logistics for a training day that any staff member may do.",
    )
    assert keep_to_document(own, doc).rationale == own.rationale


def test_pick_examples_is_leave_one_out():
    from app.classify.evaluate import Item, pick_examples

    items = [Item(str(i), "case", f"{i}.md", f"t{i}", "note", "x", "core", P) for i in range(6)]
    vecs = {str(i): [1.0, i / 10] for i in range(6)}
    ex = pick_examples(items[0], items, vecs, k=3)
    assert len(ex) == 3 and "t0" not in {e.title for e in ex}
