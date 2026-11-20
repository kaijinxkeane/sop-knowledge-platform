from fastapi.testclient import TestClient


def test_live_needs_no_dependencies():
    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health/live").json() == {"status": "ok"}


def test_health_reports_degraded_when_dependencies_down(monkeypatch, tmp_path):
    from app.db import session

    session.get_engine.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/none")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "absent"))
    from app.main import create_app

    with TestClient(create_app()) as client:
        r = client.get("/api/v1/health")
    session.get_engine.cache_clear()
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "down"
    assert body["checks"]["redis"]["status"] == "down"
    assert body["checks"]["vault"]["status"] == "missing"
    assert "y@" not in r.text  # never echo credentials


def test_openapi_is_served():
    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/openapi.json").status_code == 200
