"""24-month retention (plan §11): delete records older than the configured
period. Confirmed with the auditor on 2026-11-20.

Deleted: conversations (with their messages, citations, feedback and gap
events), searches, gap events from searches/requests, notifications, webhook
deliveries and audit events. The audit log stays verifiable: the hash before
the oldest kept event is stored as the chain's new anchor, and deleting audit
rows is only possible inside this job (the table trigger checks
`sop.retention_job`). Handovers and SOPs are company knowledge and are kept.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import audit
from app.db.models import (
    AuditEvent,
    Conversation,
    GapEvent,
    Notification,
    SearchEvent,
    VaultState,
    WebhookDelivery,
)

log = logging.getLogger("sop.retention")


def cutoff_for(months: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    year, month = divmod(now.month - 1 - months, 12)
    year, month = now.year + year, month + 1
    day = min(now.day, 28)
    return now.replace(year=year, month=month, day=day)


async def apply_retention(
    sessions: async_sessionmaker, months: int, *, now: datetime | None = None
) -> dict:
    cutoff = cutoff_for(months, now)
    out: dict[str, int] = {}
    async with sessions() as s, s.begin():
        for name, model, col in (
            ("conversations", Conversation, Conversation.updated_at),
            ("searches", SearchEvent, SearchEvent.created_at),
            ("gap_events", GapEvent, GapEvent.created_at),
            ("notifications", Notification, Notification.created_at),
            ("webhook_deliveries", WebhookDelivery, WebhookDelivery.created_at),
        ):
            out[name] = (await s.execute(delete(model).where(col < cutoff))).rowcount or 0
        # Audit log: keep the chain verifiable from the oldest kept event.
        await s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": audit._LOCK_KEY})
        last_old = (
            await s.execute(
                select(AuditEvent)
                .where(AuditEvent.ts < cutoff)
                .order_by(AuditEvent.id.desc())
                .limit(1)
            )
        ).scalar()
        if last_old is not None:
            await s.merge(VaultState(key=audit.ANCHOR_KEY, value=last_old.hash))
            await s.execute(text("SELECT set_config('sop.retention_job', 'on', true)"))
            out["audit_events"] = (
                await s.execute(delete(AuditEvent).where(AuditEvent.id <= last_old.id))
            ).rowcount or 0
            await s.execute(text("SELECT set_config('sop.retention_job', 'off', true)"))
        else:
            out["audit_events"] = 0
        await audit.record(
            s, "retention_applied", details={"months": months, **{k: v for k, v in out.items()}}
        )
    log.info("retention_applied", extra={"fields": out})
    return out
