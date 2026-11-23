"""Old versions of decks, PDFs and other files as text, for reading and diffs.

Parsed from git on demand with the indexer's own parsers (same text, OCR
included), so nothing more is stored. A few recent results are kept in memory
only (keyed by path and commit, which never change); callers check access
before asking.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass

from app.vault.parse import Part, parse_file

_CACHE: OrderedDict[tuple[str, str], Rendition] = OrderedDict()
_MAX = 16


@dataclass(frozen=True)
class Rendition:
    text: str  # one "## Slide n: title" / "## Page n" section per part
    parts: list[Part]


def render(path: str, data: bytes) -> Rendition:
    parsed = parse_file(path, data)
    by_number = {c.number: c.text for c in parsed.chunks if c.number is not None}
    sections = []
    if parsed.parts:
        for p in parsed.parts:
            label = "Slide" if p.part == "slide" else "Page"
            head = f"## {label} {p.number}" + (
                f": {p.title}" if p.part == "slide" and p.title else ""
            )
            body = by_number.get(p.number, "")
            if p.part == "slide" and p.title and body.startswith(p.title):
                body = body[len(p.title) :].lstrip("\n")
            sections.append(f"{head}\n\n{body}".rstrip())
    else:  # documents and images: their chunks in order
        for c in parsed.chunks:
            sections.append(f"## {c.heading}\n\n{c.text}" if c.heading else c.text)
    return Rendition(text="\n\n".join(sections) + "\n", parts=list(parsed.parts))


async def rendition(path: str, commit: str, data: bytes) -> Rendition:
    key = (path, commit)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    out = await asyncio.to_thread(render, path, data)
    _CACHE[key] = out
    while len(_CACHE) > _MAX:
        _CACHE.popitem(last=False)
    return out


def forget_all() -> None:
    """Retract: drop every cached text (memory only, so nothing else to purge)."""
    _CACHE.clear()
