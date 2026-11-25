import json

import httpx
import pytest

from app.models.adapters.openai_compat import OpenAICompatAdapter
from app.models.config import TierConfig
from app.models.types import (
    Message,
    ProviderConfigError,
    ProviderUnavailableError,
)

LOCAL = TierConfig(
    "classifier", "openai_compat", "qwen3:4b", "local", base_url="http://ollama:11434/v1"
)
MSGS = [Message("user", "hello")]


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


# --- local streaming: thinking blocks are stripped ------------------------------------

from app.models.adapters.openai_compat import _ThinkStripper  # noqa: E402
from app.models.config import TierConfig as _Tier  # noqa: E402


@pytest.mark.parametrize(
    "chunks,expected",
    [
        (["<thi", "nk>\nhmm\n</th", "ink>\n\nHello", " there"], "Hello there"),
        (["Hello", " there"], "Hello there"),
        (["  <", "b>bold</b>"], "  <b>bold</b>"),
        (["<think>never closed"], ""),
    ],
)
def test_think_stripper(chunks, expected):
    s = _ThinkStripper()
    assert "".join(s.feed(c) for c in chunks) + s.flush() == expected


def test_no_think_and_json_mode_payload():
    tier = _Tier("t", "openai_compat", "qwen3:4b", "local", base_url="http://x/v1", think=False)
    from app.models.types import Message as _M

    body = OpenAICompatAdapter.payload(
        tier, system="sys", messages=[_M("user", "hi")], max_tokens=10, json_mode=True
    )
    assert body["reasoning_effort"] == "none" and body["messages"][-1]["content"] == "hi"
    assert body["response_format"] == {"type": "json_object"}
