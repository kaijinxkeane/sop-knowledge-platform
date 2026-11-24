"""Conflict-check eval: the labelled sets and the scoring (no model needed)."""

from __future__ import annotations

import re

import pytest

from app.config import REPO_ROOT
from app.eval.conflicts import SETS, Item, candidates, evaluate, load_items, search_recall
from app.models.types import ChatResult, ContentScope, Usage
from app.retention.conflicts import SYSTEM

EVAL_DIR = REPO_ROOT / "config" / "eval"
# Fictional data only: no emails, phone numbers, NRIC-like ids or links.
REAL_DATA = re.compile(r"@|https?://|\b[STFG]\d{7}[A-Z]\b|\b[689]\d{3}\s?\d{4}\b")


@pytest.mark.parametrize("name", SETS.values())
def test_sets_are_balanced_and_fictional(name):
    items = load_items(EVAL_DIR / name)
    conflicts = [i for i in items if i.conflict]
    assert len(conflicts) == len(items) - len(conflicts), "half conflicts, half not"
    assert {i.kind for i in conflicts} <= {
        "number",
        "deadline",
        "owner",
        "order",
        "rule",
        "tool",
        "buried",
        "implicit",
    }
    assert {i.kind for i in items if not i.conflict} <= {
        "detail",
        "situation",
        "reworded",
        "exception",
        "long",
        "equivalent",
    }
    for i in items:
        for text in (i.title_a, i.text_a, i.title_b, i.text_b):
            assert not REAL_DATA.search(text), f"{i.id} looks like real data"


def test_sets_do_not_overlap():
    sets = [load_items(EVAL_DIR / n) for n in SETS.values()]
    for x, a in enumerate(sets):
        for b in sets[x + 1 :]:
            assert not {i.id for i in a} & {i.id for i in b}
            assert not {(i.text_a, i.text_b) for i in a} & {(i.text_a, i.text_b) for i in b}


def test_cascade_needs_both_stages_to_flag():
    from app.eval.conflicts import Result, Trial, cascade

    def run(model, verdicts):
        trials = [
            Trial(item, 0, "number" if want else "detail", want, got, 1.0, model)
            for item, (want, got) in verdicts.items()
        ]
        return Result(model, "dev", trials).to_json()

    first = run(
        "8b", {"c1": (True, True), "c2": (True, True), "n1": (False, True), "n2": (False, False)}
    )
    confirm = run(
        "14b", {"c1": (True, True), "c2": (True, False), "n1": (False, False), "n2": (False, True)}
    )
    result = cascade(first, confirm)
    got = {t.item: t.got for t in result.trials}
    # n2: cleared by the first stage, so the confirm model's flag is never asked for
    assert got == {"c1": True, "c2": False, "n1": False, "n2": False}
    assert result.model == "8b → 14b"
    flagged = next(t for t in result.trials if t.item == "c1")
    assert flagged.seconds == 2.0 and flagged.explanation == "14b"


class Scripted:
    """Answers per item, by the first passage's title; records what it was sent."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    async def chat(self, tier, *, system, messages, scope, json_mode=False, **_):
        self.calls.append((tier, system, scope))
        title = re.search(r'title="([^"]+)"', messages[0].content).group(1)
        text = self.answers[title]
        if text is None:
            raise RuntimeError("model down")
        return ChatResult(text, tier, "fake", "fake-8b", "end", Usage(1, 1), 1)


def _item(i, conflict):
    return Item(i, conflict, "number" if conflict else "detail", i, "a", f"{i}-b", "b")


async def test_scoring_counts_recall_false_alarms_and_errors():
    items = [_item("p1", True), _item("p2", True), _item("n1", False), _item("n2", False)]
    gw = Scripted(
        {
            "p1": '{"conflict": true, "explanation": "x"}',
            "p2": '{"conflict": false}',
            "n1": '{"conflict": true, "explanation": "y"}',
            "n2": None,  # error: never counted as correct
        }
    )
    result = await evaluate(gw, items, model="fake-8b", set_name="dev")
    s = result.summary()
    assert s["recall (conflicts caught)"].startswith("50.0% (1/2")
    assert s["false alarms (non-conflicts flagged)"].startswith("50.0% (1/2")
    assert s["errors"] == 1
    assert result.per_item_correct() == {"p1#0": True, "p2#0": False, "n1#0": False, "n2#0": False}
    # The eval sends the nightly job's prompt, on the local background tier, as unclassified.
    tier, system, scope = gw.calls[0]
    assert tier == "background" and SYSTEM in system
    assert scope == ContentScope.unclassified()


def test_candidates_follow_the_nightly_rule():
    # 0 and 1 are close; 2 is far from both. k=1 keeps only each passage's nearest.
    v = [[1.0, 0.0], [0.99, 0.14], [0.0, 1.0]]
    assert candidates(v, cutoff=0.05, k=3) == {(0, 1)}
    assert candidates(v, cutoff=1.0, k=1) == {(0, 1), (1, 2)}
    assert candidates(v, cutoff=1.0, k=3) == {(0, 1), (0, 2), (1, 2)}


async def test_search_recall_reports_missed_conflicts():
    items = [_item("p1", True), _item("p2", True)]

    async def embed(texts):
        # p1's two passages identical (found), p2's opposite (missed).
        return [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, -1.0]]

    [row] = await search_recall(items, embed, cutoffs=[0.1], ks=[3])
    assert row["missed"] == ["p2"]
    assert row["conflicts reaching the model"].startswith("50.0% (1/2")


async def test_units_and_only_flagged_reach_the_model():
    items = [_item("p1", True), _item("n1", False)]
    items[0] = Item("p1", True, "number", "p1", "Request leave two weeks ahead.", "p1-b", "b")
    gw = Scripted({"p1": '{"conflict": false}', "n1": '{"conflict": false}'})
    result = await evaluate(gw, items, model="m", set_name="dev", units=True, only={("p1", 0)})
    assert [t.item for t in result.trials] == ["p1"]  # n1 was not flagged: never asked
    _, system, _ = gw.calls[0]
    assert "Bracketed notes" in system


def test_units_add_conversions_and_keep_the_wording():
    from app.retention.units import annotate

    cases = {
        "two weeks before": "two weeks [= 14 days, 10 working days] before",
        "10 working days' notice": "10 working days [= 2 weeks, about 14 calendar days]' notice",
        "every 6 months": "every 6 months [= about 180 days, about 26 weeks]",
        "180 days": "180 days [= about 6 months]",
        "finish at 17:00.": "finish at 17:00 [= 5:00 pm].",
        "leave at 5 pm": "leave at 5 pm [= 17:00]",
        "twice a year": "twice a year [= every 6 months]",  # not "a year = 12 months"
        "audit quarterly": "audit quarterly [= every 3 months]",
        "3 days, 2.50 hours, version 1.30": "3 days, 2.50 hours, version 1.30",
    }
    for text, want in cases.items():
        assert annotate(text) == want


def test_judge_marks_unit_notes_as_system_added():
    from app.retention.conflicts import UNITS_NOTE

    assert "added by the system" in UNITS_NOTE and "not a contradiction" in UNITS_NOTE


async def test_focus_pairs_the_most_alike_sentences():
    from app.retention.focus import closest_statements

    words = ["pitch", "lunch", "room"]

    async def embed(texts):  # one dimension per topic word
        return [[float(w in t.lower()) for w in words] + [0.1] for t in texts]

    a = "Lunch is at 12:30. Each pitch lasts 2 minutes. Set up the room early."
    b = "Each pitch lasts 4 minutes. Book the room."
    pairs = await closest_statements(a, b, embed, top=2)
    assert set(pairs) == {
        ("Each pitch lasts 2 minutes.", "Each pitch lasts 4 minutes."),
        ("Set up the room early.", "Book the room."),
    }  # each sentence used once: lunch has no partner left
    assert await closest_statements("One rule.", "Another rule.", embed) == []


async def test_strict_screen_and_focus_reach_the_prompt():
    from app.retention.conflicts import FOCUS_NOTE, SCREEN_NOTE, STRICT_NOTE, judge_pair

    sent = {}

    class Gw:
        async def chat(self, tier, *, system, messages, scope, json_mode=False, **_):
            sent.update(system=system, user=messages[0].content)
            return ChatResult('{"conflict": false}', tier, "f", "m", "stop", Usage(), 1)

    async def embed(texts):
        return [[1.0, float(i)] for i, _ in enumerate(texts)]

    await judge_pair(
        Gw(), "First <b>rule</b>. Second rule.", "Third rule. Fourth.", title_a="A", title_b="B",
        scope=ContentScope.unclassified(), strict=True, screen=True, embed=embed,
    )  # fmt: skip
    assert STRICT_NOTE in sent["system"] and SCREEN_NOTE in sent["system"]
    assert FOCUS_NOTE in sent["system"]
    closest = sent["user"].split("<closest>")[1]
    assert "<b>" not in closest  # passage text stays escaped data inside the block
