"""Conflict-check eval (plan §7): how well the local model spots contradictions.

    python -m app.cli eval-conflicts [--set dev|holdout] [--model TAG]
                                     [--repeats N] [--out results.json]

Runs the nightly job's own `judge_pair` on labelled pairs of fictional
passages (config/eval/conflicts.yaml; conflicts-holdout.yaml for the final
comparison only). Needs Ollama, not the database. No model grades the result:
each verdict is compared with its label.

    python -m app.cli eval-conflicts --stage search [--set dev|holdout]

    python -m app.cli eval-conflicts-cascade FIRST.json CONFIRM.json [--out F]

scores a two-stage check from two saved runs on the same set: a pair is a
conflict only if the first model flags it *and* the confirm model agrees (the
confirm model runs only on flagged pairs, so its other verdicts are ignored).

checks the step before the model: would the nightly vector search even pick
each conflicting pair? Every passage is embedded like an indexed chunk and
treated as its own document; each finds its k nearest others within the
distance cutoff (the same rule as `candidate_pairs`), for a grid of cutoffs and k.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from app.eval.stats import rate
from app.models.types import ContentScope
from app.retention.conflicts import judge_pair

# holdout2 (2026-11-24): written before the 14B confirm-stage runs; holdout was used once.
SETS = {
    "dev": "conflicts.yaml",
    "holdout": "conflicts-holdout.yaml",
    "holdout2": "conflicts-holdout2.yaml",
}


@dataclass(frozen=True)
class Item:
    id: str
    conflict: bool
    kind: str
    title_a: str
    text_a: str
    title_b: str
    text_b: str


@dataclass
class Trial:
    item: str
    run: int
    kind: str
    want: bool
    got: bool | None  # None: the model failed or gave no usable JSON
    seconds: float
    explanation: str = ""

    @property
    def correct(self) -> bool:
        return self.got is not None and self.got == self.want


def load_items(path: Path) -> list[Item]:
    raw = yaml.safe_load(path.read_text())["items"]
    items = [
        Item(
            id=r["id"],
            conflict=bool(r["conflict"]),
            kind=r["kind"],
            title_a=r["a"]["title"],
            text_a=r["a"]["text"],
            title_b=r["b"]["title"],
            text_b=r["b"]["text"],
        )
        for r in raw
    ]
    if len({i.id for i in items}) != len(items):
        raise ValueError(f"duplicate ids in {path.name}")
    return items


@dataclass
class Result:
    model: str
    set: str
    trials: list[Trial]

    def summary(self) -> dict:
        ts = self.trials
        pos = [t for t in ts if t.want]
        neg = [t for t in ts if not t.want]
        flagged = [t for t in ts if t.got]
        true_pos = sum(bool(t.got) for t in pos)
        by_kind: dict[str, str] = {}
        for kind in sorted({t.kind for t in ts}):
            k = [t for t in ts if t.kind == kind]
            by_kind[kind] = f"{sum(t.correct for t in k)}/{len(k)} correct"
        return {
            "model": self.model,
            "set": self.set,
            "trials": len(ts),
            "recall (conflicts caught)": rate(true_pos, len(pos)),
            "false alarms (non-conflicts flagged)": rate(sum(bool(t.got) for t in neg), len(neg)),
            "flag rate (all pairs)": rate(len(flagged), len(ts)),
            "precision": rate(true_pos, len(flagged)) if flagged else "n/a (nothing flagged)",
            "accuracy": rate(sum(t.correct for t in ts), len(ts)),
            "errors": sum(t.got is None for t in ts),
            "seconds per pair (median)": round(statistics.median(t.seconds for t in ts), 2),
            "by kind": by_kind,
        }

    def per_item_correct(self) -> dict[str, bool]:
        return {f"{t.item}#{t.run}": t.correct for t in self.trials}

    def to_json(self) -> dict:
        return {
            "kind": f"conflicts-{self.set}",
            "summary": self.summary(),
            "per_item_correct": self.per_item_correct(),
            "trials": [asdict(t) for t in self.trials],
        }


async def evaluate(
    gateway,
    items: list[Item],
    *,
    model: str,
    set_name: str,
    repeats: int = 1,
    tier: str = "background",
    units: bool = False,
    only: set[tuple[str, int]] | None = None,
    progress: Callable[[Trial], None] | None = None,
) -> Result:
    """`only`: (item, run) pairs to check, e.g. those a first stage flagged."""
    trials: list[Trial] = []
    for run in range(repeats):
        for item in items:
            if only is not None and (item.id, run) not in only:
                continue
            start = time.perf_counter()
            got, explanation = None, ""
            try:
                verdict = await judge_pair(
                    gateway,
                    item.text_a,
                    item.text_b,
                    title_a=item.title_a,
                    title_b=item.title_b,
                    # Fictional eval text: unclassified, so no cloud tier may take it.
                    scope=ContentScope.unclassified(),
                    tier=tier,
                    units=units,
                )
                got, explanation = verdict.conflict, verdict.explanation
            except Exception:  # noqa: BLE001 - counted as an error, the run goes on
                pass
            seconds = time.perf_counter() - start
            trial = Trial(item.id, run, item.kind, item.conflict, got, seconds, explanation)
            trials.append(trial)
            if progress:
                progress(trial)
    return Result(model, set_name, trials)


def cascade(first: dict, confirm: dict) -> Result:
    """Two saved runs (`Result.to_json()`) on the same set → the two-stage result.
    Run i of the first stage is paired with run i of the confirm stage."""
    if first["kind"] != confirm["kind"]:
        raise ValueError("both runs must be on the same set")
    second = {(t["item"], t["run"]): t for t in confirm["trials"]}
    trials = []
    for t in first["trials"]:
        got, seconds, why = t["got"], t["seconds"], t["explanation"]
        if got:
            c = second.get((t["item"], t["run"]))
            if c is None:
                raise ValueError(f"confirm run has no trial for {t['item']} run {t['run']}")
            got = c["got"]  # None (model failed) stays an error
            seconds += c["seconds"]
            why = c["explanation"]
        trials.append(Trial(t["item"], t["run"], t["kind"], t["want"], got, seconds, why))
    name = f"{first['summary']['model']} → {confirm['summary']['model']}"
    return Result(name, first["kind"].removeprefix("conflicts-"), trials)


# --- search stage ---------------------------------------------------------------


def _distance(a: list[float], b: list[float]) -> float:
    """Cosine distance, as pgvector's <=> operator."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return 1 - dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def candidates(vectors: list[list[float]], cutoff: float, k: int) -> set[tuple[int, int]]:
    """Pairs the nightly query would return: each passage's k nearest, within the cutoff."""
    found: set[tuple[int, int]] = set()
    for i, v in enumerate(vectors):
        near = sorted((_distance(v, w), j) for j, w in enumerate(vectors) if j != i)[:k]
        found.update((min(i, j), max(i, j)) for d, j in near if d <= cutoff)
    return found


async def search_recall(
    items: list[Item],
    embed: Callable[[list[str]], Awaitable[list[list[float]]]],
    *,
    cutoffs: list[float],
    ks: list[int],
) -> list[dict]:
    # Same text the indexer embeds for a chunk with no heading (`_embed_text`).
    texts = [f"{i.title_a}\n\n{i.text_a}" for i in items] + [
        f"{i.title_b}\n\n{i.text_b}" for i in items
    ]
    vectors = await embed(texts)
    n = len(items)
    conflicts = [(x, n + x) for x, i in enumerate(items) if i.conflict]
    rows = []
    for k in ks:
        for cutoff in cutoffs:
            found = candidates(vectors, cutoff, k)
            caught = [items[a].id for a, b in conflicts if (a, b) in found]
            rows.append(
                {
                    "k": k,
                    "cutoff": cutoff,
                    "conflicts reaching the model": rate(len(caught), len(conflicts)),
                    "pairs to check": len(found),
                    "missed": sorted({items[a].id for a, _ in conflicts} - set(caught)),
                }
            )
    return rows
