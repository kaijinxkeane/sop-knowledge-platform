"""Review queue for the AI Classifier's proposals (plan §4.1, §8).

Proposals contain the model's reasoning and quoted passages, so each one is
shown only to people who could read the note at the strictest level that
applies (reviewers of the proposed space, or the note's author).

Who approves what:
- `review` on the space (or the note's author with `contribute`) for
  internal / restricted in that space
- `approve` (the lead) for `public`, or for sharing with another space
- while personal-data safeguards or unconfirmed names remain, nothing looser
  than `restricted` can be approved
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import CurrentUser, current_user, get_db
from app.classify.rules import NAME_FLAGS, may_approve, required_action
from app.classify.service import refresh_name_flags, replace_access
from app.db.models import (
    ClassificationProposal,
    Document,
    DocumentAccess,
    DocumentVersion,
    KnownName,
    Space,
)
from app.policy.engine import Principal, Sensitivity, can_view_document, resolve_sensitivity
from app.vault.labels import Labels, labels_from_rows, vault_config

router = APIRouter(tags=["classification"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")


class SharedIn(BaseModel):
    space: str = Field(max_length=64)
    sensitivity: str = Field(max_length=16)


class LabelsIn(BaseModel):
    space: str = Field(max_length=64)
    sensitivity: str = Field(max_length=16)
    shared_with: list[SharedIn] = Field(default_factory=list, max_length=10)


class ProposalOut(BaseModel):
    id: str
    document_id: str
    title: str
    vault_path: str
    proposed: LabelsIn | None
    current: LabelsIn | None
    confidence: float
    rationale: str
    evidence: list[str]
    names: list[str]
    safeguards: list[str]
    decision: str
    needs: str  # review | approve
    stale: bool  # the note changed since this proposal


class GroupOut(BaseModel):
    group_key: str
    folder: str
    proposed_space: str | None
    proposed_sensitivity: str
    items: list[ProposalOut]


class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class BulkResult(BaseModel):
    id: str
    ok: bool
    error: str | None = None


class NamesIn(BaseModel):
    safe: list[str] = Field(default_factory=list, max_length=50)
    client: list[str] = Field(default_factory=list, max_length=50)


def _labels_out(labels: Labels | None) -> LabelsIn | None:
    if labels is None or labels.space is None:
        return None
    return LabelsIn(
        space=labels.space,
        sensitivity=labels.sensitivity.label,
        shared_with=[SharedIn(space=s, sensitivity=lv.label) for s, lv in labels.shared_with],
    )


def _proposed(p: ClassificationProposal) -> Labels:
    return Labels(
        space=p.proposed_space,
        sensitivity=resolve_sensitivity(p.proposed_sensitivity),
        shared_with=[(s, resolve_sensitivity(lv)) for s, lv in p.proposed_shared_with],
    )


def _may_see(
    principal: Principal,
    p: ClassificationProposal,
    doc: Document,
    author_id=None,
    access: list | None = None,
) -> bool:
    """Who may see a proposal (its title, quotes and rationale are note content).

    - the note's author, always
    - unplaced note (no access rows): only when the author is unknown, the
      triage space's leads. Never the proposed space's reviewers: the AI may
      have picked the wrong space.
    - placed note: someone who can already read the note as labelled now AND
      may review its current or proposed space (approving still needs the
      rights for the new labels).
    """
    if author_id is not None and author_id == principal.user_id:
        return True
    rows = [(a.space, a.sensitivity) for a in (access or [])]
    if not rows:
        if author_id is not None:
            return False
        triage = vault_config().unplaced_reviewers
        return (
            bool(triage)
            and principal.can("approve", triage)
            and principal.can_read(triage, Sensitivity.RESTRICTED)
        )
    if not can_view_document(
        principal, rows, safeguards=doc.safeguards or (), status=doc.status, author_id=author_id
    ):
        return False
    owner = next((a.space for a in access if a.role == "owner"), None)
    return any(principal.can("review", sp) for sp in {owner, p.proposed_space} if sp)


async def _access(session: AsyncSession, doc: Document) -> list[DocumentAccess]:
    return list(
        (
            await session.execute(
                select(DocumentAccess).where(DocumentAccess.document_id == doc.id)
            )
        ).scalars()
    )


async def _author(session: AsyncSession, doc: Document):
    """Who wrote it: the app creator, else the first commit's (matched) author."""
    if doc.author_id is not None:
        return doc.author_id
    return await session.scalar(
        select(DocumentVersion.authored_by)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.committed_at)
        .limit(1)
    )


async def _load(session: AsyncSession, me: CurrentUser, proposal_id: uuid.UUID):
    p = await session.get(ClassificationProposal, proposal_id)
    doc = await session.get(Document, p.document_id) if p else None
    author = await _author(session, doc) if doc else None
    access = await _access(session, doc) if doc else []
    if p is None or doc is None or not _may_see(me.principal, p, doc, author, access):
        raise NOT_FOUND
    return p, doc, author


@router.get("/classifications/queue", response_model=list[GroupOut])
async def queue(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[GroupOut]:
    rows = (
        await session.execute(
            select(ClassificationProposal, Document)
            .join(Document, Document.id == ClassificationProposal.document_id)
            .where(ClassificationProposal.status == "pending")
            .order_by(ClassificationProposal.group_key, Document.vault_path)
        )
    ).all()
    groups: dict[str, list[ProposalOut]] = defaultdict(list)
    for p, doc in rows:
        access = await _access(session, doc)
        if not _may_see(me.principal, p, doc, await _author(session, doc), access):
            continue
        proposed = _proposed(p)
        groups[p.group_key].append(
            ProposalOut(
                id=str(p.id),
                document_id=str(doc.id),
                title=doc.title,
                vault_path=doc.vault_path,
                proposed=_labels_out(proposed),
                current=_labels_out(labels_from_rows(access)),
                confidence=p.confidence,
                rationale=p.rationale,
                evidence=p.evidence,
                names=list(doc.name_hits or []),
                safeguards=list(doc.safeguards or []),
                decision=p.decision,
                needs=required_action(proposed) if proposed.space else "review",
                stale=p.content_hash != doc.content_hash,
            )
        )
    out = []
    for key, items in groups.items():
        folder, space, sens = key.split("|")
        out.append(
            GroupOut(
                group_key=key,
                folder=folder,
                proposed_space=None if space == "unsure" else space,
                proposed_sensitivity=sens,
                items=items,
            )
        )
    return out


async def _approve(
    session: AsyncSession,
    me: CurrentUser,
    p: ClassificationProposal,
    doc: Document,
    edit: LabelsIn | None,
    author=None,
) -> None:
    if p.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "this proposal was already decided")
    if p.content_hash != doc.content_hash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the note changed since this proposal; it will be re-classified",
        )
    spaces = set((await session.execute(select(Space.name))).scalars())
    if edit is not None:
        target = Labels(
            space=edit.space,
            sensitivity=resolve_sensitivity(edit.sensitivity),
            shared_with=[(x.space, resolve_sensitivity(x.sensitivity)) for x in edit.shared_with],
        )
    else:
        target = _proposed(p)
    if target.space not in spaces or any(s not in spaces for s, _ in target.shared_with):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "choose a known space")
    if edit is not None and edit.sensitivity != target.sensitivity.label:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown sensitivity")
    pattern = [x for x in doc.safeguards or [] if x not in NAME_FLAGS]
    if (pattern or doc.name_hits) and target.sensitivity is not Sensitivity.RESTRICTED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "this note contains personal data or unconfirmed names: it can only be restricted "
            "until those are removed or the names are confirmed",
        )
    is_author = author is not None and author == me.user.id
    forward = None
    if not may_approve(me.principal, target, is_author=is_author):
        if await _access(session, doc):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "this decision needs the space lead"
                if required_action(target) == "approve"
                else "you can't approve labels in this space",
            )
        # Unplaced note: whoever may see it (author or triage lead) places it at
        # restricted in the chosen space; that space's reviewers decide the rest.
        forward, target = target, Labels(space=target.space, sensitivity=Sensitivity.RESTRICTED)
    rows = await replace_access(session, doc, target, source="approved_ai", decided_by=me.user.id)
    if forward is not None:
        session.add(
            ClassificationProposal(
                document_id=doc.id,
                content_hash=p.content_hash,
                proposed_space=forward.space,
                proposed_sensitivity=forward.sensitivity.label,
                proposed_shared_with=[[sp, lv.label] for sp, lv in forward.shared_with],
                confidence=p.confidence,
                rationale=p.rationale,
                evidence=p.evidence,
                names=p.names,
                model=p.model,
                status="pending",
                decision="forwarded",
                group_key=p.group_key,
            )
        )
    refresh_name_flags(doc, rows, vault_config())
    p.status, p.reviewed_by, p.reviewed_at = "approved", me.user.id, datetime.now(UTC)
    await audit.record(
        session,
        "classification_approved",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={
            "proposal": str(p.id),
            "edited": edit is not None,
            "space": target.space,
            "sensitivity": target.sensitivity.label,
            "self_approved": is_author,
            "placed_and_forwarded": forward is not None,
        },
    )


@router.post("/classifications/{proposal_id}/approve", status_code=204)
async def approve(
    proposal_id: uuid.UUID,
    edit: LabelsIn | None = None,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    p, doc, author = await _load(session, me, proposal_id)
    await _approve(session, me, p, doc, edit, author)
    await session.commit()


@router.post("/classifications/{proposal_id}/reject", status_code=204)
async def reject(
    proposal_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """The labels in force stay as they are (quarantined or restricted)."""
    p, doc, _ = await _load(session, me, proposal_id)  # seeing it is enough to reject
    if p.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "this proposal was already decided")
    p.status, p.reviewed_by, p.reviewed_at = "rejected", me.user.id, datetime.now(UTC)
    await audit.record(
        session,
        "classification_rejected",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={"proposal": str(p.id)},
    )
    await session.commit()


@router.post("/classifications/bulk-approve", response_model=list[BulkResult])
async def bulk_approve(
    body: BulkIn, me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[BulkResult]:
    """Approve a group as proposed. Each item is checked on its own; one
    refusal does not stop the others."""
    results = []
    for pid in body.ids:
        try:
            async with session.begin_nested():
                p, doc, author = await _load(session, me, pid)
                await _approve(session, me, p, doc, None, author)
            results.append(BulkResult(id=str(pid), ok=True))
        except HTTPException as exc:
            results.append(BulkResult(id=str(pid), ok=False, error=str(exc.detail)))
    await session.commit()
    return results


@router.post("/documents/{document_id}/names", status_code=204)
async def review_names(
    document_id: uuid.UUID,
    body: NamesIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Mark detected names as safe (e.g. a public figure, a venue) or as clients.
    Client names stay restricted; safe names stop flagging this and other notes."""
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NOT_FOUND
    rows = list(
        (
            await session.execute(
                select(DocumentAccess).where(DocumentAccess.document_id == doc.id)
            )
        ).scalars()
    )
    owner = next((r.space for r in rows if r.role == "owner"), None)
    if owner is None or not (
        me.principal.can("review", owner) and me.principal.can_read(owner, Sensitivity.RESTRICTED)
    ):
        raise NOT_FOUND
    hits = set(doc.name_hits or [])
    decided = {n.strip().lower(): "safe" for n in body.safe} | {
        n.strip().lower(): "client" for n in body.client
    }
    if not set(decided) <= hits:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "only names detected in this note can be reviewed here",
        )
    for name, kind in decided.items():
        await session.merge(KnownName(name=name, kind=kind, added_by=me.user.id))
    doc.name_hits = sorted(n for n in hits if decided.get(n) != "safe")
    refresh_name_flags(doc, rows, vault_config())
    await audit.record(
        session,
        "names_reviewed",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={"safe": len(body.safe), "client": len(body.client)},
    )
    await session.commit()


class AccuracyOut(BaseModel):
    space: str
    approved_as_proposed: int
    approved_with_edits: int
    rejected: int
    pending: int


@router.get("/reports/classification-accuracy", response_model=list[AccuracyOut])
async def accuracy(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> list[AccuracyOut]:
    """Counts only (no content): how often reviewers accepted the AI's labels."""
    spaces = [s for s in me.principal.space_actions() if me.principal.can("approve", s)]
    if not spaces:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "for space leads")
    out = []
    for space in sorted(spaces):
        rows = dict(
            (
                await session.execute(
                    select(ClassificationProposal.status, func.count())
                    .where(ClassificationProposal.proposed_space == space)
                    .group_by(ClassificationProposal.status)
                )
            ).all()
        )
        edited = await session.scalar(
            select(func.count())
            .select_from(ClassificationProposal)
            .join(DocumentAccess, DocumentAccess.document_id == ClassificationProposal.document_id)
            .where(
                ClassificationProposal.proposed_space == space,
                ClassificationProposal.status == "approved",
                DocumentAccess.role == "owner",
                (DocumentAccess.space != ClassificationProposal.proposed_space)
                | (DocumentAccess.sensitivity != ClassificationProposal.proposed_sensitivity),
            )
        )
        approved = rows.get("approved", 0)
        out.append(
            AccuracyOut(
                space=space,
                approved_as_proposed=approved - (edited or 0),
                approved_with_edits=edited or 0,
                rejected=rows.get("rejected", 0),
                pending=rows.get("pending", 0),
            )
        )
    return out
