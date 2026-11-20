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

from app.models.adapters.anthropic_adapter import AnthropicAdapter
from app.models.adapters.base import ChatAdapter, EmbedAdapter
from app.models.adapters.openai_compat import OpenAICompatAdapter
from app.models.config import GatewayConfig, TierConfig
from app.models.types import (
    UNCLASSIFIED,
    ChatResult,
    ContentScope,
    DataBoundaryError,
    Message,
    ProviderConfigError,
)

log = logging.getLogger("sop.gateway")


class ModelGateway:
    def __init__(
        self,
        config: GatewayConfig,
        *,
        adapters: dict[str, ChatAdapter] | None = None,
        anthropic_api_key: str | None = None,
    ):
        self.config = config
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

    def _adapter(self, tier: TierConfig) -> object:
        try:
            return self._adapters[tier.provider]
        except KeyError:
            raise ProviderConfigError(
                f"no adapter registered for provider {tier.provider!r}"
            ) from None

    async def chat(
        self,
        tier_name: str,
        *,
        messages: list[Message],
        scope: ContentScope,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        tier = self.config.tier(tier_name)
        self.check_boundary(tier, scope)
        adapter = self._adapter(tier)
        result = await adapter.chat(  # type: ignore[attr-defined]
            tier, system=system, messages=messages, max_tokens=max_tokens or tier.max_tokens
        )
        log.info(
            "model_call",
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
                }
            },
        )
        return result

    async def embed(
        self, texts: list[str], *, scope: ContentScope, tier_name: str = "embedding"
    ) -> list[list[float]]:
        tier = self.config.tier(tier_name)
        self.check_boundary(tier, scope)
        adapter = self._adapter(tier)
        if not hasattr(adapter, "embed"):
            raise ProviderConfigError(f"provider {tier.provider!r} does not support embeddings")
        vectors = await adapter.embed(tier, texts)  # type: ignore[attr-defined]
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
    return ModelGateway(load_gateway_config(settings.config_dir, env), anthropic_api_key=key)


__all__ = ["ModelGateway", "build_gateway", "EmbedAdapter"]
