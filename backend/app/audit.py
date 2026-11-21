"""Append-only, hash-chained audit log (plan §11).

Each event's hash covers the previous event's hash, so editing or deleting a
past row breaks the chain. The table also refuses UPDATE/DELETE (DB trigger).
Details hold ids and outcomes only: never passwords, codes, tokens or content.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent

GENESIS = "0" * 64
_LOCK_KEY = 7_415_001  # pg advisory lock serialising appends
_FORBIDDEN = {"password", "code", "token", "secret", "totp", "content", "text", "question"}


def _canonical(
    prev_hash: str, ts: datetime, actor_id, action, target_type, target_id, details: dict
) -> bytes:
    return json.dumps(
        [
            prev_hash,
            ts.astimezone(UTC).isoformat(),
            str(actor_id) if actor_id else None,
            action,
            target_type,
            target_id,
            details,
        ],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()


def compute_hash(
    prev_hash: str, ts: datetime, actor_id, action, target_type, target_id, details: dict
) -> str:
    return hashlib.sha256(
        _canonical(prev_hash, ts, actor_id, action, target_type, target_id, details)
    ).hexdigest()


def _check_details(details: dict) -> None:
    for key in details:
        if any(word in key.lower() for word in _FORBIDDEN):
            raise ValueError(f"audit detail {key!r} looks like a secret or content")


async def record(
    session: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    details: dict | None = None,
) -> AuditEvent:
    details = details or {}
    _check_details(details)
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    prev = (
        await session.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1))
    ).scalar() or GENESIS
    ts = datetime.now(UTC)
    tid = str(target_id) if target_id is not None else None
    event = AuditEvent(
        ts=ts,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=tid,
        details=details,
        prev_hash=prev,
        hash=compute_hash(prev, ts, actor_id, action, target_type, tid, details),
    )
    session.add(event)
    await session.flush()
    return event


ANCHOR_KEY = "audit_anchor"  # vault_state: hash before the oldest kept event


def verify_chain(events: Iterable[AuditEvent], start: str = GENESIS) -> tuple[bool, int | None]:
    """(ok, id of the first bad event). Events must be in id order from the start
    (or from the retention anchor, when the retention job removed older events)."""
    prev = start
    for e in events:
        expected = compute_hash(
            prev, e.ts, e.actor_id, e.action, e.target_type, e.target_id, e.details or {}
        )
        if e.prev_hash != prev or e.hash != expected:
            return False, e.id
        prev = e.hash
    return True, None
