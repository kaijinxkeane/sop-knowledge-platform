"""The model gateway: the only way agents reach a model (plan §5.1).

Responsibilities:
- resolve a tier name to a provider and model (config/models.yaml)
- enforce the data boundary: content from a ``local_only`` space, or content
  that is not yet classified, is never sent to a cloud provider
- log usage (tokens, latency, model) without content, for the cost dashboard
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace

from app.models.adapters.anthropic_adapter import AnthropicAdapter
from app.models.adapters.base import ChatAdapter, EmbedAdapter
from app.models.adapters.openai_compat import OpenAICompatAdapter
from app.models.config import GatewayConfig, TierConfig
from app.models.types import (
    UNCLASSIFIED,
    ChatResult,
    ContentScope,
    DataBoundaryError,
    GatewayError,
    Message,
    ProviderConfigError,
    ProviderUnavailableError,
    StreamEnd,
)
from app.models.usage import UsageEvent

log = logging.getLogger("sop.gateway")


class ModelGateway:
    def __init__(
        self,
        config: GatewayConfig,
        *,
        adapters: dict[str, ChatAdapter] | None = None,
        anthropic_api_key: str | None = None,
        on_usage: Callable[[UsageEvent], Awaitable[None]] | None = None,
    ):
        self.config = config
        self.on_usage = on_usage
        self._adapters: dict[str, object] = adapters or {
            "anthropic": AnthropicAdapter(anthropic_api_key),
            "openai_compat": OpenAICompatAdapter(),
        }

    def check_boundary(self, tier: TierConfig, scope: ContentScope) -> None:
        """Raise DataBoundaryError if this tier may not receive this content."""
        if tier.location == "local":
            return
        restricted: list[str] = []
        for space in sorted(scope.spaces):
            if space == UNCLASSIFIED:
                restricted.append("unclassified content")
                continue
            space_cfg = self.config.spaces.get(space)
            # Unknown spaces fail closed.
            if space_cfg is None or space_cfg.local_only:
                restricted.append(f"space {space!r}")
        if restricted:
            raise DataBoundaryError(
                f"tier {tier.name!r} is a cloud model; refusing to send {', '.join(restricted)}"
            )

    def is_configured(self, tier_name: str) -> bool:
        """False if the tier's provider can't be used at all (e.g. no API key)."""
        tier = self.config.tiers.get(tier_name)
        if tier is None:
            return False
        adapter = self._adapters.get(tier.provider)
        return adapter is not None and bool(getattr(adapter, "configured", True))

    def _adapter(self, tier: TierConfig) -> object:
        try:
            return self._adapters[tier.provider]
        except KeyError:
            raise ProviderConfigError(
                f"no adapter registered for provider {tier.provider!r}"
            ) from None

    def _fallback(self, tier: TierConfig, exc: Exception) -> TierConfig | None:
        """The local tier to use when `tier`'s provider is unavailable or not set up."""
        if not tier.fallback_tier or not isinstance(
            exc, (ProviderConfigError, ProviderUnavailableError)
        ):
            return None
        log.warning(
            "model_fallback",
            extra={
                "fields": {
                    "tier": tier.name,
                    "fallback": tier.fallback_tier,
                    "error": type(exc).__name__,
                }
            },
        )
        return self.config.tier(tier.fallback_tier)

    def _log(self, event: str, tier: TierConfig, scope: ContentScope, result, **extra) -> None:
        log.info(
            event,
            extra={
                "fields": {
                    "tier": tier.name,
                    "provider": result.provider,
                    "model": result.model,
                    "location": tier.location,
                    "spaces": sorted(scope.spaces),
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cache_read_tokens": result.usage.cache_read_tokens,
                    "latency_ms": result.latency_ms,
                    "stop_reason": result.stop_reason,
                    "request_id": result.request_id,
                    **extra,
                }
            },
        )

    async def _usage(self, tier: TierConfig, result=None, *, fallback: bool = False) -> None:
        """Daily totals for the cost dashboard: tier, model and token counts only."""
        if self.on_usage is None:
            return
        u = result.usage if result is not None else None
        await self.on_usage(
            UsageEvent(
                tier=tier.name,
                model=getattr(result, "model", None) or tier.model,
                provider=tier.provider,
                location=tier.location,
                input_tokens=u.input_tokens if u else 0,
                output_tokens=u.output_tokens if u else 0,
                cache_read_tokens=u.cache_read_tokens if u else 0,
                fallback=fallback,
            )
        )

    async def chat(
        self,
        tier_name: str,
        *,
        messages: list[Message],
        scope: ContentScope,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatResult:
        tier = self.config.tier(tier_name)
        self.check_boundary(tier, scope)
        fell_back = False
        try:
            result = await self._adapter(tier).chat(  # type: ignore[attr-defined]
                tier,
                system=system,
                messages=messages,
                max_tokens=max_tokens or tier.max_tokens,
                json_mode=json_mode,
            )
        except GatewayError as exc:
            fallback = self._fallback(tier, exc)
            if fallback is None:
                raise
            self.check_boundary(fallback, scope)
            tier, fell_back = fallback, True
            result = await self._adapter(tier).chat(  # type: ignore[attr-defined]
                tier,
                system=system,
                messages=messages,
                max_tokens=min(max_tokens or tier.max_tokens, tier.max_tokens),
                json_mode=json_mode,
            )
        self._log("model_call", tier, scope, result)
        await self._usage(tier, result, fallback=fell_back)
        return result

    async def stream(
        self,
        tier_name: str,
        *,
        messages: list[Message],
        scope: ContentScope,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str | StreamEnd]:
        """Yield text deltas, then a StreamEnd. Falls back to the tier's local
        fallback only if the provider fails before the first token."""
        tier = self.config.tier(tier_name)
        self.check_boundary(tier, scope)
        fallback_from = None
        started = False
        try:
            async for item in self._adapter(tier).stream(  # type: ignore[attr-defined]
                tier, system=system, messages=messages, max_tokens=max_tokens or tier.max_tokens
            ):
                if isinstance(item, StreamEnd):
                    self._log("model_call", tier, scope, item, stream=True)
                    await self._usage(tier, item)
                    yield item
                    return
                started = True
                yield item
        except GatewayError as exc:
            fallback = None if started else self._fallback(tier, exc)
            if fallback is None:
                raise
            self.check_boundary(fallback, scope)
            fallback_from, tier = tier.name, fallback
        async for item in self._adapter(tier).stream(  # type: ignore[attr-defined]
            tier,
            system=system,
            messages=messages,
            max_tokens=min(max_tokens or tier.max_tokens, tier.max_tokens),
        ):
            if isinstance(item, StreamEnd):
                item = replace(item, fallback_from=fallback_from)
                self._log("model_call", tier, scope, item, stream=True)
                await self._usage(tier, item, fallback=fallback_from is not None)
            yield item

    async def embed(
        self, texts: list[str], *, scope: ContentScope, tier_name: str = "embedding"
    ) -> list[list[float]]:
        tier = self.config.tier(tier_name)
        self.check_boundary(tier, scope)
        adapter = self._adapter(tier)
        if not hasattr(adapter, "embed"):
            raise ProviderConfigError(f"provider {tier.provider!r} does not support embeddings")
        vectors = await adapter.embed(tier, texts)  # type: ignore[attr-defined]
        await self._usage(tier)
        log.info(
            "embed_call",
            extra={"fields": {"tier": tier.name, "model": tier.model, "count": len(texts)}},
        )
        return vectors


def build_gateway() -> ModelGateway:
    from app.config import get_settings
    from app.models.config import load_gateway_config

    settings = get_settings()
    env = dict(os.environ)
    env["OLLAMA_BASE_URL"] = settings.ollama_base_url.rstrip("/")
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    from app.db.session import get_sessionmaker
    from app.models.usage import recorder

    return ModelGateway(
        load_gateway_config(settings.config_dir, env),
        anthropic_api_key=key,
        on_usage=recorder(get_sessionmaker()),
    )


__all__ = ["ModelGateway", "build_gateway", "EmbedAdapter"]
