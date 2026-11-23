"""Quiet flag for instruction-like text in notes (prompt-injection hygiene).

The indexer scans each note and attachment with these fixed patterns (no
model, no cost) and stores only the *ids* of the patterns that matched on the
document (`documents.injection_flags`). Nothing is sent to anyone: the flag
appears in the governance report the space's leads already use, and on the
review of that note, so the person approving it can look. Flagged notes are
not blocked: prompts already treat all notes as data (`app.agents.untrusted`),
so the flag is for tidiness and spotting misuse, and a false positive costs
nothing but a glance.

Pattern ids, never matched text, go into the database, the API and logs.
"""

from __future__ import annotations

import re

PATTERNS: dict[str, re.Pattern] = {
    "override": re.compile(
        r"\b(ignore|disregard|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|"
        r"all|any|your|the)\b[^.\n]{0,20}\b(instructions?|rules|prompts?|guidelines|directions)",
        re.I,
    ),
    "addresses_ai": re.compile(
        r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|assistant|bot|chatbot|"
        r"model|agent|llm)\b|\b(dear|hey|attention)\s+(ai|assistant|chatbot|bot|llm)\b|"
        r"\b(as an ai|you are (now )?(an? )?(ai|assistant|chatbot|language model))\b",
        re.I,
    ),
    "access_request": re.compile(
        r"\b(request|grant|give|escalate|elevate|widen|unlock)\b[^.\n]{0,30}\b(access|permissions?|"
        r"privileges?|clearance)\b[^.\n]{0,40}\b(all|every|restricted|admin|hr|full|other)\b",
        re.I,
    ),
    "reveal": re.compile(
        r"\b(reveal|print|show|repeat|output|leak)\b[^.\n]{0,30}\b(system prompt|your "
        r"(instructions|prompt|rules)|hidden|restricted (documents?|files?|notes?))",
        re.I,
    ),
    "hide_from_user": re.compile(
        r"\b(do not|don't|never)\s+(tell|mention|show|inform)\s+(this\s+to\s+)?the\s+(user|staff|"
        r"reader|employee)",
        re.I,
    ),
    "fake_authority": re.compile(
        r"\b(system|admin(istrator)?|security)\s+(update|message|note|notice|override)\s*[:(\[]|"
        r"\boverrides?\b[^.\n]{0,25}\b(text|content|instructions|rules|above)\b|"
        r"\b(dan|jailbreak|god)\s+mode\b",
        re.I,
    ),
    "markup": re.compile(
        r"<\s*/?\s*(system|instructions?|sources?|im_start|im_end|assistant)\b|\[/?INST\]|"
        r"<\|[a-z_]+\|>",
        re.I,
    ),
}


def scan(text: str) -> list[str]:
    """Ids of the patterns found in `text` (sorted, no duplicates)."""
    return sorted(k for k, rx in PATTERNS.items() if rx.search(text or ""))
