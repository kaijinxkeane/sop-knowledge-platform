from __future__ import annotations

from typing import Protocol

from app.models.config import TierConfig
from app.models.types import ChatResult, Message


class ChatAdapter(Protocol):
    async def chat(
        self, tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> ChatResult: ...


class EmbedAdapter(Protocol):
    async def embed(self, tier: TierConfig, texts: list[str]) -> list[list[float]]: ...
