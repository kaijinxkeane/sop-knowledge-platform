"""Approving one exact version of a document (plan §6).

Approval makes the document's current chunks *live* (used in answers) and
drops the chunks of the previously approved version. Attachments embedded in
the note (decks, worksheets) are approved with it, so a deck swapped in the
vault is not cited until its note is approved again.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentLink, SopApproval, VaultState
from app.governance.versions import with_frontmatter
from app.vault.git import GitVault
from app.vault.labels import VaultConfig

BASELINE_KEY = "governance_baseline"


def review_cycle_days(doc: Document, config: VaultConfig) -> int:
    raw = (doc.frontmatter or {}).get("review_cycle_days")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = config.review_cycle_days
    return days if 1 <= days <= 3650 else config.review_cycle_days


async def promote(s: AsyncSession, doc: Document) -> None:
    """The current version becomes the live one."""
    await s.execute(delete(Chunk).where(Chunk.document_id == doc.id, Chunk.current.is_(False)))
    await s.execute(
        update(Chunk).where(Chunk.document_id == doc.id).values(live=True, current=True)
    )


async def approve(
    s: AsyncSession,
    doc: Document,
    *,
    approver_id: uuid.UUID | None,
    method: str,
    config: VaultConfig,
    request_id: uuid.UUID | None = None,
    today: date | None = None,
) -> SopApproval:
    assert method in ("review", "self", "baseline")
    today = today or datetime.now(UTC).date()
    approval = SopApproval(
        document_id=doc.id,
        git_commit=doc.current_commit,
        content_hash=doc.governed_hash or doc.content_hash or "",
        approved_by=approver_id,
        method=method,
        review_request_id=request_id,
    )
    s.add(approval)
    doc.approved_hash = approval.content_hash
    doc.approved_commit = doc.current_commit
    doc.review_due = today + timedelta(days=review_cycle_days(doc, config))
    if doc.status != "retired":
        doc.status = "published"
    await promote(s, doc)
    # Embedded attachments are approved together with the note.
    embedded = (
        (
            await s.execute(
                select(Document)
                .join(DocumentLink, DocumentLink.to_id == Document.id)
                .where(
                    DocumentLink.from_id == doc.id,
                    DocumentLink.embed.is_(True),
                    Document.kind == "attachment",
                )
            )
        )
        .scalars()
        .all()
    )
    for att in embedded:
        if att.approved_hash != att.governed_hash:
            s.add(
                SopApproval(
                    document_id=att.id,
                    git_commit=att.current_commit,
                    content_hash=att.governed_hash or att.content_hash or "",
                    approved_by=approver_id,
                    method=method,
                    review_request_id=request_id,
                )
            )
            att.approved_hash, att.approved_commit = att.governed_hash, att.current_commit
            await promote(s, att)
    await s.flush()
    return approval


async def baseline_needed(s: AsyncSession) -> bool:
    return await s.get(VaultState, BASELINE_KEY) is None


async def apply_baseline(s: AsyncSession, config: VaultConfig) -> int:
    """First connection of a vault: notes already marked `published` (and all
    attachments) count as approved, recorded as `baseline` so the governance
    report shows they were never reviewed in the platform. Runs once."""
    if not await baseline_needed(s):
        return 0
    docs = (
        (
            await s.execute(
                select(Document).where(
                    Document.approved_hash.is_(None),
                    (Document.kind == "attachment")
                    | (Document.frontmatter["status"].astext == "published"),
                )
            )
        )
        .scalars()
        .all()
    )
    for doc in docs:
        await approve(s, doc, approver_id=None, method="baseline", config=config)
    await s.merge(VaultState(key=BASELINE_KEY, value=datetime.now(UTC).isoformat()))
    return len(docs)


def write_back(
    git: GitVault,
    doc: Document,
    *,
    reviewer: str,
    approved_on: date,
    review_due: date | None,
) -> str | None:
    """Record the approval in the note's frontmatter, as a platform commit.
    These keys are outside the governed hash, so the approval still holds."""
    if doc.kind != "note":
        return None
    full = git.safe_path(doc.vault_path)
    with git.lock():
        text = full.read_text(encoding="utf-8")
        updates = {
            "status": "published" if doc.status != "retired" else "retired",
            "reviewer": reviewer,
            "approved_by": reviewer,
            "approved_on": approved_on.isoformat(),
        }
        if review_due:
            updates["review_due"] = review_due.isoformat()
        new = with_frontmatter(text, updates)
        if new is None or new == text:
            return None
        full.write_text(new, encoding="utf-8")
        return git.commit(
            [doc.vault_path],
            f"Record approval of {doc.vault_path}",
            author_name="SOP Platform",
            author_email="platform@sop.local",
            platform=True,
        )


async def provenance(s: AsyncSession, document_ids) -> dict[uuid.UUID, dict]:
    """Who wrote and who approved the live version of each document (for
    citations: "written by A, approved by B"). Ids and names only."""
    from app.db.models import DocumentVersion, User

    ids = list(set(document_ids))
    if not ids:
        return {}
    docs = {
        d.id: d for d in (await s.execute(select(Document).where(Document.id.in_(ids)))).scalars()
    }
    out: dict[uuid.UUID, dict] = {}
    for doc_id, doc in docs.items():
        if doc.approved_hash is None:
            continue
        approval = (
            await s.execute(
                select(SopApproval)
                .where(SopApproval.document_id == doc_id)
                .order_by(SopApproval.approved_at.desc())
                .limit(1)
            )
        ).scalar()
        author = None
        if doc.approved_commit:
            author = await s.scalar(
                select(DocumentVersion.author_name).where(
                    DocumentVersion.document_id == doc_id,
                    DocumentVersion.git_commit == doc.approved_commit,
                )
            )
        approver = None
        if approval is not None and approval.approved_by is not None:
            approver = await s.scalar(
                select(User.display_name).where(User.id == approval.approved_by)
            )
        out[doc_id] = {
            "written_by": author,
            "approved_by": approver,
            "approval": approval.method if approval is not None else None,
            "approved_on": approval.approved_at.date().isoformat() if approval else None,
        }
    return out
