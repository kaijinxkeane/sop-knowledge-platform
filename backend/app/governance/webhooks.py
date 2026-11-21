"""Outbound webhooks (plan §8): review requested, SOP published, review due.

Subscribers are listed in config/webhooks.yaml. Events go into an outbox table
in the same transaction as the change, and a worker job delivers them, signed
with HMAC-SHA256 (`X-SOP-Signature: sha256=<hex>`) when the subscriber has a
secret. Payloads hold ids, spaces and times only, never titles or text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import httpx
import yaml
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import WebhookDelivery

log = logging.getLogger("sop.webhooks")
EVENTS = frozenset({"review_requested", "sop_published", "review_due", "changes_requested"})
MAX_ATTEMPTS = 6
_ALLOWED_KEYS = {"event", "document_id", "space", "review_id", "commit", "at", "due"}


@dataclass(frozen=True)
class Subscriber:
    url: str
    events: frozenset[str]
    secret_env: str | None = None


def load_subscribers(config_dir: Path | None = None) -> tuple[Subscriber, ...]:
    path = (config_dir or get_settings().config_dir) / "webhooks.yaml"
    if not path.is_file():
        return ()
    data = yaml.safe_load(path.read_text()) or {}
    subs = []
    for w in data.get("webhooks") or []:
        url = str(w.get("url") or "")
        if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("webhook urls must use https (or localhost for testing)")
        events = frozenset(w.get("events") or EVENTS)
        if events - EVENTS:
            raise ValueError(f"unknown webhook events: {sorted(events - EVENTS)}")
        subs.append(Subscriber(url, events, w.get("secret_env")))
    return tuple(subs)


@lru_cache(maxsize=1)
def subscribers() -> tuple[Subscriber, ...]:
    return load_subscribers()


async def emit(s: AsyncSession, event: str, subs=None, **fields) -> int:
    assert event in EVENTS, event
    payload = {"event": event, "at": datetime.now(UTC).isoformat(), **fields}
    bad = set(payload) - _ALLOWED_KEYS
    assert not bad, f"webhook payloads hold ids only; got {sorted(bad)}"
    payload = {k: (str(v) if v is not None else None) for k, v in payload.items()}
    n = 0
    for sub in subscribers() if subs is None else subs:
        if event in sub.events:
            s.add(
                WebhookDelivery(
                    event=event,
                    url=sub.url,
                    secret_env=sub.secret_env,
                    payload=payload,
                    status="pending",
                )
            )
            n += 1
    return n


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def deliver_pending(
    sessions: async_sessionmaker, *, client: httpx.AsyncClient | None = None, limit: int = 50
) -> dict:
    """Send due deliveries; retry with backoff, give up after MAX_ATTEMPTS."""
    now = datetime.now(UTC)
    sent = failed = 0
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        async with sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(WebhookDelivery)
                        .where(
                            WebhookDelivery.status == "pending",
                            or_(
                                WebhookDelivery.next_attempt_at.is_(None),
                                WebhookDelivery.next_attempt_at <= now,
                            ),
                        )
                        .order_by(WebhookDelivery.created_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for d in rows:
                body = json.dumps(d.payload, sort_keys=True).encode()
                headers = {"Content-Type": "application/json", "X-SOP-Event": d.event}
                secret = os.environ.get(d.secret_env) if d.secret_env else None
                if secret:
                    headers["X-SOP-Signature"] = sign(secret, body)
                d.attempts += 1
                try:
                    r = await client.post(d.url, content=body, headers=headers)
                    ok = 200 <= r.status_code < 300
                except httpx.HTTPError:
                    ok = False
                if ok:
                    d.status, sent = "sent", sent + 1
                elif d.attempts >= MAX_ATTEMPTS:
                    d.status, failed = "failed", failed + 1
                else:
                    d.next_attempt_at = now + timedelta(minutes=2**d.attempts)
            await s.commit()
    finally:
        if own:
            await client.aclose()
    if sent or failed:
        log.info("webhooks_delivered", extra={"fields": {"sent": sent, "failed": failed}})
    return {"sent": sent, "failed": failed}
