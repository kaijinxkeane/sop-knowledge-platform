"""Required reading and sign-off (frontend spec §9.2, §11).

  POST   /reading-assignments            a space lead: must-read for people or roles, due date
  DELETE /reading-assignments/{id}
  GET    /documents/{id}/reading         my status for one SOP (for the reader)
  POST   /documents/{id}/acknowledge     "I have read version N"
  GET    /me/required-reading            what I must read (only documents I can open)
  GET    /reports/read-status            a lead: who has or hasn't read, overdue

Hidden documents are 404, like everywhere else. Acknowledgements are
append-only; audit details hold ids and counts only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, clock
from app.api.deps import CurrentUser, current_user, get_db
from app.db.models import (
    Document,
    ReadAcknowledgement,
    ReadingAssignment,
    Role,
    User,
)
from app.db.scoped import apply_reader_scope, visible
from app.governance.history import owner_space
from app.governance.notify import notify
from app.governance.reading import (
    applies_to,
    assignees,
    assignments_for,
    earliest_due,
    live_approval,
    valid_acks,
    version_number,
)
from app.identity import principal_for

router = APIRouter(tags=["reading"])
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "not found")


class ReadingAssignIn(BaseModel):
    document_id: uuid.UUID
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    roles: list[str] = Field(default_factory=list, max_length=20)
    due_on: date | None = None


class ReadingAssignmentOut(BaseModel):
    id: str
    document_id: str
    target_type: str
    target: str  # role name, or the person's display name
    due_on: date | None


class StatusOut(BaseModel):
    document_id: str
    required: bool
    due_on: date | None
    overdue: bool
    current_version: int | None  # None: never approved, nothing to acknowledge
    acknowledged_version: int | None  # the version read, if it still counts
    acknowledged_at: datetime | None
    reread: bool  # read before a material change: read again


class RequiredOut(BaseModel):
    document_id: str
    title: str
    due_on: date | None
    overdue: bool
    acknowledged_at: datetime | None
    current_version: int | None
    reread: bool


class PersonStatus(BaseModel):
    name: str
    due_on: date | None
    overdue: bool
    acknowledged_at: datetime | None
    version: int | None
    can_read: bool  # assigned but the labels don't let them read it: a gap to fix


class DocStatus(BaseModel):
    document_id: str
    title: str
    space: str | None
    current_version: int | None
    assignments: list[ReadingAssignmentOut]
    people: list[PersonStatus]


async def _readable(session: AsyncSession, me: CurrentUser, doc_id: uuid.UUID) -> Document:
    await session.commit()
    await apply_reader_scope(session, me.principal)
    doc = await session.get(Document, doc_id)
    ok = doc is not None and visible(me.principal, doc)
    await session.commit()
    if not ok:
        raise NOT_FOUND
    await session.refresh(doc)
    return doc


async def _status(session: AsyncSession, me: CurrentUser, doc: Document) -> StatusOut:
    mine = [a for a in await assignments_for(session, me.user) if a.document_id == doc.id]
    live = await live_approval(session, doc)
    current = await version_number(session, live) if live else None
    ack = (await valid_acks(session, doc.id, [me.user.id])).get(me.user.id)
    ack_version = None
    if ack is not None:
        ack_version = ack.version
    ever = await session.scalar(
        select(ReadAcknowledgement.id)
        .where(
            ReadAcknowledgement.document_id == doc.id,
            ReadAcknowledgement.user_id == me.user.id,
        )
        .limit(1)
    )
    due = earliest_due(mine, me.user)
    today = clock.today()
    return StatusOut(
        document_id=str(doc.id),
        required=bool(mine),
        due_on=due,
        overdue=bool(mine) and ack is None and due is not None and due < today,
        current_version=current,
        acknowledged_version=ack_version,
        acknowledged_at=ack.acknowledged_at if ack else None,
        reread=ack is None and ever is not None,
    )


def _lead(me: CurrentUser, doc: Document) -> str:
    space = owner_space(doc)
    if space is None or not me.principal.can("approve", space):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the space's lead can assign reading")
    return space


@router.post("/reading-assignments", response_model=list[ReadingAssignmentOut], status_code=201)
async def assign(
    body: ReadingAssignIn,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ReadingAssignmentOut]:
    doc = await _readable(session, me, body.document_id)
    _lead(me, doc)
    if doc.kind != "note" or doc.approved_hash is None or doc.status == "retired":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "only approved SOPs can be assigned as required reading"
        )
    if not body.user_ids and not body.roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "choose people or roles")
    known_roles = set((await session.execute(select(Role.name))).scalars())
    if set(body.roles) - known_roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown role")
    active = set(
        (
            await session.execute(
                select(User.id).where(User.id.in_(body.user_ids), User.is_active.is_(True))
            )
        ).scalars()
    )
    if set(body.user_ids) - active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown person")
    targets = [("user", str(u)) for u in dict.fromkeys(body.user_ids)] + [
        ("role", r) for r in dict.fromkeys(body.roles)
    ]
    existing = {
        (a.target_type, a.target): a
        for a in (
            await session.execute(
                select(ReadingAssignment).where(ReadingAssignment.document_id == doc.id)
            )
        ).scalars()
    }
    out = []
    for kind, target in targets:
        a = existing.get((kind, target))
        if a is None:
            a = ReadingAssignment(
                document_id=doc.id,
                target_type=kind,
                target=target,
                due_on=body.due_on,
                assigned_by=me.user.id,
            )
            session.add(a)
        else:
            a.due_on = body.due_on
        out.append(a)
    await session.flush()
    people = await assignees(session, out)
    await notify(
        session, [u.id for u in people], "reading_assigned", document_id=doc.id, skip=me.user.id
    )
    await audit.record(
        session,
        "reading_assigned",
        actor_id=me.user.id,
        target_type="document",
        target_id=doc.id,
        details={"users": len(body.user_ids), "roles": len(body.roles), "people": len(people)},
    )
    await session.commit()
    names = await _user_names(session, out)
    return [_assignment_out(a, names) for a in out]


async def _user_names(session: AsyncSession, rows: list[ReadingAssignment]) -> dict[str, str]:
    ids = [uuid.UUID(a.target) for a in rows if a.target_type == "user"]
    if not ids:
        return {}
    res = await session.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {str(i): n for i, n in res.all()}


def _assignment_out(a: ReadingAssignment, names: dict[str, str]) -> ReadingAssignmentOut:
    return ReadingAssignmentOut(
        id=str(a.id),
        document_id=str(a.document_id),
        target_type=a.target_type,
        target=names.get(a.target, "unknown") if a.target_type == "user" else a.target,
        due_on=a.due_on,
    )


class RoleName(BaseModel):
    name: str
    description: str


@router.get("/reading-assignments/roles", response_model=list[RoleName])
async def assignable_roles(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RoleName]:
    """Role names a lead can assign reading to (names only, no grants or members)."""
    if not any("approve" in acts for acts in me.principal.space_actions().values()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only space leads")
    rows = (await session.execute(select(Role.name, Role.description).order_by(Role.name))).all()
    return [RoleName(name=n, description=d or "") for n, d in rows]


@router.delete("/reading-assignments/{assignment_id}", status_code=204)
async def unassign(
    assignment_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    a = await session.get(ReadingAssignment, assignment_id)
    if a is None:
        raise NOT_FOUND
    doc = await _readable(session, me, a.document_id)
    _lead(me, doc)
    a = await session.get(ReadingAssignment, assignment_id)
    await session.delete(a)
    await audit.record(
        session, "reading_unassigned", actor_id=me.user.id, target_type="document", target_id=doc.id
    )
    await session.commit()


@router.get("/documents/{document_id}/reading", response_model=StatusOut)
async def reading_status(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> StatusOut:
    doc = await _readable(session, me, document_id)
    return await _status(session, me, doc)


@router.post("/documents/{document_id}/acknowledge", response_model=StatusOut)
async def acknowledge(
    document_id: uuid.UUID,
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> StatusOut:
    doc = await _readable(session, me, document_id)
    live = await live_approval(session, doc)
    if live is None or doc.status == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "this document has no approved version")
    current = (await valid_acks(session, doc.id, [me.user.id])).get(me.user.id)
    if current is None or current.approval_id != live.id:
        session.add(
            ReadAcknowledgement(
                user_id=me.user.id,
                document_id=doc.id,
                approval_id=live.id,
                version=await version_number(session, live),
                git_commit=live.git_commit,
            )
        )
        await audit.record(
            session,
            "reading_acknowledged",
            actor_id=me.user.id,
            target_type="document",
            target_id=doc.id,
            details={"commit": live.git_commit},
        )
        await session.commit()
    return await _status(session, me, doc)


@router.get("/me/required-reading", response_model=list[RequiredOut])
async def my_required(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RequiredOut]:
    mine = await assignments_for(session, me.user)
    doc_ids = list(dict.fromkeys(a.document_id for a in mine))
    await session.commit()
    await apply_reader_scope(session, me.principal)
    docs = []
    for i in doc_ids:
        d = await session.get(Document, i)
        # Assigned but not readable (labels changed): not shown, not even the title.
        if d is not None and visible(me.principal, d) and d.status != "retired":
            docs.append(d.id)
    await session.commit()
    out = []
    for i in docs:
        d = await session.get(Document, i)
        st = await _status(session, me, d)
        out.append(
            RequiredOut(
                document_id=str(d.id),
                title=d.title,
                due_on=st.due_on,
                overdue=st.overdue,
                acknowledged_at=st.acknowledged_at,
                current_version=st.current_version,
                reread=st.reread,
            )
        )
    out.sort(key=lambda r: (r.acknowledged_at is not None, r.due_on or date.max))
    return out


@router.get("/reports/read-status", response_model=list[DocStatus])
async def read_status(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    space: str | None = Query(default=None, max_length=64),
) -> list[DocStatus]:
    """For a space's leads: every assigned SOP, who must read it and who has."""
    leads = [s for s, acts in me.principal.space_actions().items() if "approve" in acts]
    if space is not None:
        leads = [s for s in leads if s == space]
    if not leads:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only space leads")
    rows = (await session.execute(select(ReadingAssignment))).scalars().all()
    by_doc: dict[uuid.UUID, list[ReadingAssignment]] = {}
    for a in rows:
        by_doc.setdefault(a.document_id, []).append(a)
    today = clock.today()
    out = []
    for doc_id, assigned in by_doc.items():
        doc = await session.get(Document, doc_id)
        if doc is None or owner_space(doc) not in leads or not visible(me.principal, doc):
            continue
        people = await assignees(session, assigned)
        acks = await valid_acks(session, doc.id, [u.id for u in people])
        live = await live_approval(session, doc)
        names = await _user_names(session, assigned)
        statuses = []
        for u in sorted(people, key=lambda u: u.display_name):
            ack = acks.get(u.id)
            due = earliest_due(assigned, u)
            statuses.append(
                PersonStatus(
                    name=u.display_name,
                    due_on=due,
                    overdue=ack is None and due is not None and due < today,
                    acknowledged_at=ack.acknowledged_at if ack else None,
                    version=ack.version if ack else None,
                    can_read=visible(principal_for(u), doc),
                )
            )
        out.append(
            DocStatus(
                document_id=str(doc.id),
                title=doc.title,
                space=owner_space(doc),
                current_version=await version_number(session, live) if live else None,
                assignments=[_assignment_out(a, names) for a in assigned],
                people=statuses,
            )
        )
    out.sort(key=lambda d: d.title.lower())
    return out


__all__ = ["router", "applies_to"]
