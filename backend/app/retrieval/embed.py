"""Local embeddings through the model gateway (the `embedding` tier is local)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from app.models.gateway import ModelGateway, build_gateway
from app.models.types import ContentScope

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]

# qwen3-embedding expects an instruction on queries only; documents are embedded as-is.
QUERY_INSTRUCTION = (
    "Instruct: Given a staff member's question, retrieve SOP passages that answer it\nQuery: "
)
BATCH = 16


@lru_cache(maxsize=1)
def _gateway() -> ModelGateway:
    return build_gateway()


async def embed_documents(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        # Unclassified scope on purpose: indexing reads everything, and the
        # gateway only allows that on local tiers.
        out += await _gateway().embed(texts[i : i + BATCH], scope=ContentScope.unclassified())
    return out


async def embed_query(query: str) -> list[float]:
    return (await embed_documents([QUERY_INSTRUCTION + query]))[0]
