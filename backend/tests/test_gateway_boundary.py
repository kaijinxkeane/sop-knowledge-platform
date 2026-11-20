"""The data boundary: local-only and unclassified content never reaches a cloud tier."""

import pytest

from app.models.config import GatewayConfig, SpaceConfig, TierConfig
from app.models.gateway import ModelGateway
from app.models.types import ChatResult, ContentScope, DataBoundaryError, Message, Usage


class RecordingAdapter:
    def __init__(self):
        self.calls = []

    async def chat(self, tier, *, system, messages, max_tokens):
        self.calls.append((tier.name, system, messages, max_tokens))
        return ChatResult("ok", tier.name, tier.provider, tier.model, "end_turn", Usage(1, 1), 5)

    async def embed(self, tier, texts):
        self.calls.append((tier.name, texts))
        return [[0.0, 1.0] for _ in texts]


@pytest.fixture
def gateway():
    cfg = GatewayConfig(
        tiers={
            "cloud": TierConfig("cloud", "anthropic", "claude-haiku-5-5", "cloud", max_tokens=100),
            "local": TierConfig(
                "local", "openai_compat", "qwen3:4b", "local", base_url="http://x/v1"
            ),
            "embedding": TierConfig(
                "embedding",
                "openai_compat",
                "qwen3-embedding:0.6b",
                "local",
                base_url="http://x/v1",
            ),
        },
        spaces={
            "core": SpaceConfig("core", "Core", local_only=True),
            "hr": SpaceConfig("hr", "HR", local_only=False),
        },
    )
    adapter = RecordingAdapter()
    gw = ModelGateway(cfg, adapters={"anthropic": adapter, "openai_compat": adapter})
    gw.recorder = adapter
    return gw


MSG = [Message("user", "hi")]


async def test_cloud_allowed_for_non_local_only_space(gateway):
    result = await gateway.chat("cloud", messages=MSG, scope=ContentScope.of("hr"))
    assert result.text == "ok"
    assert gateway.recorder.calls[0][3] == 100  # tier default max_tokens


async def test_cloud_allowed_without_vault_content(gateway):
    await gateway.chat("cloud", messages=MSG, scope=ContentScope.none())


@pytest.mark.parametrize(
    "scope,needle",
    [
        (ContentScope.of("core"), "space 'core'"),
        (ContentScope.of("hr", "core"), "space 'core'"),
        (ContentScope.unclassified(), "unclassified content"),
        (ContentScope.of("finance"), "space 'finance'"),  # unknown space fails closed
    ],
)
async def test_cloud_refused(gateway, scope, needle):
    with pytest.raises(DataBoundaryError, match=needle):
        await gateway.chat("cloud", messages=MSG, scope=scope)
    assert gateway.recorder.calls == []  # nothing was sent


async def test_local_tier_accepts_anything(gateway):
    for scope in (ContentScope.of("core"), ContentScope.unclassified(), ContentScope.of("x")):
        await gateway.chat("local", messages=MSG, scope=scope, max_tokens=7)
    assert len(gateway.recorder.calls) == 3


async def test_embed_is_boundary_checked_and_local(gateway):
    vectors = await gateway.embed(["a", "b"], scope=ContentScope.of("core"))
    assert len(vectors) == 2
    with pytest.raises(DataBoundaryError):
        await gateway.embed(["a"], scope=ContentScope.of("core"), tier_name="cloud")
