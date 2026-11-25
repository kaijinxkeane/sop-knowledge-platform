"""Cost and usage bookkeeping: counts and tokens only, never content; never breaks a call."""

from pathlib import Path

import pytest

from app.models.config import GatewayConfig, SpaceConfig, TierConfig, load_gateway_config
from app.models.gateway import ModelGateway
from app.models.types import ChatResult, ContentScope, Message, Usage
from app.models.usage import UsageEvent, cost_usd, recorder

CONFIG = Path(__file__).resolve().parents[2] / "config"


class Adapter:
    async def chat(self, tier, *, system, messages, max_tokens, json_mode=False):
        return ChatResult(
            "secret answer",
            tier.name,
            tier.provider,
            tier.model,
            "end_turn",
            Usage(1000, 200, 50),
            5,
        )

    async def embed(self, tier, texts):
        return [[0.0] for _ in texts]


def gateway(events):
    cfg = GatewayConfig(
        tiers={
            "answer": TierConfig(
                "answer", "cloud_api", "hosted-model", "cloud", price=(0.1, 0.5, 0.01)
            ),
            "embedding": TierConfig(
                "embedding", "openai_compat", "e", "local", base_url="http://x/v1"
            ),
        },
        spaces={"hr": SpaceConfig("hr", "HR")},
    )

    async def sink(e):
        events.append(e)

    a = Adapter()
    return ModelGateway(cfg, adapters={"cloud_api": a, "openai_compat": a}, on_usage=sink)


async def test_each_call_is_counted_without_content():
    events: list[UsageEvent] = []
    gw = gateway(events)
    await gw.chat(
        "answer", messages=[Message("user", "a private question")], scope=ContentScope.of("hr")
    )
    await gw.embed(["some text"], scope=ContentScope.unclassified())
    assert [(e.tier, e.input_tokens, e.output_tokens, e.cache_read_tokens) for e in events] == [
        ("answer", 1000, 200, 50),
        ("embedding", 0, 0, 0),
    ]
    assert "private" not in repr(events) and "secret" not in repr(events)


async def test_a_failing_recorder_never_breaks_the_call():
    class Broken:
        def __call__(self):
            raise RuntimeError("db down")

    record = recorder(Broken())
    await record(UsageEvent("answer", "m", "cloud_api", "cloud", 1, 1))  # logs, no raise


def test_cost_and_config_prices():
    assert cost_usd((0.1, 0.5, 0.01), 1_000_000, 200_000, 100_000) == pytest.approx(0.201)
    assert cost_usd(None, 10**9, 10**9, 0) == 0.0
    cfg = load_gateway_config(CONFIG, {"OLLAMA_BASE_URL": "http://localhost:11434"})
    # Every cloud tier has a price, so the dashboard's total is complete.
    assert all(t.price for t in cfg.tiers.values() if t.location == "cloud")
    assert all(t.price is None for t in cfg.tiers.values() if t.location == "local")
