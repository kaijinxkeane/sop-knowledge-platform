"""Background worker (arq + Redis).

- every minute: re-index files changed in git since the last run (app saves
  are indexed immediately; this catches Obsidian edits on the device), then
  fill in embeddings that failed earlier (e.g. Ollama was down)
- every minute (at :30): run the local Classifier / name detector on new
  versions (plan §4.1); notes stay restricted until it has run
- nightly 02:05: commit stray, uncommitted changes as *unattributed*
- every 15 minutes: heartbeat

    uv run arq app.workers.main.WorkerSettings
"""

from __future__ import annotations

import logging

from arq import cron
from arq.connections import RedisSettings

from app import audit
from app.config import get_settings
from app.db.session import get_sessionmaker
from app.logging import configure_logging
from app.retrieval.embed import embed_documents
from app.vault.git import GitVault
from app.vault.indexer import Indexer, commit_stray_changes

log = logging.getLogger("sop.worker")


def _indexer() -> Indexer:
    return Indexer(GitVault(get_settings().vault_path), get_sessionmaker(), embed_documents)


async def heartbeat(ctx: dict) -> str:
    log.info("worker_heartbeat", extra={"fields": {"job_try": ctx.get("job_try")}})
    return "ok"


async def index_sync(ctx: dict) -> dict:
    indexer = _indexer()
    if not indexer.git.is_repo():
        log.warning("vault_not_a_git_repo")
        return {}
    return (await indexer.sync()).summary()


async def classify_pending(ctx: dict) -> dict:
    from app.classify.model import gateway_classifier
    from app.classify.service import ClassifierService
    from app.retrieval.embed import _gateway
    from app.spaces import space_profiles

    service = ClassifierService(
        get_sessionmaker(), gateway_classifier(_gateway(), space_profiles())
    )
    return (await service.run_pending()).summary()


async def nightly_check(ctx: dict) -> int:
    indexer = _indexer()
    if not indexer.git.is_repo():
        return 0
    paths = commit_stray_changes(indexer.git)
    if paths:
        async with get_sessionmaker()() as s:
            await audit.record(s, "unattributed_changes", details={"files": len(paths)})
            await s.commit()
        await indexer.sync()
    return len(paths)


async def startup(ctx: dict) -> None:
    configure_logging(get_settings().log_level)
    log.info("worker_started")


class WorkerSettings:
    functions = [heartbeat, index_sync, classify_pending, nightly_check]
    cron_jobs = [
        cron(heartbeat, minute={0, 15, 30, 45}),
        cron(index_sync, second=0, run_at_startup=True, unique=True, timeout=600),
        cron(classify_pending, second=30, unique=True, timeout=900),
        cron(nightly_check, hour=2, minute=5, unique=True, timeout=600),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
