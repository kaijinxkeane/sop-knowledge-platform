from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.models.config import TierConfig
from app.models.types import ChatResult, Message, StreamEnd


class ChatAdapter(Protocol):
    async def chat(
        self,
        tier: TierConfig,
        *,
        system: str | None,
        messages: list[Message],
        max_tokens: int,
        json_mode: bool = False,
    ) -> ChatResult: ...

    def stream(
        self, tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str | StreamEnd]: ...


class EmbedAdapter(Protocol):
    async def embed(self, tier: TierConfig, texts: list[str]) -> list[list[float]]: ...
