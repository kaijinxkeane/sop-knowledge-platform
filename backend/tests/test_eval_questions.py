"""The answering eval's question set is consistent with the demo vault's ground truth."""

import yaml

from app.eval.answers import allowed_by_truth, principal_for_roles
from tests.conftest import CONFIG_DIR, REPO_ROOT

Q = yaml.safe_load((CONFIG_DIR / "eval" / "questions.yaml").read_text())
ROLES = yaml.safe_load((CONFIG_DIR / "roles.yaml").read_text())
T = yaml.safe_load((REPO_ROOT / "demo-vault-labels.yaml").read_text())
TRUTH = {**T["notes"], **T["attachments"]}


def test_ids_unique_and_sets_known():
    ids = [q["id"] for q in Q["questions"]]
    assert len(ids) == len(set(ids))
    assert {q["set"] for q in Q["questions"]} <= {
        "answering",
        "reasoning",
        "abstention",
        "adversarial",
    }


def test_expected_docs_exist_and_are_readable_by_the_asking_role():
    for q in Q["questions"]:
        p = principal_for_roles(Q["roles"][q["role"]], ROLES)
        for path in q.get("docs") or []:
            assert path in TRUTH, (q["id"], path)
            assert allowed_by_truth(path, p, TRUTH), (q["id"], path)
        assert bool(q.get("no_answer")) != bool(q.get("include")), q["id"]


def _section(text="", cites=(), no_answer=False):
    from types import SimpleNamespace

    return SimpleNamespace(
        text=text,
        no_answer=no_answer,
        first_token_ms=10,
        invalid_citations=0,
        model="m",
        citations=[{"vault_path": c} for c in cites],
    )


def test_grader():
    from types import SimpleNamespace

    from app.eval.answers import grade, per_item_correct

    route = SimpleNamespace(spaces=["core"], reason="search")
    ceo = principal_for_roles(["employee", "core-lead"], ROLES)
    staff = principal_for_roles(["employee", "core-staff"], ROLES)
    q = {
        "id": "t",
        "set": "answering",
        "role": "ceo",
        "spaces": ["core"],
        "include": [["7,500", "7500"]],
        "docs": ["Commercial/Rate Card 2026.md"],
    }
    ok = grade(
        q, [_section("Floor is 7,500 [1].", ["Commercial/Rate Card 2026.md"])], route, ceo, TRUTH, 5
    )
    assert ok.correct and not ok.leak
    missing = grade(
        q, [_section("It depends [1].", ["Commercial/Rate Card 2026.md"])], route, ceo, TRUTH, 5
    )
    assert not missing.correct and missing.notes == ["missing facts"]
    # the same citation for a user who may not read it is a leak
    leak = grade(
        q, [_section("7,500 [1]", ["Commercial/Rate Card 2026.md"])], route, staff, TRUTH, 5
    )
    assert leak.leak and not leak.correct
    a = {
        "id": "a",
        "set": "abstention",
        "role": "core_staff",
        "no_answer": True,
        "must_not_include": ["7,500"],
    }
    assert grade(a, [_section(no_answer=True)], route, staff, TRUTH, 5).correct
    r1, r2 = ok, missing
    r2.id = "t"
    assert per_item_correct([r1, r2]) == {"t": False}
