"""Liveness and readiness checks.

/health/live  -> the process is up (no dependencies checked)
/health       -> each dependency's status; HTTP 503 if any required one is down
The response never includes secrets, paths outside the vault, or content.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine

router = APIRouter(prefix="/health", tags=["ops"])


async def _check_db() -> dict:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            has_vector = (
                await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            ).scalar() is not None
        return {"status": "ok", "pgvector": has_vector}
    except Exception as exc:  # noqa: BLE001 - report, don't crash the health check
        return {"status": "down", "error": type(exc).__name__}


async def _check_redis() -> dict:
    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    try:
        await client.ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": type(exc).__name__}
    finally:
        await client.aclose()


def _check_vault() -> dict:
    vault = get_settings().vault_path
    if not vault.is_dir():
        return {"status": "missing"}
    return {"status": "ok", "git": (vault / ".git").exists()}


@router.get("/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("")
async def health(response: Response) -> dict:
    db, redis = await asyncio.gather(_check_db(), _check_redis())
    checks = {"database": db, "redis": redis, "vault": _check_vault()}
    ok = db["status"] == "ok" and redis["status"] == "ok"
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", "checks": checks}
