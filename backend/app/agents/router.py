"""Concierge routing (plan §5, "Routing"): which departments answer a question.

1. Permissions: only spaces the user may read are candidates.
2. Search, no model: strong matches from one clear space -> that space; from
   two -> both (unless one clearly leads).
3. Unclear (3+ spaces with no leader, or nothing strong): the local `router`
   tier picks, seeing only the question and one-line space descriptions,
   never vault content. Routing never uses a cloud tier.
4. Model unavailable: every permitted space in the results (or all of them).

Every decision carries a reason (single_space | search | model | fallback)
and is logged with the chosen spaces, never the question.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.agents.untrusted import REMINDER, tag, with_rules
from app.models.gateway import ModelGateway
from app.models.types import ContentScope, Message
from app.retrieval.search import Hit
from app.spaces import SpaceProfile

log = logging.getLogger("sop.router")
STRONG_DISTANCE = 0.55  # qwen3-embedding:0.6b: relevant passages sit at ~0.30-0.55
LEAD_SHARE = 0.7  # one space holding this share of the strong-match score leads


@dataclass(frozen=True)
class Route:
    spaces: tuple[str, ...]
    reason: str  # single_space | search | model | fallback


def _strong(hit: Hit) -> bool:
    if hit.distance is not None and hit.distance <= STRONG_DISTANCE:
        return True
    return "keyword" in hit.matched  # every query word matched


ROUTER_SYSTEM = """You route staff questions to the right department.
Departments:
{spaces}
Reply with JSON only: {{"spaces": ["<department>", ...]}} listing the one or two
departments most likely to have the answer."""


async def route(
    question: str,
    hits: list[Hit],
    readable: list[str],
    profiles: dict[str, SpaceProfile],
    gateway: ModelGateway | None,
) -> Route:
    readable = [s for s in readable if s in profiles]
    if len(readable) <= 1:
        return _done(Route(tuple(readable), "single_space"))

    scores: dict[str, float] = {}
    for h in hits:
        if h.space in readable and _strong(h):
            scores[h.space] = scores.get(h.space, 0.0) + h.score
    ranked = sorted(scores, key=scores.get, reverse=True)
    total = sum(scores.values())
    if ranked and scores[ranked[0]] / total >= LEAD_SHARE:
        return _done(Route((ranked[0],), "search"))
    if len(ranked) == 2:
        return _done(Route(tuple(ranked), "search"))

    if gateway is not None:
        try:
            listing = "\n".join(f"- {s}: {profiles[s].description}" for s in readable)
            result = await gateway.chat(
                "router",
                system=with_rules(ROUTER_SYSTEM.format(spaces=listing)),
                messages=[Message("user", tag("question", question) + f"\n{REMINDER}")],
                scope=ContentScope.none(),
                json_mode=True,
            )
            match = re.search(r"\{.*\}", result.text, re.DOTALL)
            picked = json.loads(match.group(0)).get("spaces", []) if match else []
            chosen = tuple(dict.fromkeys(s for s in picked if s in readable))[:2]
            if chosen:
                return _done(Route(chosen, "model"))
        except Exception:  # noqa: BLE001 - routing must never fail the question
            pass
    in_results = tuple(dict.fromkeys(h.space for h in hits if h.space in readable))
    return _done(Route(in_results or tuple(readable), "fallback"))


def _done(r: Route) -> Route:
    log.info("route", extra={"fields": {"reason": r.reason, "spaces": list(r.spaces)}})
    return r
