"""Sentence focus for the conflict check (plan §7).

A contradiction buried in a long passage ("a 2-minute pitch" inside a full day's
timetable vs "4 minutes for their pitch") is easy for a small model to miss when
the passages look like they're about different things. This finds the sentence
pairs that are most alike across the two passages with the local embedding
model, so the check can show them first. Nothing is dropped: the full passages
are still sent.
"""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable

Embed = Callable[[list[str]], Awaitable[list[list[float]]]]
_SPLIT = re.compile(r"(?<=[.!?;])\s+")
TOP = 3


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if len(s.strip()) > 3]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1.0)


async def closest_statements(text_a: str, text_b: str, embed: Embed, top: int = TOP):
    """The `top` most alike (sentence from A, sentence from B) pairs, best first.
    Empty when either passage is a single sentence (nothing to focus on)."""
    sa, sb = sentences(text_a), sentences(text_b)
    if len(sa) < 2 and len(sb) < 2:
        return []
    vectors = await embed(sa + sb)
    va, vb = vectors[: len(sa)], vectors[len(sa) :]
    scored = sorted(
        ((_cos(x, y), i, j) for i, x in enumerate(va) for j, y in enumerate(vb)), reverse=True
    )
    out, used_a, used_b = [], set(), set()
    for _, i, j in scored:  # each sentence at most once, so three different topics
        if i in used_a or j in used_b:
            continue
        out.append((sa[i], sb[j]))
        used_a.add(i)
        used_b.add(j)
        if len(out) == top:
            break
    return out
