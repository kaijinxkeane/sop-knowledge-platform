"""Retrieval-only eval: do the passages handed to the agents contain the answer?

    python -m app.cli eval-retrieval [--questions questions-holdout.yaml]

For each answerable question (same files as the answering eval), runs the real
retrieval (RLS, routing, per-space search) and measures, on the passage text
the department agents would see:
- fact recall: share of the question's required fact groups present
- all facts: every required group present (the answer is fully available)
- doc hit: at least one expected document among the passages
- context size in characters (cost and latency of the answer call)
No answering model is called, so it is fast; the router model is used only when
search is unclear, as in production.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.agents.concierge import retrieve
from app.eval.answers import principal_for_roles
from app.eval.stats import rate


@dataclass
class RetrievalResult:
    id: str
    set: str
    fact_recall: float
    all_facts: bool
    doc_hit: bool
    chars: int
    passages: int
    missing: list[str]


async def run_retrieval_eval(
    *, questions_file: Path, roles_config: dict, sessions, gateway, embed_query, profiles, only=None
) -> list[RetrievalResult]:
    data = yaml.safe_load(questions_file.read_text())  # noqa: ASYNC240 - CLI only
    out = []
    for q in data["questions"]:
        if q.get("no_answer") or (only and q["id"] not in only):
            continue
        principal = principal_for_roles(data["roles"][q["role"]], roles_config)
        vector = await embed_query(q["question"])
        _, per_space = await retrieve(sessions, principal, q["question"], vector, profiles, gateway)
        hits = [h for hs in per_space.values() for h in hs]
        text = "\n".join(f"{h.title}\n{h.heading or ''}\n{h.text}" for h in hits).lower()
        groups = q.get("include") or []
        found = [any(alt.lower() in text for alt in g) for g in groups]
        docs = set(q.get("docs") or [])
        out.append(
            RetrievalResult(
                id=q["id"],
                set=q["set"],
                fact_recall=sum(found) / len(groups) if groups else 1.0,
                all_facts=all(found),
                doc_hit=not docs or any(h.vault_path in docs for h in hits),
                chars=sum(len(h.text) for h in hits),
                passages=len(hits),
                missing=[g[0] for g, f in zip(groups, found, strict=True) if not f],
            )
        )
    return out


def summarise_retrieval(rows: list[RetrievalResult]) -> dict:
    return {
        "questions": len(rows),
        "all_facts_in_context": rate(sum(r.all_facts for r in rows), len(rows)),
        "fact_recall_mean": round(statistics.mean(r.fact_recall for r in rows), 3),
        "expected_doc_hit": rate(sum(r.doc_hit for r in rows), len(rows)),
        "context_chars_median": statistics.median(r.chars for r in rows),
        "context_chars_max": max(r.chars for r in rows),
        "passages_median": statistics.median(r.passages for r in rows),
    }
