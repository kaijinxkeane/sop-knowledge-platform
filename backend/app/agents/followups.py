"""Follow-up chips for an answer (frontend spec §4), made without a model.

Each suggestion is another section of an SOP the answer cited: its heading,
read under the asker's own RLS scope and from approved (live) text only, so a
chip never points at something the asker can't open or that isn't approved.
Headings are document text: shown as plain text, never used as instructions.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.scoped import apply_reader_scope, visible
from app.policy.engine import Principal
from app.retrieval.search import LIVE

MAX = 3
_PATH = re.compile(r"\s*[›>]\s*")  # headings are stored as "Title › Section"
_PART = re.compile(r"^(slide|page)\s+\d+\s*[:.\-–]?\s*", re.I)
_SKIP = {"", "overview", "contents", "table of contents", "summary", "notes", "references"}


def _leaf(heading: str | None) -> str:
    leaf = _PATH.split(heading or "")[-1].strip()
    return _PART.sub("", leaf).strip()[:120]


async def followups(
    session: AsyncSession, principal: Principal, cited: list[tuple[str, str | None]]
) -> list[dict]:
    """Up to three {document_id, title, heading} from the cited documents'
    other sections, nearest after the cited one first. `cited` is
    [(document_id, heading)] in citation order. The session must be fresh:
    this applies the reader scope and leaves it open for the caller to end."""
    order: list[uuid.UUID] = []
    used: dict[uuid.UUID, set[str]] = {}
    for doc_id, heading in cited:
        try:
            d = uuid.UUID(str(doc_id))
        except ValueError:
            continue
        if d not in used:
            order.append(d)
            used[d] = set()
        used[d].add(_leaf(heading).lower())
    if not order:
        return []
    await apply_reader_scope(session, principal)
    per_doc: list[list[dict]] = []
    for d in order[:MAX]:
        doc = await session.get(Document, d)
        if doc is None or not visible(principal, doc):
            continue
        rows = (
            await session.execute(
                text(
                    f"SELECT c.heading FROM chunks c JOIN documents d ON d.id = c.document_id "
                    f"WHERE c.document_id = :d AND {LIVE} ORDER BY c.ord"
                ),
                {"d": d},
            )
        ).scalars()
        leaves: list[str] = []
        for h in rows:
            leaf = _leaf(h)
            if leaf.lower() not in {x.lower() for x in leaves}:
                leaves.append(leaf)
        cited_at = [i for i, x in enumerate(leaves) if x.lower() in used[d]]
        start = (max(cited_at) + 1) if cited_at else 0
        ranked = leaves[start:] + leaves[:start]
        skip = used[d] | _SKIP | {doc.title.strip().lower()}
        per_doc.append(
            [
                {"document_id": str(d), "title": doc.title, "heading": x}
                for x in ranked
                if x.lower() not in skip
            ]
        )
    out: list[dict] = []
    while len(out) < MAX and any(per_doc):
        for items in per_doc:  # one from each cited document in turn
            if items and len(out) < MAX:
                out.append(items.pop(0))
    return out
