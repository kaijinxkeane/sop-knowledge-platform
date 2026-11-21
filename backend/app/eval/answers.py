"""Phase 3 answering eval (plan §5.2): the real pipeline, graded deterministically.

    python -m app.cli eval-answers [--model qwen3:8b] [--only c01,x02] [--out results.json]

Needs the dev stack with the demo vault indexed and name-checked. Questions
live in config/eval/questions.yaml. No model judges the answers: facts are
matched against expected strings, citations against expected SOPs, and leaks
against the demo vault's ground-truth labels.
"""

from __future__ import annotations

import statistics
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.agents.concierge import ask
from app.eval.stats import rate
from app.models.gateway import ModelGateway
from app.policy.engine import GrantRule, Principal, Sensitivity
from app.spaces import SpaceProfile


def principal_for_roles(roles: list[str], roles_config: dict) -> Principal:
    grants = []
    for name in roles:
        for g in roles_config["roles"][name]["grants"]:
            grants.append(
                GrantRule(
                    g.get("space"),
                    Sensitivity[g["max_sensitivity"].upper()],
                    frozenset(g["actions"]),
                )
            )
    return Principal(uuid.uuid4(), frozenset(roles), tuple(grants))


def allowed_by_truth(path: str, principal: Principal, truth: dict) -> bool:
    t = truth.get(path)
    return t is not None and principal.can_read(t["space"], t["sensitivity"])


@dataclass
class Graded:
    id: str
    set: str
    role: str
    correct: bool
    answered: bool
    routed: list[str]
    route_reason: str
    route_ok: bool
    cited: list[str]
    citation_ok: bool
    invalid_markers: int
    leak: list[str]
    first_token_ms: int | None
    total_ms: int
    models: list[str]
    answer: str
    notes: list[str] = field(default_factory=list)
    run: int = 0
    facts: float | None = None  # share of expected fact groups covered (detail)
    words: int = 0
    groups: int = 0  # number of expected fact groups


def grade(q: dict, sections, route, principal, truth, total_ms: int) -> Graded:
    answered = [s for s in sections if not s.no_answer]
    text = "\n".join(s.text for s in answered)
    low = text.lower()
    cited = sorted({c["vault_path"] for s in answered for c in s.citations})
    notes, leak = [], []
    for path in cited:
        if not allowed_by_truth(path, principal, truth):
            leak.append(f"cited unreadable {path}")
    for bad in q.get("must_not_include") or []:
        if bad.lower() in low:
            leak.append(f"contains {bad!r}")
    coverage = None
    if q.get("no_answer"):
        correct = not answered and not leak
        citation_ok = not cited
    else:
        groups = q.get("include") or []
        hit = [any(alt.lower() in low for alt in group) for group in groups]
        facts = all(hit)
        coverage = sum(hit) / len(groups) if groups else None
        docs = set(q.get("docs") or [])
        citation_ok = bool(cited) and (not docs or any(c in docs for c in cited))
        correct = bool(answered) and facts and citation_ok and not leak
        if answered and not facts:
            notes.append("missing facts")
        if answered and not citation_ok:
            notes.append("wrong or missing citation")
        if not answered:
            notes.append("said no answer")
    expected_spaces = set(q.get("spaces") or [])
    firsts = [s.first_token_ms for s in answered if s.first_token_ms is not None]
    return Graded(
        id=q["id"],
        set=q["set"],
        role=q["role"],
        correct=correct,
        answered=bool(answered),
        routed=list(route.spaces),
        route_reason=route.reason,
        route_ok=expected_spaces <= set(route.spaces) if expected_spaces else True,
        cited=cited,
        citation_ok=citation_ok,
        invalid_markers=sum(s.invalid_citations for s in sections),
        leak=leak,
        first_token_ms=min(firsts) if firsts else None,
        total_ms=total_ms,
        models=sorted({s.model for s in sections if s.model}),
        answer=text,
        notes=notes,
        facts=coverage if answered or coverage is None else 0.0,
        words=len(text.split()),
        groups=len(q.get("include") or []),
    )


async def run_eval(
    *,
    questions_file: Path,
    roles_config: dict,
    truth: dict,
    sessions,
    gateway: ModelGateway,
    embed_query,
    profiles: dict[str, SpaceProfile],
    only: set[str] | None = None,
    repeats: int = 1,
    progress=None,
) -> list[Graded]:
    data = yaml.safe_load(questions_file.read_text())  # noqa: ASYNC240 - CLI only
    results = []
    todo = [q for q in data["questions"] if not only or q["id"] in only]
    for run, q in ((r, q) for r in range(repeats) for q in todo):
        principal = principal_for_roles(data["roles"][q["role"]], roles_config)
        started = time.monotonic()
        sections, route = [], None
        async for ev in ask(
            principal=principal,
            question=q["question"],
            sessions=sessions,
            gateway=gateway,
            embed_query=embed_query,
            profiles=profiles,
        ):
            if ev["type"] == "done":
                sections, route = ev["sections"], ev["route"]
        g = grade(q, sections, route, principal, truth, int((time.monotonic() - started) * 1000))
        g.run = run
        results.append(g)
        if progress:
            progress(g)
    return results


def per_item_correct(results: list[Graded]) -> dict[str, bool]:
    """An item counts as right only if every run was right (for paired comparison)."""
    out: dict[str, bool] = {}
    for r in results:
        out[r.id] = out.get(r.id, True) and r.correct
    return out


def summarise(results: list[Graded]) -> dict:
    def r(xs):
        return rate(sum(xs), len(xs)) if xs else "-"

    by_set = {}
    for name in ("answering", "reasoning", "abstention", "adversarial"):
        rows = [x for x in results if x.set == name]
        if rows:
            by_set[name] = r([x.correct for x in rows])
    answerable = [x for x in results if x.set in ("answering", "reasoning")]
    answered = [x for x in results if x.answered]
    firsts = sorted(x.first_token_ms for x in results if x.first_token_ms is not None)
    totals = sorted(x.total_ms for x in results)
    items = per_item_correct(results)
    cov = [x.facts for x in results if x.facts is not None]
    multi = [x.facts for x in results if x.facts is not None and x.groups >= 3]
    return {
        "questions": len({x.id for x in results}),
        "runs": max((x.run for x in results), default=0) + 1,
        "trials": len(results),
        "correct": r([x.correct for x in results]),
        "by_set": by_set,
        "items_right_every_run": rate(sum(items.values()), len(items)),
        "answerable_but_said_no_answer": r([not x.answered for x in answerable]),
        "answered_but_missing_facts": r(["missing facts" in x.notes for x in answered]),
        "citation_valid_when_answered": r([x.citation_ok for x in answered]),
        "fact_coverage_mean": round(statistics.mean(cov), 3) if cov else None,
        "fact_coverage_multi_part": round(statistics.mean(multi), 3) if multi else None,
        "words_median_when_answered": statistics.median([x.words for x in answered])
        if answered
        else None,
        "routing_ok": r([x.route_ok for x in results]),
        "route_reasons": {
            k: sum(x.route_reason == k for x in results)
            for k in sorted({x.route_reason for x in results})
        },
        "leaks": sum(bool(x.leak) for x in results),
        "invalid_citation_markers": sum(x.invalid_markers for x in results),
        "first_token_s_median": round(statistics.median(firsts) / 1000, 1) if firsts else None,
        "first_token_s_p90": round(firsts[int(0.9 * (len(firsts) - 1))] / 1000, 1)
        if firsts
        else None,
        "total_s_median": round(statistics.median(totals) / 1000, 1) if totals else None,
        "models": sorted({m for x in results for m in x.models}),
    }
