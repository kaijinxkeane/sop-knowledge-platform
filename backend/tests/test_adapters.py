import json
from types import SimpleNamespace

import httpx
import pytest

from app.models.adapters.anthropic_adapter import FALLBACK_BETA, AnthropicAdapter
from app.models.adapters.openai_compat import OpenAICompatAdapter
from app.models.config import TierConfig
from app.models.types import (
    Message,
    ModelRefusalError,
    ProviderConfigError,
    ProviderUnavailableError,
)

HAIKU = TierConfig(
    "answer", "anthropic", "claude-haiku-5-5", "cloud", effort="medium", max_tokens=800
)
SONNET = TierConfig(
    "reasoning", "anthropic", "claude-sonnet-5-5", "cloud", effort="medium", fallbacks="default"
)
LOCAL = TierConfig(
    "classifier", "openai_compat", "qwen3:4b", "local", base_url="http://ollama:11434/v1"
)
MSGS = [Message("user", "hello")]


# --- Anthropic -------------------------------------------------------------


def test_params_basic():
    p = AnthropicAdapter.build_params(HAIKU, system="sys", messages=MSGS, max_tokens=800)
    assert p["model"] == "claude-haiku-5-5"
    assert p["system"] == "sys"
    assert p["output_config"] == {"effort": "medium"}
    assert p["cache_control"] == {"type": "ephemeral"}
    assert p["messages"] == [{"role": "user", "content": "hello"}]
    # Sampling parameters are rejected by current models; never send them.
    assert not {"temperature", "top_p", "top_k"} & set(p)
    assert "betas" not in p


def test_params_with_server_side_fallback():
    p = AnthropicAdapter.build_params(SONNET, system=None, messages=MSGS, max_tokens=100)
    assert p["betas"] == [FALLBACK_BETA]
    assert p["fallbacks"] == "default"
    assert "system" not in p


def _response(stop_reason="end_turn", text="hi there"):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        model="claude-haiku-5-5",
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=12, output_tokens=3, cache_read_input_tokens=8),
        _request_id="req_123",
    )


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _adapter_with(response):
    adapter = AnthropicAdapter("test-key")
    msgs = FakeMessages(response)
    adapter._client = SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs))
    return adapter, msgs


async def test_chat_extracts_text_and_usage():
    adapter, msgs = _adapter_with(_response())
    result = await adapter.chat(HAIKU, system=None, messages=MSGS, max_tokens=800)
    assert result.text == "hi there"  # thinking blocks are ignored
    assert result.usage.cache_read_tokens == 8
    assert result.request_id == "req_123"
    assert msgs.kwargs["max_tokens"] == 800


async def test_chat_refusal_raises():
    adapter, _ = _adapter_with(_response(stop_reason="refusal", text=""))
    with pytest.raises(ModelRefusalError):
        await adapter.chat(HAIKU, system=None, messages=MSGS, max_tokens=10)


async def test_missing_key_is_config_error():
    with pytest.raises(ProviderConfigError, match="not set"):
        await AnthropicAdapter(None).chat(HAIKU, system=None, messages=MSGS, max_tokens=10)


# --- OpenAI-compatible (Ollama) ------------------------------------------


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_local_chat_strips_think_and_sends_system():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "choices": [
                    {"message": {"content": "<think>hmm</think>\nready"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 2},
            },
        )

    adapter = OpenAICompatAdapter(transport=_transport(handler))
    result = await adapter.chat(LOCAL, system="be brief", messages=MSGS, max_tokens=50)
    assert result.text == "ready"
    assert seen["url"] == "http://ollama:11434/v1/chat/completions"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert seen["body"]["max_tokens"] == 50
    assert result.usage.input_tokens == 9


async def test_local_embeddings_keep_input_order():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2]},
                    {"index": 0, "embedding": [0.1]},
                ]
            },
        )

    adapter = OpenAICompatAdapter(transport=_transport(handler))
    assert await adapter.embed(LOCAL, ["a", "b"]) == [[0.1], [0.2]]


async def test_local_missing_model_hints_pull():
    adapter = OpenAICompatAdapter(transport=_transport(lambda r: httpx.Response(404, json={})))
    with pytest.raises(ProviderConfigError, match="ollama pull qwen3:4b"):
        await adapter.chat(LOCAL, system=None, messages=MSGS, max_tokens=5)


async def test_local_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused")

    adapter = OpenAICompatAdapter(transport=_transport(handler))
    with pytest.raises(ProviderUnavailableError):
        await adapter.chat(LOCAL, system=None, messages=MSGS, max_tokens=5)
