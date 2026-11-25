"""Cost and usage report: daily totals recorded by the gateway, admin/auditor only."""

from pathlib import Path

from app.api import deps
from app.models.config import GatewayConfig, TierConfig, load_gateway_config
from app.models.usage import UsageEvent, recorder

CONFIG = Path(__file__).resolve().parents[3] / "config"
LOCAL = dict(location="local", base_url="http://x/v1")


class Gw:
    """A priced cloud tier (none is configured today; the report still prices one)."""

    config = GatewayConfig(
        tiers={
            "answer": TierConfig(
                "answer", "cloud_api", "hosted-model", "cloud", price=(0.10, 0.50, 0.01)
            ),
            "answer-local": TierConfig("answer-local", "openai_compat", "qwen3:8b", **LOCAL),
        },
        spaces={},
    )


class RealGw:
    config = load_gateway_config(CONFIG, {"OLLAMA_BASE_URL": "http://localhost:11434"})


async def test_usage_is_summed_per_day_and_priced(client, sessions, make_user, sign_in):
    record = recorder(sessions)
    for _ in range(3):
        await record(UsageEvent("answer", "hosted-model", "cloud_api", "cloud", 1_000_000, 100_000))
    await record(
        UsageEvent("answer-local", "qwen3:8b", "openai_compat", "local", 500, 50, fallback=True)
    )
    client._transport.app.dependency_overrides[deps.get_gateway] = lambda: Gw()

    admin = await make_user(roles=("employee", "platform-admin"))
    r = await client.get("/api/v1/reports/usage", headers=await sign_in(admin))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cloud_calls"] == 3 and body["local_calls"] == 1 and body["fallbacks"] == 1
    hosted = next(t for t in body["tiers"] if t["tier"] == "answer")
    assert hosted["input_tokens"] == 3_000_000 and hosted["calls"] == 3
    assert body["total_cost_usd"] == 0.45  # 3 x (1M x $0.10 + 0.1M x $0.50)
    assert body["priced"] and len(body["days"]) == 1
    # Totals only: nothing that could identify a person or a question.
    assert set(hosted) == {
        "tier",
        "model",
        "provider",
        "location",
        "calls",
        "fallbacks",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cost_usd",
    }

    staff = await make_user(roles=("employee", "core-lead"))
    assert (
        await client.get("/api/v1/reports/usage", headers=await sign_in(staff))
    ).status_code == 403
    bad = await client.get(
        "/api/v1/reports/usage", params={"month": "2026-13"}, headers=await sign_in(admin)
    )
    assert bad.status_code == 422


async def test_fully_local_costs_nothing(client, sessions, make_user, sign_in):
    record = recorder(sessions)
    await record(UsageEvent("answer", "qwen3:8b", "openai_compat", "local", 10_000, 2_000))
    client._transport.app.dependency_overrides[deps.get_gateway] = lambda: RealGw()
    admin = await make_user(roles=("employee", "platform-admin"))
    body = (await client.get("/api/v1/reports/usage", headers=await sign_in(admin))).json()
    assert body["total_cost_usd"] == 0 and body["cloud_calls"] == 0 and body["priced"]
