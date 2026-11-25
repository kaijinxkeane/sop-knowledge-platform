"""The local answering eval's candidate list stays well-formed (plan §5.2)."""

import yaml

from app.models.config import load_gateway_config
from tests.conftest import CONFIG_DIR

CANDIDATES = yaml.safe_load((CONFIG_DIR / "eval" / "answer-candidates.yaml").read_text())


def test_references_are_the_live_answering_tiers():
    cfg = load_gateway_config(CONFIG_DIR, {"OLLAMA_BASE_URL": "http://localhost:11434"})
    for tier, model in CANDIDATES["references"].items():
        assert cfg.tier(tier).model == model


def test_candidates_are_complete_and_unique():
    tags = [c["tag"] for c in CANDIDATES["candidates"]]
    assert len(tags) == len(set(tags))
    assert "qwen3:8b" in tags
    for c in CANDIDATES["candidates"]:
        assert {"tag", "kind", "min_memory_gb", "why"} <= set(c)
        assert c["min_memory_gb"] in (16, 24, 32, 48, 64)
