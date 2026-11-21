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


@dataclass
class EvalResult:
    model: str
    blind: bool
    repeats: int
    example_pool: int | None = None
    items: list[Item] = field(default_factory=list)
    trials: list[Trial] = field(default_factory=list)

    def per_item_correct(self) -> dict[str, bool]:
        """An item counts as right only if every run was exact (for paired comparison)."""
        out: dict[str, bool] = {}
        for t in self.trials:
            out[t.item] = out.get(t.item, True) and t.outcome == "exact"
        return out

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
        Example(o.title, o.text[:EXAMPLE_CHARS], o.space, o.sensitivity.label)
        for d, _, o in near[:k]
        if d <= max_distance
    )


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
) -> EvalResult:
    """`example_pool`: simulate N notes already labelled by people (a random,
    fixed subset of the items, never the item itself); None = no examples."""
    result = EvalResult(
        model=model, blind=blind, repeats=repeats, items=list(items), example_pool=example_pool
    )
    vectors: dict[str, list[float]] = {}
    pool: list[Item] = []
    if example_pool:
        vecs = await embed([f"{i.title}\n\n{i.text[:2000]}" for i in items])
        vectors = {i.id: v for i, v in zip(items, vecs, strict=True)}
        pool = random.Random(seed).sample(items, min(example_pool, len(items)))
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
            result.trials.append(t)
            if progress:
                progress(t)
    return result
