"""Cost and usage (plan §8.1, Admin → cost and usage dashboard).

  GET /reports/usage?month=YYYY-MM    daily and per-tier totals with an estimated cost

For the platform admin and auditors (manage_users or view_audit). Totals only:
tiers, models and token counts. No questions, no answers, no people.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db, get_gateway
from app.db.models import ModelUsage
from app.models.usage import cost_usd

router = APIRouter(tags=["admin"])


class UsageRow(BaseModel):
    tier: str
    model: str
    provider: str
    location: str  # local | cloud
    calls: int
    fallbacks: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float


class DayOut(BaseModel):
    day: date
    calls: int
    cloud_calls: int
    cost_usd: float


class UsageOut(BaseModel):
    month: str
    days: list[DayOut]
    tiers: list[UsageRow]
    total_cost_usd: float
    cloud_calls: int
    local_calls: int
    fallbacks: int
    priced: bool  # False if a cloud tier has no price in config/models.yaml


def _month(value: str | None) -> tuple[date, date, str]:
    today = datetime.now(UTC).date()
    if value is None:
        start = today.replace(day=1)
    else:
        try:
            start = datetime.strptime(value, "%Y-%m").date()
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "month must be YYYY-MM"
            ) from None
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, end, start.strftime("%Y-%m")


@router.get("/reports/usage", response_model=UsageOut)
async def usage(
    me: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    gateway=Depends(get_gateway),
    month: str | None = Query(default=None, max_length=7),
) -> UsageOut:
    if not (me.principal.can("manage_users") or me.principal.can("view_audit")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
    start, end, label = _month(month)
    rows = (
        (
            await session.execute(
                select(ModelUsage).where(ModelUsage.day >= start, ModelUsage.day < end)
            )
        )
        .scalars()
        .all()
    )
    tiers = gateway.config.tiers
    priced = True

    def price(tier: str, location: str):
        nonlocal priced
        cfg = tiers.get(tier)
        if location == "cloud" and (cfg is None or cfg.price is None):
            priced = False
        return cfg.price if cfg is not None else None

    by_tier: dict[tuple[str, str], UsageRow] = {}
    by_day: dict[date, DayOut] = {}
    for r in rows:
        p = price(r.tier, r.location)
        c = cost_usd(p, r.input_tokens, r.output_tokens, r.cache_read_tokens)
        key = (r.tier, r.model)
        t = by_tier.get(key) or UsageRow(
            tier=r.tier,
            model=r.model,
            provider=r.provider,
            location=r.location,
            calls=0,
            fallbacks=0,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cost_usd=0.0,
        )
        t.calls += r.calls
        t.fallbacks += r.fallbacks
        t.input_tokens += r.input_tokens
        t.output_tokens += r.output_tokens
        t.cache_read_tokens += r.cache_read_tokens
        t.cost_usd += c
        by_tier[key] = t
        d = by_day.get(r.day) or DayOut(day=r.day, calls=0, cloud_calls=0, cost_usd=0.0)
        d.calls += r.calls
        d.cloud_calls += r.calls if r.location == "cloud" else 0
        d.cost_usd += c
        by_day[r.day] = d
    tier_rows = sorted(by_tier.values(), key=lambda t: (-t.cost_usd, -t.calls))
    for t in tier_rows:
        t.cost_usd = round(t.cost_usd, 4)
    for d in by_day.values():
        d.cost_usd = round(d.cost_usd, 4)
    return UsageOut(
        month=label,
        days=sorted(by_day.values(), key=lambda d: d.day),
        tiers=tier_rows,
        total_cost_usd=round(sum(t.cost_usd for t in tier_rows), 4),
        cloud_calls=sum(t.calls for t in tier_rows if t.location == "cloud"),
        local_calls=sum(t.calls for t in tier_rows if t.location == "local"),
        fallbacks=sum(t.fallbacks for t in tier_rows),
        priced=priced,
    )
