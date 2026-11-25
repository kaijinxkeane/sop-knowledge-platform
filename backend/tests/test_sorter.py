"""The trained sorter only ever makes the Classifier safer."""

from app.classify.rules import CONFIDENCE_THRESHOLD, Proposal, decide
from app.classify.sorter import Labelled, SorterModel, Vote, combine, predict, train
from app.policy.engine import Sensitivity
from app.vault.labels import Labels

P, INT, R = Sensitivity.PUBLIC, Sensitivity.INTERNAL, Sensitivity.RESTRICTED


def _vec(*hot: int, n: int = 8) -> list[float]:
    return [1.0 if i in hot else 0.0 for i in range(n)]


DATA = [
    Labelled(_vec(0), "hr", "internal", "HR"),
    Labelled(_vec(0, 1), "hr", "internal", "HR"),
    Labelled(_vec(4), "it", "internal", "IT"),
    Labelled(_vec(4, 5), "it", "internal", "IT"),
    Labelled(_vec(6), "core", "internal", "Programmes"),
    Labelled(_vec(6, 7), "core", "internal", "Programmes"),
]


def test_learns_departments_and_folders_from_filed_documents():
    model = train(DATA)
    assert set(model.spaces) == {"hr", "it", "core"}
    vote = predict(model, _vec(0))
    assert vote is not None and vote.space == "hr" and vote.folder == "HR"
    assert predict(SorterModel.from_json(model.to_json()), _vec(4)).space == "it"


def test_abstains_when_unsure_or_untrained():
    assert predict(train(DATA), _vec(0, 4, 6)) is None  # equally close to all three
    assert predict(train(DATA[:2]), _vec(0)) is None  # one department: nothing to choose
    assert predict(train(DATA), []) is None


def test_keeps_no_text():
    stored = train(DATA).to_json()
    assert set(stored) == {"n", "spaces", "levels", "folders"}


def _ai(space="hr", sens=INT, confidence=0.9) -> Proposal:
    return Proposal(space=space, sensitivity=sens, confidence=confidence, rationale="ai")


def test_disagreement_waits_for_a_person():
    held, folder = combine(_ai("hr"), Vote("it", 0.9, INT, "IT"))
    assert held.confidence < CONFIDENCE_THRESHOLD and folder is None
    current = Labels(space="hr", sensitivity=R)
    assert decide(current, held, known_spaces={"hr", "it"}).apply is None


def test_agreement_takes_the_stricter_level_and_suggests_a_folder():
    out, folder = combine(_ai("hr", P), Vote("hr", 0.9, R, "HR/Payroll"))
    assert out.sensitivity is R and folder == "HR/Payroll"
    out, _ = combine(_ai("hr", R), Vote("hr", 0.9, P, None))
    assert out.sensitivity is R  # never looser


def test_unsure_ai_gets_a_guess_that_is_never_applied():
    guess, folder = combine(_ai(None, P, 0.2), Vote("it", 0.95, None, "IT"))
    assert guess.space == "it" and guess.sensitivity is R and folder == "IT"
    assert guess.confidence < CONFIDENCE_THRESHOLD
    for current in (None, Labels(space="it", sensitivity=R)):
        assert decide(current, guess, known_spaces={"it"}).apply is None


def test_no_vote_changes_nothing():
    p = _ai()
    assert combine(p, None) == (p, None)
