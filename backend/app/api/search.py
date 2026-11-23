"""Search across everything the user may read (plan §9: hybrid, scope-filtered).

The query text is never logged. It is stored (with its vector and how well
it matched) as the user's own search history, which only they see, for
"gaps from your searches" (plan §7); it is deleted after the retention period.
If the local embedding model is unavailable, results come from keyword search
alone and `semantic` is false.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db, get_query_embedder
from app.db.models import SearchEvent
from app.db.scoped import apply_reader_scope
from app.retrieval.search import search

router = APIRouter(tags=["knowledge"])


class HitOut(BaseModel):
    document_id: str
    title: str
    vault_path: str
    doc_type: str
    kind: str
    programme: str | None
    stage: str | None
    heading: str | None
    part: str | None  # slide | page, for citations like "slide 14"
    part_number: int | None
    snippet: str
    score: float
    matched: list[str]


class SearchOut(BaseModel):
    semantic: bool
    results: list[HitOut]


@router.get("/search", response_model=SearchOut)
async def search_endpoint(
    q: str = Query(min_length=2, max_length=500),
    space: str | None = Query(default=None, max_length=64),
    programme: str | None = Query(default=None, max_length=200),
    stage: str | None = Query(default=None, max_length=32),
    doc_type: str | None = Query(default=None, max_length=32),
    kind: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=10, ge=1, le=50),
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    embed_query=Depends(get_query_embedder),
) -> SearchOut:
    q = q.replace("\x00", " ").strip()  # Postgres text can't hold NUL
    vector = None
    try:
        vector = await embed_query(q)
    except Exception:  # noqa: BLE001 - degrade to keyword search
        vector = None
    await session.commit()
    await apply_reader_scope(session, me.principal)
    hits = await search(
        session,
        me.principal,
        q,
        query_vector=vector,
        space=space,
        programme=programme,
        stage=stage,
        doc_type=doc_type,
        kind=kind,
        limit=limit,
    )
    user_id = me.principal.user_id
    await session.rollback()  # leave reader mode before writing the history row
    distances = [h.distance for h in hits if h.distance is not None]
    session.add(
        SearchEvent(
            user_id=user_id,
            query=q,
            vector=vector,
            results=len(hits),
            best_distance=min(distances) if distances else None,
        )
    )
    await session.commit()
    return SearchOut(
        semantic=vector is not None,
        results=[
            HitOut(
                document_id=str(h.document_id),
                title=h.title,
                vault_path=h.vault_path,
                doc_type=h.doc_type,
                kind=h.kind,
                programme=h.programme,
                stage=h.stage,
                heading=h.heading,
                part=h.part,
                part_number=h.part_number,
                snippet=h.snippet,
                score=h.score,
                matched=h.matched,
            )
            for h in hits
        ],
    )
