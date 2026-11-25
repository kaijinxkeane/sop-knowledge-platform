"""Record model usage for the cost dashboard: daily totals, never content.

The gateway calls `record` after every model call. A failure to record is
logged and ignored, so bookkeeping can never break an answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from app.db.models import ModelUsage

log = logging.getLogger("sop.usage")


@dataclass(frozen=True)
class UsageEvent:
    tier: str
    model: str
    provider: str
    location: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    fallback: bool = False


def cost_usd(price: tuple[float, float, float] | None, inp: int, out: int, cache: int) -> float:
    """Estimated cost in USD from per-million-token prices (None: free, e.g. local)."""
    if price is None:
        return 0.0
    return (inp * price[0] + out * price[1] + cache * price[2]) / 1_000_000


def recorder(sessionmaker):
    """An async callback for ModelGateway(on_usage=...) that upserts daily totals."""

    async def record(e: UsageEvent) -> None:
        try:
            values = {
                "day": datetime.now(UTC).date(),
                "tier": e.tier,
                "model": e.model,
                "provider": e.provider,
                "location": e.location,
                "calls": 1,
                "fallbacks": int(e.fallback),
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "cache_read_tokens": e.cache_read_tokens,
            }
            stmt = insert(ModelUsage).values(**values)
            t = ModelUsage.__table__.c
            stmt = stmt.on_conflict_do_update(
                index_elements=["day", "tier", "model"],
                set_={
                    "calls": t.calls + 1,
                    "fallbacks": t.fallbacks + int(e.fallback),
                    "input_tokens": t.input_tokens + e.input_tokens,
                    "output_tokens": t.output_tokens + e.output_tokens,
                    "cache_read_tokens": t.cache_read_tokens + e.cache_read_tokens,
                },
            )
            async with sessionmaker() as s:
                await s.execute(stmt)
                await s.commit()
        except Exception as exc:  # never let bookkeeping break a model call
            log.warning("usage_not_recorded", extra={"fields": {"error": type(exc).__name__}})

    return record
