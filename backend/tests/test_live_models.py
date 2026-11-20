"""Opt-in checks against real providers: SOP_LIVE_TESTS=1 uv run pytest -m live"""

import os

import pytest

from app.models.gateway import build_gateway
from app.models.types import ContentScope, Message

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("SOP_LIVE_TESTS") != "1", reason="set SOP_LIVE_TESTS=1"),
]


async def test_answer_tier_on_claude():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    result = await build_gateway().chat(
        "answer",
        messages=[Message("user", "Reply with: ready")],
        scope=ContentScope.none(),
        max_tokens=256,
    )
    assert result.text


async def test_local_model_via_ollama():
    import dataclasses

    gw = build_gateway()
    model = os.environ.get("SOP_LIVE_LOCAL_MODEL", gw.config.tier("classifier").model)
    gw.config.tiers["classifier"] = dataclasses.replace(gw.config.tier("classifier"), model=model)
    result = await gw.chat(
        "classifier",
        messages=[Message("user", "Reply with: ready")],
        scope=ContentScope.of("core"),
        max_tokens=64,
    )
    assert result.text
