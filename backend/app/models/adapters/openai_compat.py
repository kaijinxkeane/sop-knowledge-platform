"""Local models through an OpenAI-compatible HTTP API (Ollama, vLLM, LM Studio, llama.cpp).

Model residency (how long a model stays in memory) is controlled on the
Ollama server with OLLAMA_KEEP_ALIVE, not per request, so the 16 GB host can
unload the Classifier when idle (plan §3.4).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator

import httpx

from app.models.config import TierConfig
from app.models.types import (
    ChatResult,
    Message,
    ProviderConfigError,
    ProviderUnavailableError,
    StreamEnd,
    Usage,
)

# Reasoning models (e.g. Qwen3) may inline their chain of thought.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
# Ollama (0.12+) turns thinking off for hybrid models such as qwen3:8b with
# reasoning_effort "none"; its separate `reasoning` field is never read. Models
# that only think (e.g. the qwen3:4b 2507 Thinking build) ignore it: use an
# instruct build for tiers with `think: false`.
NO_THINK = {"reasoning_effort": "none"}


def _check(response: httpx.Response, tier: TierConfig) -> None:
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
        _check(response, tier)
        return response.json()

    @staticmethod
    def payload(
        tier: TierConfig,
        *,
        system: str | None,
        messages: list[Message],
        max_tokens: int,
        json_mode: bool = False,
        stream: bool = False,
    ) -> dict:
        wire = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m.role, "content": m.content} for m in messages
        ]
        body = {"model": tier.model, "messages": wire, "max_tokens": max_tokens, "stream": stream}
        if tier.think is False:
            body |= NO_THINK
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    async def chat(
        self,
        tier: TierConfig,
        *,
        system: str | None,
        messages: list[Message],
        max_tokens: int,
        json_mode: bool = False,
    ) -> ChatResult:
        started = time.monotonic()
        data = await self._post(
            tier,
            "/chat/completions",
            self.payload(
                tier, system=system, messages=messages, max_tokens=max_tokens, json_mode=json_mode
            ),
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

    async def stream(
        self, tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str | StreamEnd]:
        """Yield text deltas (thinking removed), then one StreamEnd."""
        started = time.monotonic()
        body = self.payload(
            tier, system=system, messages=messages, max_tokens=max_tokens, stream=True
        )
        usage: dict = {}
        stop = None
        model = tier.model
        stripper = _ThinkStripper()
        try:
            async with (
                self._client(tier) as client,
                client.stream("POST", "/chat/completions", json=body) as response,
            ):
                if response.status_code >= 400:
                    await response.aread()
                    _check(response, tier)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    model = event.get("model", model)
                    usage = event.get("usage") or usage
                    for choice in event.get("choices") or []:
                        stop = choice.get("finish_reason") or stop
                        delta = (choice.get("delta") or {}).get("content") or ""
                        if text := stripper.feed(delta):
                            yield text
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"could not reach local model server at {tier.base_url}"
            ) from exc
        if text := stripper.flush():
            yield text
        yield StreamEnd(
            tier=tier.name,
            provider="openai_compat",
            model=model,
            stop_reason=stop,
            usage=Usage(
                input_tokens=usage.get("prompt_tokens", 0) or 0,
                output_tokens=usage.get("completion_tokens", 0) or 0,
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
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


class _ThinkStripper:
    """Drop a leading <think>...</think> block from a token stream."""

    def __init__(self):
        self.buf, self.state = "", "start"  # start | thinking | text

    def feed(self, delta: str) -> str:
        if self.state == "text":
            return delta
        self.buf += delta
        if self.state == "start":
            stripped = self.buf.lstrip()
            if "<think>".startswith(stripped):  # could still become <think>
                return ""
            if not stripped.startswith("<think>"):
                self.state, out, self.buf = "text", self.buf, ""
                return out
            self.state = "thinking"
        end = self.buf.find("</think>")
        if end < 0:
            return ""
        out, self.buf, self.state = self.buf[end + len("</think>") :].lstrip(), "", "text"
        return out

    def flush(self) -> str:
        out = self.buf if self.state != "thinking" else ""
        self.buf = ""
        return out
