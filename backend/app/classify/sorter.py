"""The trained sorter: a second, small vote next to the AI Classifier.

Trained (nightly, and on demand) from documents whose place people decided:
the folder they filed it in (folder rules), its own frontmatter, or an approved
label. Each document is its search fingerprint (the mean of its chunk
embeddings, already stored for search). Training keeps one average fingerprint
per department, per department + sensitivity and per folder. Nothing else:
no text, no titles, so the model can't repeat a document.

It only ever makes things safer (`combine`):
- it disagrees with the AI about the department -> the note waits for a person
- it agrees -> the stricter of the two sensitivities is proposed
- it suggests a folder inside the agreed department (shown to reviewers)
- the AI is unsure -> its guess is shown to the reviewer, never applied
The one-way rule (app.classify.rules.decide) still decides what happens.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from app.classify.rules import CONFIDENCE_THRESHOLD, Proposal
from app.policy.engine import Sensitivity, resolve_sensitivity

TEMPERATURE = 0.05  # how sharply similarity turns into confidence (fixed, not tuned)
CONFIDENT = 0.6  # below this the sorter abstains
MIN_PER_CLASS = 2  # a department, level or folder needs this many filed documents
FOLDER_CONFIDENT = CONFIDENT  # a folder is suggested only when clearly the closest


@dataclass(frozen=True)
class Labelled:
    vector: list[float]
    space: str
    sensitivity: str
    folder: str | None = None


@dataclass
class SorterModel:
    n: int = 0
    spaces: dict[str, list[float]] = field(default_factory=dict)
    levels: dict[str, list[float]] = field(default_factory=dict)  # "space/level"
    folders: dict[str, tuple[str, list[float]]] = field(default_factory=dict)  # path -> (space, v)

    def to_json(self) -> dict:
        return {
            "n": self.n,
            "spaces": self.spaces,
            "levels": self.levels,
            "folders": {k: [s, v] for k, (s, v) in self.folders.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> SorterModel:
        return cls(
            n=int(data.get("n") or 0),
            spaces=dict(data.get("spaces") or {}),
            levels=dict(data.get("levels") or {}),
            folders={k: (s, v) for k, (s, v) in (data.get("folders") or {}).items()},
        )


@dataclass(frozen=True)
class Vote:
    space: str
    confidence: float
    sensitivity: Sensitivity | None  # None: not sure about the level
    folder: str | None


def _unit(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm else v


def _mean(vectors: list[list[float]]) -> list[float]:
    total = [sum(xs) for xs in zip(*vectors, strict=True)]
    return _unit([x / len(vectors) for x in total])


def _sim(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _softmax_best(scores: dict[str, float]) -> tuple[str, float]:
    top = max(scores.values())
    weights = {k: math.exp((s - top) / TEMPERATURE) for k, s in scores.items()}
    best = max(scores, key=lambda k: scores[k])
    return best, weights[best] / sum(weights.values())


def train(items: list[Labelled], min_per_class: int = MIN_PER_CLASS) -> SorterModel:
    groups: dict[str, list[list[float]]] = {}
    levels: dict[str, list[list[float]]] = {}
    folders: dict[str, tuple[str, list[list[float]]]] = {}
    for it in items:
        v = _unit(it.vector)
        groups.setdefault(it.space, []).append(v)
        levels.setdefault(f"{it.space}/{it.sensitivity}", []).append(v)
        if it.folder:
            folders.setdefault(it.folder, (it.space, []))[1].append(v)
    model = SorterModel(n=len(items))
    model.spaces = {s: _mean(vs) for s, vs in groups.items() if len(vs) >= min_per_class}
    model.levels = {k: _mean(vs) for k, vs in levels.items() if len(vs) >= min_per_class}
    model.folders = {
        f: (s, _mean(vs)) for f, (s, vs) in folders.items() if len(vs) >= min_per_class
    }
    return model


def predict(model: SorterModel, vector: list[float]) -> Vote | None:
    """None when it has too little to go on or isn't confident."""
    if len(model.spaces) < 2 or not vector:
        return None
    v = _unit(vector)
    space, confidence = _softmax_best({s: _sim(v, c) for s, c in model.spaces.items()})
    if confidence < CONFIDENT:
        return None
    level_scores = {
        k.split("/", 1)[1]: _sim(v, c) for k, c in model.levels.items() if k.startswith(space + "/")
    }
    level = None
    if len(level_scores) >= 2:
        best, level_conf = _softmax_best(level_scores)
        if level_conf >= CONFIDENT:
            level = resolve_sensitivity(best)
    folder_scores = {f: _sim(v, c) for f, (s, c) in model.folders.items() if s == space}
    folder = None
    if folder_scores:
        best, folder_conf = _softmax_best(folder_scores)
        folder = best if folder_conf >= FOLDER_CONFIDENT else None
    return Vote(space=space, confidence=round(confidence, 3), sensitivity=level, folder=folder)


def combine(proposal: Proposal, vote: Vote | None) -> tuple[Proposal, str | None]:
    """The AI's proposal adjusted by the sorter's vote (only ever safer), and
    the folder to suggest. See the module docstring."""
    if vote is None or not proposal.valid:
        return proposal, None
    if proposal.space is None or proposal.confidence < CONFIDENCE_THRESHOLD:
        # The AI is unsure: show the sorter's guess, never strong enough to apply.
        guess = replace(
            proposal,
            space=proposal.space or vote.space,
            sensitivity=max(proposal.sensitivity, vote.sensitivity or Sensitivity.RESTRICTED),
            confidence=min(proposal.confidence, CONFIDENCE_THRESHOLD - 0.01),
        )
        return guess, vote.folder if guess.space == vote.space else None
    if vote.space != proposal.space:
        held = replace(
            proposal,
            confidence=min(proposal.confidence, CONFIDENCE_THRESHOLD - 0.01),
            rationale=(
                proposal.rationale + " The trained sorter disagrees about the department."
            ).strip(),
        )
        return held, None
    if vote.sensitivity is not None and vote.sensitivity > proposal.sensitivity:
        proposal = replace(proposal, sensitivity=vote.sensitivity)
    return proposal, vote.folder
