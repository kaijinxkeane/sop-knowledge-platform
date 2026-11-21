"""Run reads under Postgres row-level security for one user (plan §4, defence in depth).

Inside the current transaction this switches to the `sop_reader` role, which
has RLS policies, and publishes the user's scopes as `sop.scopes`. Both reset
when the transaction ends, so a pooled connection never leaks them.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.engine import Principal


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
            "set_config('sop.review_spaces', :review, true)"
        ),
        {"scopes": json.dumps(scopes), "uid": str(principal.user_id), "review": json.dumps(review)},
    )
