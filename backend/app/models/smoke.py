"""Smoke-test each model tier with a tiny, content-free request.

    uv run python -m app.models.smoke                 # all tiers
    uv run python -m app.models.smoke router classifier
    uv run python -m app.models.smoke --local-model llama3.2   # override local chat model

Every tier is local (Ollama), so a failure usually means a model isn't pulled.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import sys

from app.models.gateway import build_gateway
from app.models.types import ContentScope, GatewayError, Message, ProviderConfigError

PROMPT = [Message(role="user", content="Reply with the single word: ready")]


async def run(tiers: list[str], local_model: str | None) -> int:
    gateway = build_gateway()
    names = tiers or list(gateway.config.tiers)
    failures = 0
    for name in names:
        tier = gateway.config.tier(name)
        if local_model and tier.location == "local" and name != "embedding":
            gateway.config.tiers[name] = dataclasses.replace(tier, model=local_model)
            tier = gateway.config.tiers[name]
        label = f"{name:<11} {tier.provider}:{tier.model} ({tier.location})"
        try:
            if name == "embedding":
                vectors = await gateway.embed(["ready"], scope=ContentScope.none())
                print(f"PASS {label} -> {len(vectors[0])}-dim vector")
            else:
                result = await gateway.chat(
                    name, messages=PROMPT, scope=ContentScope.none(), max_tokens=256
                )
                u = result.usage
                print(
                    f"PASS {label} -> {result.text[:40]!r} "
                    f"({result.latency_ms} ms, {u.input_tokens}+{u.output_tokens} tok)"
                )
        except ProviderConfigError as exc:
            failures += 1
            print(f"FAIL {label} -> {exc}")
        except GatewayError as exc:
            failures += 1
            print(f"FAIL {label} -> {type(exc).__name__}: {exc}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tiers", nargs="*")
    parser.add_argument("--local-model", help="override the model for local chat tiers")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.tiers, args.local_model)))


if __name__ == "__main__":
    main()
