"""Small, dependency-free statistics for comparing models on an eval."""

from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n (good for rates near 0 or 1)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    pct = 100 * k / n if n else 0
    return f"{pct:.1f}% ({k}/{n}, 95% CI {100 * lo:.1f}-{100 * hi:.1f}%)"


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value. b: only A right, c: only B right (paired items)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def paired(a: dict[str, bool], b: dict[str, bool]) -> dict:
    """Compare two models item by item (only items both answered)."""
    common = sorted(set(a) & set(b))
    only_a = [i for i in common if a[i] and not b[i]]
    only_b = [i for i in common if b[i] and not a[i]]
    return {
        "items": len(common),
        "both_right": sum(a[i] and b[i] for i in common),
        "both_wrong": sum(not a[i] and not b[i] for i in common),
        "only_a_right": only_a,
        "only_b_right": only_b,
        "mcnemar_p": round(mcnemar(len(only_a), len(only_b)), 4),
    }
