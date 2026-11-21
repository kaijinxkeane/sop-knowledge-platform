"""What counts as a change to an approved SOP.

An approval covers one exact version, identified by its *governed hash*: the
file's bytes, except that the frontmatter keys the platform writes itself
(status, reviewer, approved_by, approved_on, review_due) are left out. So the
platform's own write-back, or someone typing `approved_by:` by hand, never
changes what was approved, and any other edit does.
"""

from __future__ import annotations

import hashlib
import json

import yaml

PLATFORM_KEYS = frozenset({"status", "reviewer", "approved_by", "approved_on", "review_due"})


def split_frontmatter(text: str) -> tuple[dict | None, str, str]:
    """(frontmatter dict or None, raw frontmatter block, body)."""
    if not text.startswith("---"):
        return None, "", text
    end = text.find("\n---", 3)
    if end < 0:
        return None, "", text
    raw = text[3:end]
    body = text[end + 4 :]
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None, raw, body
    return (data if isinstance(data, dict) else None), raw, body


def governed_hash(path: str, data: bytes) -> str:
    if not path.lower().endswith(".md"):
        return hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8", errors="replace")
    fm, _, body = split_frontmatter(text)
    if fm is None:
        return hashlib.sha256(data).hexdigest()
    kept = {str(k): v for k, v in fm.items() if str(k) not in PLATFORM_KEYS}
    canon = json.dumps(kept, sort_keys=True, default=str) + "\n---\n" + body.strip()
    return hashlib.sha256(canon.encode()).hexdigest()


def with_frontmatter(text: str, updates: dict) -> str | None:
    """The note with these frontmatter keys set (None if it has no readable
    frontmatter, so nothing is rewritten blindly)."""
    fm, _, body = split_frontmatter(text)
    if fm is None:
        return None
    fm = {**fm, **updates}
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---" + body
