"""Run reads under Postgres row-level security for one user (plan §4, defence in depth).

Inside the current transaction this switches to the `sop_reader` role, which
has RLS policies, and publishes the user's scopes as `sop.scopes`. Both reset
when the transaction ends, so a pooled connection never leaks them.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.engine import Principal, edit_spaces


async def apply_reader_scope(session: AsyncSession, principal: Principal) -> None:
    if not session.in_transaction():
        await session.begin()
    scopes = {space: level.label for space, level in principal.scopes().items()}
    review = sorted(s for s, acts in principal.space_actions().items() if "review" in acts)
    await session.execute(text("SET LOCAL ROLE sop_reader"))
    await session.execute(
        text(
            "SELECT set_config('sop.scopes', :scopes, true), "
            "set_config('sop.user_id', :uid, true), "
            "set_config('sop.review_spaces', :review, true), "
            "set_config('sop.edit_spaces', :edit, true)"
        ),
        {
            "scopes": json.dumps(scopes),
            "uid": str(principal.user_id),
            "review": json.dumps(review),
            "edit": json.dumps(edit_spaces(principal)),
        },
    )


def visible(principal: Principal, doc) -> bool:
    """Policy-engine check for a loaded Document (the second check, after RLS)."""
    from app.policy.engine import can_view_document

    return can_view_document(
        principal,
        [(a.space, a.sensitivity) for a in doc.access],
        safeguards=doc.safeguards or (),
        status=doc.status,
        author_id=doc.author_id,
        readers=[r.user_id for r in doc.readers],
    )


def sees_latest(principal: Principal, doc) -> bool:
    """Twin of sop_doc_wip_visible(): does this user get the latest text of a
    visible document (else the approved version)? Yes if it was never approved,
    or if they are its author or have contribute/review on one of its spaces."""
    from app.policy.engine import can_see_unapproved

    if not visible(principal, doc):
        return False
    return doc.approved_hash is None or can_see_unapproved(
        principal, [(a.space, a.sensitivity) for a in doc.access], author_id=doc.author_id
    )


def has_pending_change(doc) -> bool:
    """An approved document whose latest version is not the approved one."""
    return doc.approved_hash is not None and doc.governed_hash != doc.approved_hash
