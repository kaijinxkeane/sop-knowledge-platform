"""Structured JSON logging that never records content.

Policy (plan §11): logs, traces and error reports contain IDs, hashes, counts
and timings, never note text, questions or answers. That makes logs safe to
share for debugging. Content lives only in the audit log in the database.

Call sites must pass content-free fields via ``extra={"fields": {...}}``.
As a safety net, any field whose name suggests content is redacted.
"""

from __future__ import annotations

import json
import logging
import sys
import time

CONTENT_FIELD_NAMES = frozenset(
    {"text", "content", "question", "answer", "prompt", "body", "messages", "passage", "note"}
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                payload[key] = "[redacted]" if key.lower() in CONTENT_FIELD_NAMES else value
        if record.exc_info and record.exc_info[0] is not None:
            # Exception type only: messages can embed content.
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._sop_handler = True  # type: ignore[attr-defined]
    root = logging.getLogger()
    # Replace only our own handler (idempotent); leave others (e.g. test capture) alone.
    root.handlers[:] = [h for h in root.handlers if not getattr(h, "_sop_handler", False)]
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Third-party HTTP clients can log request bodies at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpcore", "httpx2", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
