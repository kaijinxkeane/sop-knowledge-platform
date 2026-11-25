"""Load tier and space configuration from config/models.yaml and config/spaces/*.yaml.

Agents ask for a *tier* ("router", "answer", ...), never a model name, so moving a
tier to a local model is a config change (plan §5.1).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.models.types import UNCLASSIFIED, Location

KNOWN_PROVIDERS = {"anthropic", "openai_compat"}
_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


@dataclass(frozen=True)
class TierConfig:
    name: str
    provider: str
    model: str
    location: Location
    base_url: str | None = None
    effort: str | None = None
    max_tokens: int = 4096
    fallbacks: str | None = None  # Anthropic server-side refusal fallback ("default")
    cache: bool = True
    think: bool | None = None  # False: switch off a local model's thinking (Qwen3 /no_think)
    fallback_tier: str | None = None  # used when this tier's provider is unavailable
    # USD per million tokens (input, output, cache read), for the cost dashboard.
    # Local tiers cost nothing per call and leave it unset.
    price: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class SpaceConfig:
    name: str
    title: str
    local_only: bool = False


@dataclass(frozen=True)
class GatewayConfig:
    tiers: dict[str, TierConfig]
    spaces: dict[str, SpaceConfig]

    def tier(self, name: str) -> TierConfig:
        try:
            return self.tiers[name]
        except KeyError:
            raise KeyError(f"unknown model tier {name!r}; defined: {sorted(self.tiers)}") from None


def _expand_env(value: object, env: dict[str, str]) -> object:
    if isinstance(value, str):

        def sub(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in env:
                raise ValueError(f"config references unset environment variable ${{{key}}}")
            return env[key]

        return _ENV_RE.sub(sub, value)
    return value


def _tier_from_dict(name: str, raw: dict, env: dict[str, str]) -> TierConfig:
    raw = {k: _expand_env(v, env) for k, v in raw.items()}
    provider = raw.get("provider")
    if provider not in KNOWN_PROVIDERS:
        raise ValueError(f"tier {name!r}: provider must be one of {sorted(KNOWN_PROVIDERS)}")
    if not raw.get("model"):
        raise ValueError(f"tier {name!r}: model is required")

    if provider == "anthropic":
        location: Location = "cloud"
        if raw.get("location", "cloud") != "cloud":
            raise ValueError(f"tier {name!r}: the anthropic provider is always location: cloud")
    else:
        # Fail closed: an OpenAI-compatible endpoint counts as cloud unless the
        # config explicitly says it runs on this machine.
        location = "local" if raw.get("location") == "local" else "cloud"
        if not raw.get("base_url"):
            raise ValueError(f"tier {name!r}: openai_compat requires base_url")

    price = None
    if raw.get("price") is not None:
        p = raw["price"]
        if not isinstance(p, dict) or not {"input", "output"} <= set(p):
            raise ValueError(f"tier {name!r}: price needs input and output (USD per 1M tokens)")
        price = (float(p["input"]), float(p["output"]), float(p.get("cache_read", 0)))
        if min(price) < 0:
            raise ValueError(f"tier {name!r}: prices can't be negative")

    return TierConfig(
        name=name,
        provider=provider,
        model=str(raw["model"]),
        location=location,
        base_url=raw.get("base_url"),
        effort=raw.get("effort"),
        max_tokens=int(raw.get("max_tokens", 4096)),
        fallbacks=raw.get("fallbacks"),
        cache=bool(raw.get("cache", True)),
        think=None if raw.get("think") is None else bool(raw.get("think")),
        fallback_tier=raw.get("fallback_tier"),
        price=price,
    )


def load_gateway_config(config_dir: Path, env: dict[str, str] | None = None) -> GatewayConfig:
    env = dict(os.environ if env is None else env)
    models_file = config_dir / "models.yaml"
    data = yaml.safe_load(models_file.read_text(encoding="utf-8")) or {}
    raw_tiers = data.get("tiers") or {}
    if not raw_tiers:
        raise ValueError(f"{models_file}: no tiers defined")
    tiers = {name: _tier_from_dict(name, raw or {}, env) for name, raw in raw_tiers.items()}
    for tier in tiers.values():
        fb = tiers.get(tier.fallback_tier) if tier.fallback_tier else None
        if tier.fallback_tier and fb is None:
            raise ValueError(f"tier {tier.name!r}: unknown fallback_tier {tier.fallback_tier!r}")
        if fb is not None and (fb.location != "local" or fb.fallback_tier):
            # A fallback must be local (it can take any content) and final.
            raise ValueError(
                f"tier {tier.name!r}: fallback_tier must be a local tier without its own fallback"
            )

    spaces: dict[str, SpaceConfig] = {}
    for path in sorted((config_dir / "spaces").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = raw.get("name") or path.stem
        if name == UNCLASSIFIED:
            raise ValueError(f"{path}: {UNCLASSIFIED!r} is reserved")
        spaces[name] = SpaceConfig(
            name=name, title=raw.get("title", name), local_only=bool(raw.get("local_only", False))
        )
    return GatewayConfig(tiers=tiers, spaces=spaces)
