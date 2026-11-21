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
from app.db.scoped import visible
from app.policy.engine import Principal

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
    space: str | None = None  # owning space (for routing and answer sections)
    distance: float | None = None  # cosine distance, when matched semantically
    text: str = ""  # the full passage, for answering
    version: str | None = None  # git commit of the indexed version
    chunk_id: uuid.UUID | None = None
    ord: int | None = None  # position of the passage in its document


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
    distances: dict[uuid.UUID, float] = {}

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
            SELECT c.id, c.embedding <=> CAST(:vec AS vector) AS dist
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND c.embedding <=> CAST(:vec AS vector) <= :maxd {extra}
            ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :n"""),
            params | {"vec": vec, "maxd": max_distance},
        )
        for rank, (cid, dist) in enumerate(semantic.all()):
            ranks.setdefault(cid, {})["semantic"] = rank
            distances[cid] = float(dist)

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
        SELECT c.id, c.document_id, c.ord, c.heading, c.part, c.part_number, c.text,
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
        if not visible(principal, doc):
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
                # owner space, or the shared space the user reads it through
                space=next(
                    (a.space for a in sorted(doc.access, key=lambda a: a.role != "owner")), None
                ),
                distance=distances.get(cid),
                text=row.text,
                version=doc.current_commit,
                chunk_id=row.id,
                ord=row.ord,
            )
        )
        if len(hits) >= limit:
            break
    return hits


EXPAND_DOC_CHARS = 4000  # a document this short is passed whole
CONTEXT_BUDGET = 8000  # characters of passages per department agent


async def expand(
    session: AsyncSession,
    hits: list[Hit],
    *,
    doc_chars: int = EXPAND_DOC_CHARS,
    budget: int = CONTEXT_BUDGET,
) -> list[Hit]:
    """Small-to-big: turn passage hits into answerable context.

    A matched document short enough is passed whole, in its own order (so
    "the full agenda" sees every section); a longer one gets each matched
    passage plus its neighbours. Documents keep their rank order and stop at
    `budget`. Only documents already in `hits` are read, inside the same
    RLS-scoped session, so this can never widen what the user can see.
    """
    if not hits:
        return hits
    by_doc: dict[uuid.UUID, list[Hit]] = {}
    for h in hits:
        by_doc.setdefault(h.document_id, []).append(h)
    rows = (
        await session.execute(
            text("""
            SELECT id, document_id, ord, heading, part, part_number, text FROM chunks
            WHERE document_id = ANY(:ids) ORDER BY document_id, ord"""),
            {"ids": list(by_doc)},
        )
    ).all()
    chunks: dict[uuid.UUID, list] = {}
    for r in rows:
        chunks.setdefault(r.document_id, []).append(r)

    out: list[Hit] = []
    used = 0
    for doc_id, doc_hits in by_doc.items():
        best, all_rows = doc_hits[0], chunks.get(doc_id, [])
        if sum(len(r.text) for r in all_rows) <= doc_chars:
            keep = all_rows
        else:
            near = {h.ord + d for h in doc_hits if h.ord is not None for d in (-1, 0, 1)}
            keep = [r for r in all_rows if r.ord in near]
        size = sum(len(r.text) for r in keep)
        if out and used + size > budget:
            # no room for the whole set: fall back to the matched passages only
            keep = [r for r in all_rows if r.id in {h.chunk_id for h in doc_hits}]
            size = sum(len(r.text) for r in keep)
            if used + size > budget:
                continue
        used += size
        for r in keep:
            match = next((h for h in doc_hits if h.chunk_id == r.id), None)
            out.append(
                Hit(
                    document_id=doc_id,
                    title=best.title,
                    vault_path=best.vault_path,
                    doc_type=best.doc_type,
                    kind=best.kind,
                    programme=best.programme,
                    stage=best.stage,
                    heading=r.heading,
                    part=r.part,
                    part_number=r.part_number,
                    snippet=match.snippet if match else "",
                    score=best.score,
                    matched=match.matched if match else ["context"],
                    space=best.space,
                    distance=match.distance if match else None,
                    text=r.text,
                    version=best.version,
                    chunk_id=r.id,
                    ord=r.ord,
                )
            )
    return out
