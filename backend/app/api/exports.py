"""PDF export (frontend spec §9.3).

  POST /exports   {document_id} or {programme, stage}  ->  application/pdf

Only notes the user can read are exported, as they would read them (the
approved version, or their own latest if they edit it). Hidden documents are
404. A space can switch export off (`pdf_export: false` in config/spaces).
Restricted content gets a watermark with the reader's name and the date.
Every export is written to the audit log (ids and counts only).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, clock
from app.api.deps import CurrentUser, current_user, get_db, get_git
from app.api.notes import read_for
from app.db.models import Document, User
from app.db.scoped import apply_reader_scope, has_pending_change, sees_latest, visible
from app.governance.export import ExportDoc, ExportJob, render_pdf
from app.governance.history import owner_space
from app.governance.reading import live_approval, version_number
from app.policy.engine import Sensitivity, effective_access
from app.spaces import space_profiles
from app.vault.git import GitVault

router = APIRouter(tags=["exports"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")
MAX_DOCS = 60


class ExportIn(BaseModel):
    document_id: uuid.UUID | None = None
    programme: str | None = Field(default=None, max_length=200)
    stage: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def one_kind(self):
        if (self.document_id is None) == (self.programme is None or self.stage is None):
            raise ValueError("give document_id, or programme and stage")
        return self


def _restricted(doc: Document) -> bool:
    rows = effective_access([(a.space, a.sensitivity) for a in doc.access], doc.safeguards or ())
    return not rows or any(s == Sensitivity.RESTRICTED for _, s in rows)


def _exportable(doc: Document) -> bool:
    space = owner_space(doc)
    profile = space_profiles().get(space) if space else None
    return profile is None or profile.pdf_export


@router.post(
    "/exports",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def export_pdf(
    body: ExportIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    git: GitVault = Depends(get_git),
) -> Response:
    await session.commit()
    await apply_reader_scope(session, me.principal)
    if body.document_id is not None:
        doc = await session.get(Document, body.document_id)
        if doc is None or not visible(me.principal, doc):
            raise NOT_FOUND
        if doc.kind != "note":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "only notes export to PDF")
        docs = [doc]
    else:
        rows = (
            await session.execute(
                select(Document)
                .where(
                    Document.kind == "note",
                    Document.programme == body.programme,
                    Document.stage == body.stage,
                    Document.status != "retired",
                )
                .order_by(Document.title)
            )
        ).scalars()
        docs = [d for d in rows if visible(me.principal, d)][:MAX_DOCS]
        if not docs:
            raise NOT_FOUND
    if not all(_exportable(d) for d in docs):
        # Say which rule stopped it without naming anything else.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PDF export is turned off for this space")

    # Read what this user may read, while still under their RLS scope.
    picked = []
    for d in docs:
        try:
            text = read_for(me, d, git).decode("utf-8", errors="replace")
        except (OSError, ValueError, HTTPException):
            raise NOT_FOUND from None
        draft = has_pending_change(d) and sees_latest(me.principal, d)
        picked.append((d.id, d.title, d.owner, d.author_id, text, draft, _restricted(d)))
    await session.commit()

    out = []
    for doc_id, title, owner, author_id, text, draft, _ in picked:
        doc = await session.get(Document, doc_id)
        live = await live_approval(session, doc)
        n = await version_number(session, live) if live else None
        if n is None:
            version = "Draft (not approved yet)"
        elif draft:
            version = f"Draft (after version {n})"
        else:
            version = f"Version {n}"
        approver = await session.get(User, live.approved_by) if live and live.approved_by else None
        author = await session.get(User, author_id) if author_id else None
        out.append(
            ExportDoc(
                title=title,
                text=text,
                version=version,
                sop_id=str(doc_id)[:8].upper(),
                owner=owner,
                author=author.display_name if author else None,
                approver=approver.display_name if approver else None,
                approved_on=clock.local_date(live.approved_at) if live else None,
            )
        )
    restricted = any(p[-1] for p in picked)
    today = clock.today()
    pdf = render_pdf(
        ExportJob(
            docs=out,
            printed_by=me.user.display_name,
            printed_on=today,
            restricted=restricted,
            heading=f"{body.programme} · {body.stage}" if body.document_id is None else None,
        )
    )
    await audit.record(
        session,
        "pdf_exported",
        actor_id=me.user.id,
        target_type="document" if body.document_id else "stage",
        target_id=body.document_id,
        details={"documents": [str(p[0]) for p in picked], "restricted": restricted},
    )
    await session.commit()
    name = "sop.pdf" if body.document_id else "stage.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
