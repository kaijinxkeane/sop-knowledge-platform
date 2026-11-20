"""Background worker (arq + Redis).

Phase 0 ships a heartbeat only. Later phases add: git change detection and
re-indexing, attachment parsing/OCR/slide rendering, classification, lint,
retention and review-due jobs.

    uv run arq app.workers.main.WorkerSettings
"""

from __future__ import annotations

import logging

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.logging import configure_logging

log = logging.getLogger("sop.worker")


async def heartbeat(ctx: dict) -> str:
    log.info("worker_heartbeat", extra={"fields": {"job_try": ctx.get("job_try")}})
    return "ok"


async def startup(ctx: dict) -> None:
    configure_logging(get_settings().log_level)
    log.info("worker_started")


class WorkerSettings:
    functions = [heartbeat]
    cron_jobs = [cron(heartbeat, minute={0, 15, 30, 45})]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
