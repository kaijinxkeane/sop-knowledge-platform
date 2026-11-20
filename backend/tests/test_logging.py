import json
import logging

from app.logging import JsonFormatter


def _format(**fields):
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "evt", None, None)
    record.fields = fields
    return json.loads(JsonFormatter().format(record))


def test_content_fields_are_redacted():
    out = _format(question="secret pricing?", answer="...", tier="answer", input_tokens=5)
    assert out["question"] == "[redacted]"
    assert out["answer"] == "[redacted]"
    assert out["tier"] == "answer" and out["input_tokens"] == 5


def test_exception_message_is_not_logged():
    try:
        raise ValueError("contains the rate card text")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    out = json.loads(JsonFormatter().format(record))
    assert out["exc_type"] == "ValueError"
    assert "rate card" not in json.dumps(out)


def test_access_log_records_route_template_not_query(caplog):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with caplog.at_level(logging.INFO, logger="sop.access"):
        with TestClient(create_app()) as client:
            client.get("/api/v1/health/live?q=secret+pricing+question")
            client.get("/no/such/path?q=other+secret")
    records = [r for r in caplog.records if r.name == "sop.access"]
    fields = [r.fields for r in records]
    assert {"method": "GET", "route": "/api/v1/health/live", "status": 200} == {
        k: fields[0][k] for k in ("method", "route", "status")
    }
    assert fields[1]["route"] == "<unmatched>"
    assert "secret" not in repr(fields)
