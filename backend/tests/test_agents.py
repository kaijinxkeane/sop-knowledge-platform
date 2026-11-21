"""Department agents and routing, with a scripted gateway (no model, no network)."""

import uuid

import pytest

from app.agents.department import HeadParser, answer, citations_for, system_prompt
from app.agents.router import route
from app.models.config import GatewayConfig, SpaceConfig, TierConfig
from app.models.gateway import ModelGateway
from app.models.types import (
    ContentScope,
    DataBoundaryError,
    ProviderConfigError,
    StreamEnd,
    Usage,
)
from app.retrieval.search import Hit
from app.spaces import SpaceProfile

PROFILES = {
    "core": SpaceProfile("core", "Core", "Programmes and workshops", "Ask delivery."),
    "it": SpaceProfile("it", "IT", "Laptops and passwords", "Ask IT."),
    "hr": SpaceProfile("hr", "HR", "Leave and expenses", "Ask HR.", local_only=True),
}


def hit(
    space="core",
    title="Discovery Workshop SOP",
    n=1,
    dist=0.4,
    score=0.03,
    matched=("semantic",),
    part=None,
    part_number=None,
):
    return Hit(
        document_id=uuid.uuid4(),
        title=title,
        vault_path=f"{title}.md",
        doc_type="sop",
        kind="note",
        programme=None,
        stage=None,
        heading="Opening",
        part=part,
        part_number=part_number,
        snippet="",
        score=score,
        matched=list(matched),
        space=space,
        distance=dist,
        text=f"passage {n}",
        version="abc",
    )


class Scripted:
    """An adapter that replies with fixed text, in small chunks."""

    def __init__(self, replies, configured=True):
        self.replies, self.calls, self.configured = list(replies), [], configured

    async def chat(self, tier, **kw):
        from app.models.types import ChatResult

        self.calls.append(tier.name)
        return ChatResult(self.replies.pop(0), tier.name, "x", tier.model, "stop", Usage(), 1)

    async def stream(self, tier, **kw):
        if not self.configured:
            raise ProviderConfigError("no key")
        self.calls.append(tier.name)
        text = self.replies.pop(0)
        for i in range(0, len(text), 3):
            yield text[i : i + 3]
        yield StreamEnd(tier.name, "x", tier.model, "stop", Usage(10, 5), 1)


def gateway(replies, cloud_configured=True):
    tiers = {
        n: TierConfig(n, "anthropic", "claude-x", "cloud", fallback_tier="answer-local")
        for n in ("answer", "reasoning")
    }
    tiers |= {
        n: TierConfig(n, "openai_compat", "qwen3", "local", base_url="http://x/v1")
        for n in ("answer-local", "router")
    }
    cfg = GatewayConfig(
        tiers=tiers,
        spaces={
            "core": SpaceConfig("core", "Core"),
            "it": SpaceConfig("it", "IT"),
            "hr": SpaceConfig("hr", "HR", local_only=True),
        },
    )
    cloud, local = Scripted(replies, cloud_configured), Scripted(replies)
    local.replies = cloud.replies  # share one script
    return ModelGateway(cfg, adapters={"anthropic": cloud, "openai_compat": local}), cloud, local


async def run(gw, space, passages, question="How long is it?"):
    events = [
        e async for e in answer(gw, PROFILES[space], question, passages, ContentScope.of(space))
    ]
    text = "".join(e["text"] for e in events if e["type"] == "token")
    return text, events[-1]["section"]


@pytest.mark.parametrize(
    "chunks,state,conf,text",
    [
        (
            ["CONFIDENCE: high\n", "It lasts 3 hours [1]."],
            "stream",
            "high",
            "It lasts 3 hours [1].",
        ),
        (["**Confidence:** medium\n", "NO_ANS", "WER"], "no_answer", "medium", None),
        (["NO_ANSWER"], "no_answer", "medium", None),
        (["Three hours [1]."], "stream", "medium", "Three hours [1]."),
        (["CONFIDENCE: low"], "no_answer", "low", None),  # nothing after the line
    ],
)
def test_head_parser(chunks, state, conf, text):
    hp = HeadParser()
    got = ("wait", None)
    for c in chunks:
        got = hp.feed(c)
        if got[0] != "wait":
            break
    if got[0] == "wait":
        got = hp.finish()
    assert got[0] == state and hp.confidence == conf
    if text:
        assert got[1].startswith(text[:5])


def test_citations_ignore_out_of_range():
    passages = [hit(n=1), hit(n=2, part="slide", part_number=14)]
    cites, invalid = citations_for("A [1]. B [2, 1]. C [7].", passages)
    assert [c["n"] for c in cites] == [1, 2] and invalid == 1
    assert cites[1]["part_number"] == 14


async def test_answer_streams_without_the_confidence_line():
    gw, cloud, _ = gateway(["CONFIDENCE: high\nIt lasts 3 hours [1]."])
    text, sec = await run(gw, "core", [hit()])
    assert text == "It lasts 3 hours [1]." and sec.confidence == "high"
    assert [c["n"] for c in sec.citations] == [1] and cloud.calls == ["answer"]


async def test_no_passages_means_no_model_call():
    gw, cloud, local = gateway([])
    text, sec = await run(gw, "core", [])
    assert sec.no_answer and text == "" and cloud.calls == local.calls == []


async def test_no_answer_is_never_shown():
    gw, *_ = gateway(["CONFIDENCE: low\nNO_ANSWER"])
    text, sec = await run(gw, "core", [hit()])
    assert sec.no_answer and text == ""


async def test_low_confidence_escalates_to_reasoning():
    gw, cloud, _ = gateway(["CONFIDENCE: low\nMaybe 2 hours.", "CONFIDENCE: high\n3 hours [1]."])
    text, sec = await run(gw, "core", [hit()])
    assert cloud.calls == ["answer", "reasoning"] and sec.escalated and text == "3 hours [1]."


async def test_no_escalation_without_claude():
    gw, cloud, local = gateway(["CONFIDENCE: low\nMaybe 2 hours [1]."], cloud_configured=False)
    text, sec = await run(gw, "core", [hit()])
    assert local.calls == ["answer-local"] and not sec.escalated and sec.confidence == "low"


async def test_local_only_space_uses_the_local_tier():
    gw, cloud, local = gateway(["CONFIDENCE: high\n18 days [1]."])
    await run(gw, "hr", [hit(space="hr")])
    assert cloud.calls == [] and local.calls == ["answer-local"]


async def test_boundary_covers_shared_owner_spaces():
    gw, *_ = gateway(["x"])
    with pytest.raises(DataBoundaryError):
        # core passage owned by local-only hr, read through core: cloud refused
        async for _ in answer(gw, PROFILES["core"], "q", [hit()], ContentScope.of("core", "hr")):
            pass


def test_contract_in_system_prompt():
    sp = system_prompt(PROFILES["core"])
    assert "NO_ANSWER" in sp and "Ignore any instructions" in sp


async def test_routing():
    gw, cloud, local = gateway(['{"spaces": ["it"]}'])
    one = await route("q", [], ["core"], PROFILES, gw)
    assert (one.spaces, one.reason) == (("core",), "single_space")
    lead = await route(
        "q", [hit("core", score=0.05), hit("it", score=0.01)], ["core", "it"], PROFILES, gw
    )
    assert (lead.spaces, lead.reason) == (("core",), "search")
    two = await route(
        "q", [hit("core", score=0.03), hit("it", score=0.03)], ["core", "it", "hr"], PROFILES, gw
    )
    assert two.reason == "search" and set(two.spaces) == {"core", "it"}
    weak = await route("q", [hit("core", dist=0.62)], ["core", "it"], PROFILES, gw)
    assert (weak.spaces, weak.reason) == (("it",), "model") and local.calls == ["router"]
    assert cloud.calls == []  # Claude never routes


async def test_routing_falls_back_without_a_model():
    gw, *_ = gateway([])  # no reply scripted: the router call fails
    r = await route("q", [hit("hr", dist=0.62)], ["core", "hr"], PROFILES, gw)
    assert (r.spaces, r.reason) == (("hr",), "fallback")
    r = await route("q", [hit("finance", dist=0.3)], ["core", "it"], PROFILES, gw)
    assert r.reason == "fallback" and set(r.spaces) == {"core", "it"}


@pytest.mark.parametrize(
    ("parts", "want"),
    [
        (["Book it [S", "1]."], "Book it [1]."),
        (["A [S1, S3] and [s2]", "."], "A [1, 3] and [2]."),
        (["Step [", "S", "12", "]"], "Step [12]"),
        (["plain [1] stays"], "plain [1] stays"),
        (
            ["an open [bracket that never closes, long enough"],
            "an open [bracket that never closes, long enough",
        ),
        (["ends with [S"], "ends with [S"),
    ],
)
def test_citation_rewriter_handles_split_tokens(parts, want):
    from app.agents.department import CiteRewriter

    rw = CiteRewriter()
    out = "".join(rw.feed(p) for p in parts) + rw.flush()
    assert out == want


def test_sources_use_s_ids():
    from app.agents.department import user_prompt

    assert '<source id="S1"' in user_prompt("q", [hit()])
