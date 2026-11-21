"""Hybrid search: vector similarity + full text, fused by reciprocal rank (plan §9).

Must run in a session already under `apply_reader_scope`: RLS limits every
table to what the user may read, *before* ranking. Results are checked again
with the policy engine.

Semantic matches further than MAX_DISTANCE (cosine) are dropped, so a question
nothing answers returns nothing instead of the nearest unrelated passages
(qwen3-embedding:0.6b on the demo vault: relevant ~0.30-0.55, unrelated
~0.70+). Keyword matching needs every query word, unless there is no query
vector (embedding model down): then any word counts, ranked by coverage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.policy.engine import Principal, document_visible

RRF_K = 60
CANDIDATES = 40
MAX_DISTANCE = 0.65


@dataclass
class Hit:
    document_id: uuid.UUID
    title: str
    vault_path: str
    doc_type: str
    kind: str
    programme: str | None
    stage: str | None
    heading: str | None
    part: str | None
    part_number: int | None
    snippet: str
    score: float
    matched: list[str]


def _filters(space, programme, stage, doc_type, kind) -> tuple[str, dict]:
    where, params = [], {}
    if space:
        where.append(
            "EXISTS (SELECT 1 FROM document_access a WHERE a.document_id = d.id "
            "AND a.space = :space)"
        )
        params["space"] = space
    for col, val in (
        ("programme", programme),
        ("stage", stage),
        ("doc_type", doc_type),
        ("kind", kind),
    ):
        if val:
            where.append(f"d.{col} = :{col}")
            params[col] = val
    return (" AND " + " AND ".join(where)) if where else "", params


async def search(
    session: AsyncSession,
    principal: Principal,
    query: str,
    *,
    query_vector: list[float] | None = None,
    space: str | None = None,
    programme: str | None = None,
    stage: str | None = None,
    doc_type: str | None = None,
    kind: str | None = None,
    limit: int = 10,
    max_distance: float = MAX_DISTANCE,
) -> list[Hit]:
    extra, params = _filters(space, programme, stage, doc_type, kind)
    params |= {"q": query, "n": CANDIDATES}
    tsquery = (
        "websearch_to_tsquery('english', :q)"
        if query_vector is not None
        # any word: turn the AND query into an OR query
        else "CAST(NULLIF(replace(CAST(plainto_tsquery('english', :q) AS text), '&', '|'), '') "
        "AS tsquery)"
    )
    ranks: dict[uuid.UUID, dict[str, int]] = {}

    keyword = await session.execute(
        text(f"""
        SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id,
             {tsquery} query
        WHERE (c.tsv @@ query OR to_tsvector('english', d.title) @@ query) {extra}
        ORDER BY ts_rank_cd(c.tsv, query)
               + CASE WHEN to_tsvector('english', d.title) @@ query THEN 0.5 ELSE 0 END DESC
        LIMIT :n"""),
        params,
    )
    for rank, (cid,) in enumerate(keyword.all()):
        ranks.setdefault(cid, {})["keyword"] = rank

    if query_vector is not None:
        vec = "[" + ",".join(f"{x:.6f}" for x in query_vector) + "]"
        semantic = await session.execute(
            text(f"""
            SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND c.embedding <=> CAST(:vec AS vector) <= :maxd {extra}
            ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :n"""),
            params | {"vec": vec, "maxd": max_distance},
        )
        for rank, (cid,) in enumerate(semantic.all()):
            ranks.setdefault(cid, {})["semantic"] = rank

    if not ranks:
        return []
    scored = sorted(
        ((sum(1 / (RRF_K + r) for r in m.values()), cid, sorted(m)) for cid, m in ranks.items()),
        reverse=True,
    )[: limit * 3]
    ids = [cid for _, cid, _ in scored]
    rows = {
        r.id: r
        for r in (
            await session.execute(
                text("""
        SELECT c.id, c.document_id, c.heading, c.part, c.part_number,
               ts_headline('english', c.text, plainto_tsquery('english', :q),
                           'MaxWords=40, MinWords=15, MaxFragments=2') AS snippet
        FROM chunks c WHERE c.id = ANY(:ids)"""),
                {"q": query, "ids": ids},
            )
        ).all()
    }

    docs: dict[uuid.UUID, Document] = {}
    hits: list[Hit] = []
    per_doc: dict[uuid.UUID, int] = {}
    for score, cid, matched in scored:
        row = rows.get(cid)
        if row is None:
            continue
        doc = docs.get(row.document_id) or await session.get(Document, row.document_id)
        if doc is None:
            continue
        docs[doc.id] = doc
        # Second, independent check (the policy engine), on top of RLS.
        if not document_visible(principal, [(a.space, a.sensitivity) for a in doc.access]):
            continue
        if per_doc.get(doc.id, 0) >= 2:  # at most two passages per document
            continue
        per_doc[doc.id] = per_doc.get(doc.id, 0) + 1
        hits.append(
            Hit(
                document_id=doc.id,
                title=doc.title,
                vault_path=doc.vault_path,
                doc_type=doc.doc_type,
                kind=doc.kind,
                programme=doc.programme,
                stage=doc.stage,
                heading=row.heading,
                part=row.part,
                part_number=row.part_number,
                snippet=row.snippet,
                score=round(score, 5),
                matched=matched,
            )
        )
        if len(hits) >= limit:
            break
    return hits
