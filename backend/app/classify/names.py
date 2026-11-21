"""Filtering the names the local model found (plan §4.1, name detector).

There is no client list, so any person's or organisation's name that is not
staff, not one of the company's own names, and not confirmed safe keeps a
note restricted until a reviewer looks at it. Names the model reports that do
not actually occur in the text are ignored (no hallucinated hits).
"""

from __future__ import annotations

import re
from collections.abc import Iterable


def _norm(name: str) -> str:
    return " ".join(re.findall(r"[\w'&.-]+", name.lower()))


def staff_index(display_names: Iterable[str]) -> tuple[set[str], set[str]]:
    """(full names, single name parts) of staff, lower-cased."""
    full, parts = set(), set()
    for n in display_names:
        n = _norm(re.sub(r"\(.*?\)", "", n))
        if n:
            full.add(n)
            parts.update(p for p in n.split() if len(p) >= 3)
    return full, parts


def unresolved_names(
    found: Iterable[str],
    text: str,
    *,
    staff: tuple[set[str], set[str]],
    safe: set[str],
    clients: set[str],
) -> list[str]:
    lower = text.lower()
    full, parts = staff
    out: list[str] = []
    for raw in found:
        n = _norm(str(raw))
        if len(n) < 3 or n in out or n not in lower:
            continue
        if n in full or n in safe or all(p in parts for p in n.split()):
            continue
        out.append(n)
    # Names already on the client list always count, whatever the model said.
    out += [
        c
        for c in sorted(clients)
        if c not in out and re.search(rf"(?<!\w){re.escape(c)}(?!\w)", lower)
    ]
    return out
