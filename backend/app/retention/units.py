"""Write converted units next to durations, times of day and frequencies.

The conflict check (plan §7) flags the same rule written in other units as a
contradiction ("two weeks" vs "10 working days", "6 months" vs "180 days",
"17:00" vs "5 pm"). This adds a bracketed conversion after each one so the model
compares like with like. No model is involved and nothing is removed: the
original wording stays, the note only adds.
"""

from __future__ import annotations

import re

_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "half a": 0.5,
}  # fmt: skip
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r")"
_DURATION = re.compile(
    rf"\b{_NUM}[\s-]+(working[\s-]+days?|business[\s-]+days?|days?|weeks?|months?|years?|quarters?)\b",
    re.I,
)
_TIME_24 = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?!\s*(?:am|pm|a\.m\.|p\.m\.))", re.I)
_TIME_12 = re.compile(r"\b(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm|a\.m\.|p\.m\.)", re.I)
_FREQ = {
    r"every quarter|quarterly|four times a year|4 times a year": "every 3 months",
    r"twice a year|two times a year|2 times a year|every half[- ]year"
    r"|biannually|semi-annually": "every 6 months",
    r"once a year|annually|every year|yearly": "every 12 months",
    r"twice a month|two times a month|fortnightly|every fortnight": "every 2 weeks",
}  # fmt: skip
_FREQ_RE = re.compile(r"\b(" + "|".join(_FREQ) + r")\b", re.I)


def _number(word: str) -> float:
    w = word.lower()
    return _WORDS[w] if w in _WORDS else float(w)


def _fmt(x: float) -> str:
    return str(int(x)) if abs(x - round(x)) < 0.05 else f"{x:.1f}"


_RATE = re.compile(r"\b(?:once|twice|times|per|each|every)\s+$", re.I)


def _duration(m: re.Match) -> str:
    if m.group(1).lower() in ("a", "an") and _RATE.search(m.string[: m.start()]):
        return m.group(0)  # "twice a year" is a frequency, not a duration
    n, unit = _number(m.group(1)), re.sub(r"[\s-]+", " ", m.group(2).lower()).rstrip("s")
    if unit in ("working day", "business day"):
        out = f"= {_fmt(n / 5)} weeks, about {_fmt(n * 7 / 5)} calendar days"
    elif unit == "day":
        out = (
            f"= about {_fmt(n / 30)} months"
            if n >= 28
            else (f"= {_fmt(n / 7)} weeks" if n >= 7 else "")
        )
    elif unit == "week":
        out = f"= {_fmt(n * 7)} days, {_fmt(n * 5)} working days"
    elif unit == "month":
        out = f"= about {_fmt(n * 30)} days, about {_fmt(n * 52 / 12)} weeks"
    elif unit == "quarter":
        out = f"= {_fmt(n * 3)} months"
    else:  # year
        out = f"= {_fmt(n * 12)} months, about {_fmt(n * 365)} days"
    return f"{m.group(0)} [{out}]" if out else m.group(0)


def _time12(m: re.Match) -> str:
    h, mins, half = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()[0]
    h = (h % 12) + (12 if half == "p" else 0)
    return f"{m.group(0)} [= {h:02d}:{mins:02d}]"


def _time24(m: re.Match) -> str:
    h, mins = int(m.group(1)), int(m.group(2))
    if m.group(0).count(".") and h < 6:  # "2.5" or "1.30" read as a number, not a time
        return m.group(0)
    half = "am" if h < 12 else "pm"
    return f"{m.group(0)} [= {(h % 12) or 12}:{mins:02d} {half}]"


def _freq(m: re.Match) -> str:
    said = m.group(0).lower()
    for pattern, canon in _FREQ.items():
        if re.fullmatch(pattern, said):
            return m.group(0) if said == canon else f"{m.group(0)} [= {canon}]"
    return m.group(0)


_NOTE = re.compile(r"(\[= [^\]]*\])")


def _outside_notes(pattern: re.Pattern, fn, text: str) -> str:
    """Apply `pattern.sub(fn)` only to text outside notes already added."""
    parts = _NOTE.split(text)
    return "".join(p if i % 2 else pattern.sub(fn, p) for i, p in enumerate(parts))


def annotate(text: str) -> str:
    """Return `text` with a bracketed conversion after each duration, time and
    frequency it recognises."""
    steps = ((_FREQ_RE, _freq), (_DURATION, _duration), (_TIME_12, _time12), (_TIME_24, _time24))
    for pattern, fn in steps:
        text = _outside_notes(pattern, fn, text)
    return text
