"""Local models through an OpenAI-compatible HTTP API (Ollama, vLLM, LM Studio, llama.cpp).

Model residency (how long a model stays in memory) is controlled on the
Ollama server with OLLAMA_KEEP_ALIVE, not per request, so the 16 GB host can
unload the Classifier when idle (plan §3.4).
"""

from __future__ import annotations

import re
import time

import httpx

from app.models.config import TierConfig
from app.models.types import (
    ChatResult,
    Message,
    ProviderConfigError,
    ProviderUnavailableError,
    Usage,
)

# Reasoning models (e.g. Qwen3) may inline their chain of thought.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class OpenAICompatAdapter:
    def __init__(
        self, *, timeout: float = 300.0, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._timeout = timeout
        self._transport = transport

    def _client(self, tier: TierConfig) -> httpx.AsyncClient:
        assert tier.base_url
        return httpx.AsyncClient(
            base_url=tier.base_url.rstrip("/"), timeout=self._timeout, transport=self._transport
        )

    async def _post(self, tier: TierConfig, path: str, payload: dict) -> dict:
        try:
            async with self._client(tier) as client:
                response = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"could not reach local model server at {tier.base_url}"
            ) from exc
        if response.status_code == 404:
            raise ProviderConfigError(
                f"model {tier.model!r} not available at {tier.base_url} "
                f"(for Ollama: `ollama pull {tier.model}`)"
            )
        if response.status_code >= 500:
            raise ProviderUnavailableError(f"local model server error ({response.status_code})")
        if response.status_code >= 400:
            raise ProviderConfigError(
                f"local model server rejected the request ({response.status_code})"
            )
        return response.json()

    async def chat(
        self, tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> ChatResult:
        wire = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m.role, "content": m.content} for m in messages
        ]
        started = time.monotonic()
        data = await self._post(
            tier,
            "/chat/completions",
            {"model": tier.model, "messages": wire, "max_tokens": max_tokens, "stream": False},
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            choice = data["choices"][0]
            text = _THINK_RE.sub("", choice["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError("local model returned an unexpected response") from exc
        usage = data.get("usage") or {}
        return ChatResult(
            text=text,
            tier=tier.name,
            provider="openai_compat",
            model=data.get("model", tier.model),
            stop_reason=choice.get("finish_reason"),
            usage=Usage(
                input_tokens=usage.get("prompt_tokens", 0) or 0,
                output_tokens=usage.get("completion_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
        )

    async def embed(self, tier: TierConfig, texts: list[str]) -> list[list[float]]:
        data = await self._post(tier, "/embeddings", {"model": tier.model, "input": texts})
        try:
            rows = sorted(data["data"], key=lambda row: row["index"])
            return [row["embedding"] for row in rows]
        except (KeyError, TypeError) as exc:
            raise ProviderUnavailableError(
                "local embedding server returned an unexpected response"
            ) from exc
