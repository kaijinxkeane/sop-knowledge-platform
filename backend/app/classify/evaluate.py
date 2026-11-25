"""Phase 2b eval: the Classifier against known labels.

Items: every file in the demo vault (truth: demo-vault-labels.yaml) plus the
extra fictional notes in config/eval/classifier-cases.yaml.

Blind by default: every item is shown as `Inbox/<file name>` with its label
lines removed, because in production the Classifier only sees notes that no
folder rule or frontmatter covers. (Showing the real folder, e.g. `HR/...`,
gives the answer away.)

Each item is classified `repeats` times; local models are not fully
deterministic, so every run counts as one trial and per-item consistency is
reported too. Outcomes (plan §4.1):
- exact
- over_exposed: someone could read it who shouldn't (looser than the truth,
  or the wrong space for a non-public note). The dangerous one.
- misplaced: wrong space for a public note (everyone may read it anyway)
- over_restricted: right space, stricter than the truth (safe, more review)
- unsure: no space, or confidence below the threshold (quarantined)
- failure: the call or the reply failed
`effective_over_exposed` counts what would actually reach readers after the
one-way rule; it must be 0 whatever the model does.

With `sorter=True` every AI reply is also scored after the trained sorter's
vote (app.classify.sorter.combine), so one model run compares both. The sorter
is trained leave-one-out on the other items, or on `train_items` (the dev
items) when testing on the held-out cases.
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import yaml

from app.classify.model import EXAMPLE_CHARS, MAX_EXAMPLES, Classifier, ClassifyInput, Example
from app.classify.rules import CONFIDENCE_THRESHOLD, decide
from app.classify.sorter import Labelled, combine, predict, train
from app.eval.stats import rate
from app.policy.engine import Sensitivity
from app.vault.parse import is_supported, parse_file

STRIP_KEYS = {"space", "sensitivity", "shared_with"}
OUTCOMES = ("exact", "over_exposed", "misplaced", "over_restricted", "unsure", "failure")


@dataclass(frozen=True)
class Item:
    id: str
    source: str  # "vault" or "case"
    path: str
    title: str
    kind: str
    text: str
    space: str
    sensitivity: Sensitivity


@dataclass
class Trial:
    item: str
    run: int
    outcome: str
    got: str
    want: str
    effective_over_exposed: bool
    names: list[str]
    seconds: float
    sorted_outcome: str | None = None  # the same reply after the sorter's vote
    sorted_leaked: bool = False
    vote: str | None = None  # "space/level" the sorter said, None = abstained
    folder_ok: bool | None = None  # suggested folder right (vault items only)


@dataclass
class EvalResult:
    model: str
    blind: bool
    repeats: int
    example_pool: int | None = None
    sorter: bool = False
    cases: str = "dev"
    items: list[Item] = field(default_factory=list)
    trials: list[Trial] = field(default_factory=list)

    def per_item_correct(self, with_sorter: bool = False) -> dict[str, bool]:
        """An item counts as right only if every run was exact (for paired comparison)."""
        out: dict[str, bool] = {}
        for t in self.trials:
            got = t.sorted_outcome if with_sorter else t.outcome
            out[t.item] = out.get(t.item, True) and got == "exact"
        return out

    def _rates(self, outcomes: list[str], leaked: int) -> dict:
        n = len(outcomes)
        counts = Counter(outcomes)
        return {
            "placed_correctly": rate(counts["exact"], n),
            "over_exposed": rate(counts["over_exposed"], n),
            "misplaced": rate(counts["misplaced"], n),
            "over_restricted": rate(counts["over_restricted"], n),
            "unsure": rate(counts["unsure"], n),
            "effective_over_exposed": leaked,
        }

    def sorter_summary(self) -> dict | None:
        if not self.sorter:
            return None
        sources = {i.id: i for i in self.items}
        votes = [t for t in self.trials if t.vote]
        right = sum(t.vote.split("/")[0] == sources[t.item].space for t in votes)
        folders = [t.folder_ok for t in self.trials if t.folder_ok is not None]
        return {
            **self._rates(
                [t.sorted_outcome or "failure" for t in self.trials],
                sum(t.sorted_leaked for t in self.trials),
            ),
            "sorter_voted": rate(len(votes), len(self.trials)),
            "sorter_department_right_when_voting": rate(right, len(votes)),
            "folder_suggestions_right": rate(sum(folders), len(folders)) if folders else None,
        }

    def summary(self) -> dict:
        n = len(self.trials)
        counts = Counter(t.outcome for t in self.trials)
        by_item: dict[str, set[str]] = {}
        for t in self.trials:
            by_item.setdefault(t.item, set()).add(t.got)
        want_by_level = Counter()
        exact_by_level = Counter()
        sources = {i.id: i for i in self.items}
        for t in self.trials:
            level = sources[t.item].sensitivity.label
            want_by_level[level] += 1
            exact_by_level[level] += t.outcome == "exact"
        return {
            "model": self.model,
            "blind": self.blind,
            "example_pool": self.example_pool,
            "cases": self.cases,
            "with_sorter": self.sorter_summary(),
            "items": len(self.items),
            "runs_per_item": self.repeats,
            "trials": n,
            "placed_correctly": rate(counts["exact"], n),
            "over_exposed": rate(counts["over_exposed"], n),
            "misplaced": rate(counts["misplaced"], n),
            "over_restricted": rate(counts["over_restricted"], n),
            "unsure": rate(counts["unsure"], n),
            "failures": counts["failure"],
            "effective_over_exposed": sum(t.effective_over_exposed for t in self.trials),
            "correct_by_truth_level": {
                lv: rate(exact_by_level[lv], want_by_level[lv]) for lv in sorted(want_by_level)
            },
            "items_with_inconsistent_answers": sum(len(v) > 1 for v in by_item.values()),
            "seconds_per_call": round(sum(t.seconds for t in self.trials) / max(n, 1), 2),
        }


def _strip_labels(text: str) -> str:
    """Remove label lines from frontmatter so the model can't just read them."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    head = [
        ln
        for ln in text[3:end].splitlines()
        if ln.split(":", 1)[0].strip() not in STRIP_KEYS and not ln.startswith("  - ")
    ]
    return "---" + "\n".join(head) + text[end:]


def load_items(vault, labels_file, cases_file=None) -> list[Item]:
    truth_raw = yaml.safe_load(labels_file.read_text())
    truth = {**truth_raw["notes"], **truth_raw["attachments"]}
    items = []
    for rel in sorted(truth):
        path = vault / rel
        if not path.is_file() or not is_supported(rel):
            continue
        data = path.read_bytes()
        if rel.endswith(".md"):
            data = _strip_labels(data.decode()).encode()
        parsed = parse_file(rel, data)
        items.append(
            Item(
                rel,
                "vault",
                rel,
                parsed.title,
                parsed.kind,
                "\n\n".join(c.text for c in parsed.chunks),
                truth[rel]["space"],
                Sensitivity[truth[rel]["sensitivity"].upper()],
            )
        )
    if cases_file is not None and cases_file.is_file():
        for c in yaml.safe_load(cases_file.read_text())["cases"]:
            items.append(
                Item(
                    c["id"],
                    "case",
                    f"{c['title']}.md",
                    c["title"],
                    "note",
                    f"# {c['title']}\n\n{c['text']}",
                    c["space"],
                    Sensitivity[c["sensitivity"].upper()],
                )
            )
    return items


def outcome(p, item: Item) -> str:
    want = item.sensitivity
    if p.space is None or p.confidence < CONFIDENCE_THRESHOLD:
        return "unsure"
    if p.sensitivity < want or (p.space != item.space and want is not Sensitivity.PUBLIC):
        return "over_exposed"
    if p.space != item.space:
        return "misplaced"
    if p.sensitivity > want:
        return "over_restricted"
    return "exact"


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1 - dot / norm if norm else 1.0


def pick_examples(
    item: Item,
    pool: list[Item],
    vectors: dict[str, list[float]],
    k: int = MAX_EXAMPLES,
    max_distance: float = 0.6,
) -> tuple[Example, ...]:
    """Leave-one-out: the k pool items most like `item` (never itself), as human examples."""
    near = sorted(
        ((_cos(vectors[item.id], vectors[o.id]), o.id, o) for o in pool if o.id != item.id),
        key=lambda t: (t[0], t[1]),
    )
    return tuple(
        Example(o.title, o.text[:EXAMPLE_CHARS], o.space, o.sensitivity.label, _folder(o))
        for d, _, o in near[:k]
        if d <= max_distance
    )


def _folder(item: Item) -> str | None:
    """Where a person filed it (vault items), the label the sorter learns folders from."""
    if item.source != "vault":
        return None
    parent = str(PurePosixPath(item.path).parent)
    return None if parent in (".", "Inbox") or parent.startswith(("Inbox/", "Help")) else parent


def _sorter_vote(item: Item, pool: list[Item], vectors: dict[str, list[float]], cache: dict):
    """Leave-one-out unless the pool doesn't contain the item (held-out mode)."""
    key = item.id if any(o.id == item.id for o in pool) else "__all__"
    if key not in cache:
        cache[key] = train(
            [
                Labelled(vectors[o.id], o.space, o.sensitivity.label, _folder(o))
                for o in pool
                if o.id != item.id
            ]
        )
    return predict(cache[key], vectors[item.id])


async def evaluate(
    classify: Classifier,
    items: list[Item],
    *,
    model: str,
    known_spaces: set[str],
    repeats: int = 1,
    blind: bool = True,
    progress=None,
    example_pool: int | None = None,
    embed=None,
    seed: int = 7,
    sorter: bool = False,
    train_items: list[Item] | None = None,
    cases: str = "dev",
) -> EvalResult:
    """`example_pool`: simulate N notes already labelled by people (a random,
    fixed subset of the items, never the item itself); None = no examples.
    `train_items`: the labelled notes examples and the sorter come from when
    testing on held-out cases (then `example_pool` is all of them)."""
    result = EvalResult(
        model=model,
        blind=blind,
        repeats=repeats,
        items=list(items),
        example_pool=example_pool,
        sorter=sorter,
        cases=cases,
    )
    vectors: dict[str, list[float]] = {}
    pool: list[Item] = []
    known = list(items) + [t for t in (train_items or []) if t.id not in {i.id for i in items}]
    if example_pool or sorter:
        vecs = await embed([f"{i.title}\n\n{i.text[:2000]}" for i in known])
        vectors = {i.id: v for i, v in zip(known, vecs, strict=True)}
    labelled = list(train_items) if train_items else list(items)
    if example_pool:
        pool = random.Random(seed).sample(labelled, min(example_pool, len(labelled)))
    sorter_cache: dict = {}
    for run in range(repeats):
        for item in items:
            examples = pick_examples(item, pool, vectors) if pool else ()
            shown = f"Inbox/{PurePosixPath(item.path).name}" if blind else item.path
            want = f"{item.space}/{item.sensitivity.label}"
            started = time.monotonic()
            try:
                p = await classify(ClassifyInput(shown, item.title, item.kind, item.text, examples))
                if not p.valid:
                    raise ValueError("unreadable reply")
            except Exception:  # noqa: BLE001 - counted, never fatal
                t = Trial(item.id, run, "failure", "-", want, False, [], time.monotonic() - started)
            else:
                applied = decide(None, p, known_spaces=known_spaces).apply
                leaked = (
                    applied is not None
                    and item.sensitivity is not Sensitivity.PUBLIC
                    and (applied.space != item.space or applied.sensitivity < item.sensitivity)
                )
                t = Trial(
                    item.id,
                    run,
                    outcome(p, item),
                    f"{p.space}/{p.sensitivity.label}",
                    want,
                    leaked,
                    list(p.names),
                    time.monotonic() - started,
                )
            if sorter and t.outcome != "failure":
                vote = _sorter_vote(item, labelled, vectors, sorter_cache)
                sorted_p, folder = combine(p, vote)
                applied = decide(None, sorted_p, known_spaces=known_spaces).apply
                t.sorted_outcome = outcome(sorted_p, item)
                t.sorted_leaked = (
                    applied is not None
                    and item.sensitivity is not Sensitivity.PUBLIC
                    and (applied.space != item.space or applied.sensitivity < item.sensitivity)
                )
                if vote is not None:
                    t.vote = f"{vote.space}/{vote.sensitivity.label if vote.sensitivity else '-'}"
                if _folder(item) and vote is not None and vote.space == item.space:
                    t.folder_ok = folder == _folder(item)
            elif sorter:
                t.sorted_outcome = "failure"
            result.trials.append(t)
            if progress:
                progress(t)
    return result
