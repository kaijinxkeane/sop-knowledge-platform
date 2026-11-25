from pathlib import Path

import pytest

from app.models.config import load_gateway_config
from tests.conftest import CONFIG_DIR

ENV = {"OLLAMA_BASE_URL": "http://localhost:11434"}


def test_repo_config_loads_with_expected_tiers():
    cfg = load_gateway_config(CONFIG_DIR, ENV)
    assert {"router", "answer", "reasoning", "background", "classifier", "embedding"} <= set(
        cfg.tiers
    )
    assert {"core", "it", "hr"} <= set(cfg.spaces)


def test_reads_every_note_tiers_are_local():
    cfg = load_gateway_config(CONFIG_DIR, ENV)
    # The Classifier reads every note and embeddings index everything: local from day one.
    assert cfg.tier("classifier").location == "local"
    assert cfg.tier("embedding").location == "local"
    # Background writing (Librarian, review summaries, handover checks) stays local.
    assert cfg.tier("background").location == "local"
    assert cfg.tier("classifier").base_url == "http://localhost:11434/v1"
    # The conflict second opinion reads SOP passages too: local, thinking on.
    assert cfg.tier("conflict-confirm").location == "local"
    assert cfg.tier("conflict-confirm").think is None


def test_every_tier_is_local():
    """This system runs without Claude (decided 2026-11-25): nothing leaves the machine."""
    cfg = load_gateway_config(CONFIG_DIR, ENV)
    assert {n for n, t in cfg.tiers.items() if t.location == "cloud"} == set()
    assert {t.provider for t in cfg.tiers.values()} == {"openai_compat"}
    for name in ("answer", "reasoning", "router"):
        assert cfg.tier(name).location == "local"


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


def test_cloud_providers_are_refused(tmp_path):
    """The Claude connector was removed (2026-11-25): its provider name is unknown."""
    d = _write(tmp_path, "tiers:\n  x: {provider: anthropic, model: m}\n")
    with pytest.raises(ValueError, match="provider must be one of"):
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
    d = _write(
        tmp_path,
        "tiers:\n  x: {provider: openai_compat, base_url: http://example.com/v1, model: m}\n",
    )
    with pytest.raises(KeyError, match="unknown model tier"):
        load_gateway_config(d, {}).tier("missing")


def test_reserved_space_name_rejected(tmp_path):
    d = _write(
        tmp_path,
        "tiers:\n  x: {provider: openai_compat, base_url: http://example.com/v1, model: m}\n",
        {"bad": "name: __unclassified__\n"},
    )
    with pytest.raises(ValueError, match="reserved"):
        load_gateway_config(d, {})


def test_any_fallback_is_local_and_final():
    cfg = load_gateway_config(CONFIG_DIR, {"OLLAMA_BASE_URL": "http://localhost:11434"})
    for t in cfg.tiers.values():
        if t.fallback_tier:
            fb = cfg.tier(t.fallback_tier)
            assert fb.location == "local" and fb.fallback_tier is None


@pytest.mark.parametrize("fb", ["missing", "cloud2"])
def test_fallback_must_exist_and_be_local(tmp_path, fb):
    d = _write(
        tmp_path,
        "tiers:\n"
        f"  x: {{provider: openai_compat, base_url: http://e/v1, model: m, fallback_tier: {fb}}}\n"
        "  cloud2: {provider: openai_compat, base_url: http://e/v1, model: m}\n",
    )
    with pytest.raises(ValueError, match="fallback_tier"):
        load_gateway_config(d, {})
