"""Statistics used to compare models, and the Classifier eval's extra cases."""

from collections import Counter

import pytest
import yaml

from app.classify.evaluate import load_items, outcome
from app.classify.rules import Proposal
from app.eval.stats import mcnemar, paired, wilson
from app.policy.engine import Sensitivity
from tests.conftest import CONFIG_DIR, REPO_ROOT


def test_wilson_interval():
    lo, hi = wilson(94, 100)
    assert 0.87 < lo < 0.88 and 0.97 < hi < 0.98
    assert wilson(0, 30)[0] == 0 and wilson(0, 30)[1] > 0.1  # zero is not "certainly zero"
    assert wilson(0, 0) == (0.0, 1.0)


def test_mcnemar_and_paired():
    assert mcnemar(0, 0) == 1.0
    assert mcnemar(8, 0) == pytest.approx(0.0078, abs=1e-4)
    assert mcnemar(3, 3) == 1.0
    r = paired({"a": True, "b": False, "c": True}, {"a": True, "b": True, "c": False, "d": True})
    assert r["items"] == 3 and r["only_a_right"] == ["c"] and r["only_b_right"] == ["b"]


def test_cases_are_valid_and_cover_every_space_and_level():
    cases = yaml.safe_load((CONFIG_DIR / "eval" / "classifier-cases.yaml").read_text())["cases"]
    assert len({c["id"] for c in cases}) == len(cases)
    cells = Counter((c["space"], c["sensitivity"]) for c in cases)
    for space in ("core", "it", "hr"):
        for level in ("public", "internal", "restricted"):
            assert cells[(space, level)] >= 8, (space, level)


def test_items_merge_vault_and_cases():
    items = load_items(
        REPO_ROOT / "demo-vault",
        REPO_ROOT / "demo-vault-labels.yaml",
        CONFIG_DIR / "eval" / "classifier-cases.yaml",
    )
    assert {i.source for i in items} == {"vault", "case"}
    assert len({i.id for i in items}) == len(items)
    assert not any("sensitivity:" in i.text for i in items if i.source == "vault")


@pytest.mark.parametrize(
    ("got", "want", "expected"),
    [
        (("core", "restricted"), ("core", "restricted"), "exact"),
        (("core", "internal"), ("core", "restricted"), "over_exposed"),
        (("it", "restricted"), ("core", "internal"), "over_exposed"),
        (("it", "public"), ("core", "public"), "misplaced"),
        (("core", "restricted"), ("core", "public"), "over_restricted"),
        ((None, "restricted"), ("core", "public"), "unsure"),
    ],
)
def test_outcome(got, want, expected):
    from app.classify.evaluate import Item

    p = Proposal(space=got[0], sensitivity=Sensitivity[got[1].upper()], confidence=0.9)
    item = Item("x", "case", "x.md", "x", "note", "", want[0], Sensitivity[want[1].upper()])
    assert outcome(p, item) == expected
