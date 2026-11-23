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


def test_dev_and_holdout_do_not_overlap():
    dev, hold = (load_items(EVAL_DIR / n) for n in SETS.values())
    assert not {i.id for i in dev} & {i.id for i in hold}
    assert not {(i.text_a, i.text_b) for i in dev} & {(i.text_a, i.text_b) for i in hold}


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
