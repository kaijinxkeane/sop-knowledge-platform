"""Search across everything the user may read (plan §9: hybrid, scope-filtered).

The query text is never logged. It is stored (with its vector and how well
it matched) as the user's own search history, which only they see, for
"gaps from your searches" (plan §7); it is deleted after the retention period.
If the local embedding model is unavailable, results come from keyword search
alone and `semantic` is false.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
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
    search_id: str | None = None  # for POST /search/{id}/outcome
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
    event = SearchEvent(
        user_id=user_id,
        query=q,
        vector=vector,
        results=len(hits),
        best_distance=min(distances) if distances else None,
    )
    session.add(event)
    await session.commit()
    return SearchOut(
        search_id=str(event.id),
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


class OutcomeIn(BaseModel):
    opened: int = Field(ge=0, le=500)  # how many results the user opened
    used: bool  # did any of them help ("this answered it", copy, cite, ...)


@router.post("/search/{search_id}/outcome", status_code=204)
async def search_outcome(
    search_id: uuid.UUID,
    body: OutcomeIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Sent by the Library when the user leaves a results page. Opening several
    results and using none is a gap signal in the user's own "gaps from your
    searches". Counts only: which documents were opened is not stored."""
    event = await session.get(SearchEvent, search_id)
    if event is None or event.user_id != me.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    event.opened = max(event.opened, body.opened)
    event.used = bool(event.used) or body.used  # once useful, stays useful
    await session.commit()
