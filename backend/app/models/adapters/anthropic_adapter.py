"""Claude via the official Anthropic SDK (Messages API).

The agent loop runs on our own server (not Managed Agents) so vault access and
tools stay on the company machine.
"""

from __future__ import annotations

import time
from typing import Any

import anthropic

from app.models.config import TierConfig
from app.models.types import (
    ChatResult,
    Message,
    ModelRefusalError,
    ProviderConfigError,
    ProviderUnavailableError,
    Usage,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicAdapter:
    def __init__(self, api_key: str | None, *, timeout: float = 120.0, max_retries: int = 2):
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: anthropic.AsyncAnthropic | None = None

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
        self, tier: TierConfig, *, system: str | None, messages: list[Message], max_tokens: int
    ) -> ChatResult:
        client = self._get_client()
        params = self.build_params(tier, system=system, messages=messages, max_tokens=max_tokens)
        started = time.monotonic()
        try:
            if "betas" in params:
                response = await client.beta.messages.create(**params)
            else:
                response = await client.messages.create(**params)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderConfigError(
                f"Anthropic rejected the credentials ({exc.status_code})"
            ) from exc
        except anthropic.NotFoundError as exc:
            raise ProviderConfigError(
                f"Anthropic model or endpoint not found: {tier.model}"
            ) from exc
        except anthropic.BadRequestError as exc:
            raise ProviderConfigError(
                f"Anthropic rejected the request ({exc.status_code})"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderUnavailableError("Anthropic rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailableError(
                    f"Anthropic server error ({exc.status_code})"
                ) from exc
            raise ProviderConfigError(f"Anthropic API error ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailableError("could not reach the Anthropic API") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.stop_reason == "refusal":
            raise ModelRefusalError(f"{tier.model} declined the request")

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        return ChatResult(
            text=text,
            tier=tier.name,
            provider="anthropic",
            model=response.model,
            stop_reason=response.stop_reason,
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
            request_id=getattr(response, "_request_id", None),
        )
