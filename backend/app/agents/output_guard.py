"""Checks on what the model wrote, in code (red-team, 2026-11-22).

Marking passages as data (app.agents.untrusted) is not enough on its own: in
live tests the local 8B still copied a phishing link, a fake "DAN MODE ON"
line and a false "SYSTEM UPDATE" figure out of a planted note. So answers are
checked after the model, where no prompt can argue with the rule:

- links: removed while streaming, unless their domain is on the allowlist
  (`answers.allowed_link_domains` in config/vault.yaml, empty by default);
  images are always removed (a rendered image can send data to its server)
- uncited lines: the contract says every statement carries a citation, so a
  line without one is dropped from the final answer (a lead-in line ending in
  ":" is kept when cited items follow). Normal answers: 1 of 280 lines in the
  dev eval had no citation, and it was such a lead-in.

False *content* in an approved note (e.g. "the workshop now lasts 9 hours")
can't be caught here: it is cited like any other text. That is what approval
and the quiet instruction flag (app.governance.injection) are for.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlsplit

LINK_REMOVED = "[link removed]"
_IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)")
_MD_LINK_TARGET = re.compile(r"\]\(\s*((?:https?://|www\.)[^)\s]*)\s*\)", re.I)
_URL = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]\"']+", re.I)
_CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


@lru_cache(maxsize=1)
def allowed_domains() -> frozenset[str]:
    from app.vault.labels import vault_config

    return frozenset(d.lower().lstrip(".") for d in vault_config().allowed_link_domains)


def _allowed(url: str, domains: frozenset[str]) -> bool:
    host = (urlsplit(url if "://" in url else f"https://{url}").hostname or "").lower()
    return any(host == d or host.endswith(f".{d}") for d in domains)


def clean_links(text: str, domains: frozenset[str] | None = None) -> str:
    domains = allowed_domains() if domains is None else domains
    text = _IMAGE.sub("", text)
    text = _MD_LINK_TARGET.sub(lambda m: m.group(0) if _allowed(m.group(1), domains) else "]", text)
    return _URL.sub(lambda m: m.group(0) if _allowed(m.group(0), domains) else LINK_REMOVED, text)


class LinkFilter:
    """Streaming version of clean_links: holds back the last partial word (a
    link can't be judged until it ends), so links never reach the screen."""

    MAX_HOLD = 400

    def __init__(self, domains: frozenset[str] | None = None):
        self.pending = ""
        self.domains = domains

    def feed(self, delta: str) -> str:
        self.pending += delta
        cut = max(self.pending.rfind(" "), self.pending.rfind("\n"))
        if cut < 0 and len(self.pending) < self.MAX_HOLD:
            return ""
        if cut < 0:
            cut = len(self.pending) - 1
        out, self.pending = self.pending[: cut + 1], self.pending[cut + 1 :]
        return clean_links(out, self.domains)

    def flush(self) -> str:
        out, self.pending = self.pending, ""
        return clean_links(out, self.domains)


def drop_uncited_lines(text: str) -> tuple[str, int]:
    """Lines without a citation leave the answer. Returns (text, lines dropped).
    An answer with no citations at all is left as it is (it fails the citation
    check elsewhere)."""
    lines = text.splitlines()
    if not any(_CITE.search(ln) for ln in lines):
        return text, 0
    kept, dropped = [], 0
    for i, ln in enumerate(lines):
        if not ln.strip() or _CITE.search(ln):
            kept.append(ln)
            continue
        nxt = next((x for x in lines[i + 1 :] if x.strip()), "")
        if ln.rstrip().endswith(":") and _CITE.search(nxt):
            kept.append(ln)
            continue
        dropped += 1
    return "\n".join(kept).strip(), dropped
