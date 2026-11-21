"""Claude via the official Anthropic SDK (Messages API).

The agent loop runs on our own server (not Managed Agents) so vault access and
tools stay on the company machine.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any

import anthropic

from app.models.config import TierConfig
from app.models.types import (
    ChatResult,
    Message,
    ModelRefusalError,
    ProviderConfigError,
    ProviderUnavailableError,
    StreamEnd,
    Usage,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicAdapter:
    def __init__(self, api_key: str | None, *, timeout: float = 120.0, max_retries: int = 2):
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if not self._api_key:
            raise ProviderConfigError(
                "ANTHROPIC_API_KEY is not set; cloud tiers are unavailable "
                "(set it in .env, or point the tier at a local model)"
            )
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=self._api_key, timeout=self._timeout, max_retries=self._max_retries
            )
        return self._client

    @staticmethod
    def build_params(
        tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": tier.model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            params["system"] = system
        if tier.effort:
            params["output_config"] = {"effort": tier.effort}
        if tier.cache:
            # Automatic prompt caching: stable prefixes (system prompt, tools) are
            # billed at cache-read rates on repeat requests (plan §5.2).
            params["cache_control"] = {"type": "ephemeral"}
        if tier.fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = tier.fallbacks
        return params

    async def chat(
        self,
        tier: TierConfig,
        *,
        system: str | None,
        messages: list[Message],
        max_tokens: int,
        json_mode: bool = False,  # Claude follows the prompt's JSON instructions
    ) -> ChatResult:
        client = self._get_client()
        params = self.build_params(tier, system=system, messages=messages, max_tokens=max_tokens)
        started = time.monotonic()
        with _mapped_errors(tier):
            if "betas" in params:
                response = await client.beta.messages.create(**params)
            else:
                response = await client.messages.create(**params)
        latency_ms = int((time.monotonic() - started) * 1000)
        if response.stop_reason == "refusal":
            raise ModelRefusalError(f"{tier.model} declined the request")
        text = "".join(block.text for block in response.content if block.type == "text")
        return ChatResult(
            text=text,
            tier=tier.name,
            provider="anthropic",
            model=response.model,
            stop_reason=response.stop_reason,
            usage=_usage(response.usage),
            latency_ms=latency_ms,
            request_id=getattr(response, "_request_id", None),
        )

    async def stream(
        self, tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str | StreamEnd]:
        client = self._get_client()
        params = self.build_params(tier, system=system, messages=messages, max_tokens=max_tokens)
        started = time.monotonic()
        api = client.beta.messages if "betas" in params else client.messages
        with _mapped_errors(tier):
            async with api.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
        if final.stop_reason == "refusal":
            raise ModelRefusalError(f"{tier.model} declined the request")
        yield StreamEnd(
            tier=tier.name,
            provider="anthropic",
            model=final.model,
            stop_reason=final.stop_reason,
            usage=_usage(final.usage),
            latency_ms=int((time.monotonic() - started) * 1000),
            request_id=getattr(final, "_request_id", None),
        )


def _usage(usage) -> Usage:
    return Usage(
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )


@contextmanager
def _mapped_errors(tier: TierConfig):
    """Translate SDK errors into gateway errors (config problems vs. retryable outages)."""
    try:
        yield
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
        raise ProviderConfigError(
            f"Anthropic rejected the credentials ({exc.status_code})"
        ) from exc
    except anthropic.NotFoundError as exc:
        raise ProviderConfigError(f"Anthropic model or endpoint not found: {tier.model}") from exc
    except anthropic.BadRequestError as exc:
        raise ProviderConfigError(f"Anthropic rejected the request ({exc.status_code})") from exc
    except anthropic.RateLimitError as exc:
        raise ProviderUnavailableError("Anthropic rate limit reached") from exc
    except anthropic.APIStatusError as exc:
        if exc.status_code >= 500:
            raise ProviderUnavailableError(f"Anthropic server error ({exc.status_code})") from exc
        raise ProviderConfigError(f"Anthropic API error ({exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise ProviderUnavailableError("could not reach the Anthropic API") from exc
