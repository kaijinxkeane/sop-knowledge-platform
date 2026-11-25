"""Train the sorter from what people filed, and use it (app/classify/sorter.py).

Training documents: labels a person decided (the folder rule of where it was
filed, its own frontmatter, or an approved AI label), in a department (not a
project, not a handover), outside the built-in Help. Each one is its mean
chunk embedding; its folder counts only if that folder belongs to its
department (app/vault/folders.py). Only fingerprints are stored.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.classify.sorter import Labelled, SorterModel, train
from app.db.models import TrainedSorter
from app.vault.folders import department_of
from app.vault.labels import VaultConfig, vault_config

log = logging.getLogger("sop.sorter")
HUMAN_SOURCES = ("frontmatter", "folder_rule", "approved_ai")


async def doc_vector(s: AsyncSession, doc_id) -> list[float] | None:
    v = await s.scalar(
        text(
            "SELECT avg(embedding)::text FROM chunks "
            "WHERE document_id = :id AND embedding IS NOT NULL"
        ),
        {"id": doc_id},
    )
    return [float(x) for x in v.strip("[]").split(",")] if v else None


async def training_set(s: AsyncSession, config: VaultConfig) -> list[Labelled]:
    rows = (
        await s.execute(
            text("""
            SELECT d.vault_path, a.space, a.sensitivity, avg(c.embedding)::text
            FROM documents d
            JOIN document_access a ON a.document_id = d.id AND a.role = 'owner'
            JOIN chunks c ON c.document_id = d.id AND c.embedding IS NOT NULL
            WHERE d.label_source = ANY(:sources) AND a.space NOT LIKE 'p-%'
              AND d.vault_path NOT LIKE 'Help/%'
            GROUP BY d.id, d.vault_path, a.space, a.sensitivity"""),
            {"sources": list(HUMAN_SOURCES)},
        )
    ).all()
    out = []
    for path, space, sensitivity, vec in rows:
        folder = str(PurePosixPath(path).parent)
        out.append(
            Labelled(
                vector=[float(x) for x in vec.strip("[]").split(",")],
                space=space,
                sensitivity=sensitivity,
                folder=folder if department_of(folder, config) == space else None,
            )
        )
    return out


async def train_sorter(sessions: async_sessionmaker, config: VaultConfig | None = None) -> dict:
    config = config or vault_config()
    async with sessions() as s:
        items = await training_set(s, config)
    model = train(items)
    async with sessions() as s, s.begin():
        await s.execute(TrainedSorter.__table__.delete())
        s.add(TrainedSorter(documents=model.n, data=model.to_json()))
    summary = {
        "documents": model.n,
        "departments": len(model.spaces),
        "levels": len(model.levels),
        "folders": len(model.folders),
    }
    log.info("sorter_trained", extra={"fields": summary})
    return summary


_cache: dict = {}


async def latest_sorter(s: AsyncSession) -> SorterModel | None:
    """The latest trained sorter (reloaded only when it was retrained)."""
    row = (await s.execute(select(TrainedSorter.id, TrainedSorter.trained_at).limit(1))).first()
    if row is None:
        return None
    key = (row.id, row.trained_at)
    if _cache.get("key") != key:
        data = await s.scalar(select(TrainedSorter.data).where(TrainedSorter.id == row.id))
        _cache.update(key=key, model=SorterModel.from_json(data))
    return _cache["model"]
