from pathlib import Path

import pytest

from app.models.config import load_gateway_config
from tests.conftest import CONFIG_DIR

ENV = {"OLLAMA_BASE_URL": "http://localhost:11434"}


def test_repo_config_loads_with_expected_tiers():
    cfg = load_gateway_config(CONFIG_DIR, ENV)
    assert {"router", "answer", "reasoning", "drafting", "classifier", "embedding"} <= set(
        cfg.tiers
    )
    assert {"core", "it", "hr"} <= set(cfg.spaces)


def test_reads_every_note_tiers_are_local():
    cfg = load_gateway_config(CONFIG_DIR, ENV)
    # The Classifier reads every note and embeddings index everything: local from day one.
    assert cfg.tier("classifier").location == "local"
    assert cfg.tier("embedding").location == "local"
    assert cfg.tier("classifier").base_url == "http://localhost:11434/v1"


def test_cloud_tiers_use_current_models():
    cfg = load_gateway_config(CONFIG_DIR, ENV)
    assert cfg.tier("answer").model == "claude-haiku-5-5"
    assert cfg.tier("reasoning").model == "claude-sonnet-5-5"
    assert cfg.tier("drafting").model == "claude-opus-5-5"
    # Routing is local: questions never go to Claude just to be routed.
    assert cfg.tier("router").location == "local"


def _write(tmp_path: Path, models: str, spaces: dict[str, str] | None = None) -> Path:
    (tmp_path / "models.yaml").write_text(models)
    (tmp_path / "spaces").mkdir()
    for name, body in (spaces or {}).items():
        (tmp_path / "spaces" / f"{name}.yaml").write_text(body)
    return tmp_path


def test_openai_compat_without_explicit_local_is_cloud(tmp_path):
    d = _write(
        tmp_path,
        "tiers:\n  x: {provider: openai_compat, base_url: http://example.com/v1, model: m}\n",
    )
    assert load_gateway_config(d, {}).tier("x").location == "cloud"


def test_anthropic_cannot_claim_local(tmp_path):
    d = _write(tmp_path, "tiers:\n  x: {provider: anthropic, model: m, location: local}\n")
    with pytest.raises(ValueError, match="always location: cloud"):
        load_gateway_config(d, {})


def test_unset_env_var_is_an_error(tmp_path):
    d = _write(
        tmp_path,
        "tiers:\n  x: {provider: openai_compat, location: local,"
        " base_url: '${NOPE}/v1', model: m}\n",
    )
    with pytest.raises(ValueError, match="NOPE"):
        load_gateway_config(d, {})


def test_unknown_provider_rejected(tmp_path):
    d = _write(tmp_path, "tiers:\n  x: {provider: someone, model: m}\n")
    with pytest.raises(ValueError, match="provider"):
        load_gateway_config(d, {})


def test_unknown_tier_lookup(tmp_path):
    d = _write(tmp_path, "tiers:\n  x: {provider: anthropic, model: m}\n")
    with pytest.raises(KeyError, match="unknown model tier"):
        load_gateway_config(d, {}).tier("missing")


def test_reserved_space_name_rejected(tmp_path):
    d = _write(
        tmp_path,
        "tiers:\n  x: {provider: anthropic, model: m}\n",
        {"bad": "name: __unclassified__\n"},
    )
    with pytest.raises(ValueError, match="reserved"):
        load_gateway_config(d, {})
