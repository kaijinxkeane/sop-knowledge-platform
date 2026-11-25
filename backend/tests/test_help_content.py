"""The built-in user guide (config/help) is safe to give every vault: public,
published, and free of anything the safeguards would hold back."""

import pytest

import wiki_core
from app.vault.help import guide_sources
from app.vault.labels import load_vault_config


@pytest.mark.parametrize("src", guide_sources(), ids=lambda p: p.name)
def test_guide_is_public_published_and_clean(src):
    text = src.read_text(encoding="utf-8")
    fm = wiki_core.parse_frontmatter_block(wiki_core.split_markdown_frontmatter(text)[0])
    assert fm["sensitivity"] == "public"
    assert fm["status"] == "published"
    assert fm["title"] == src.stem
    lowered = text.lower()
    assert not [t for t in load_vault_config().flagged_terms if t in lowered]
    assert "@" not in text  # no email addresses


def test_help_folder_is_core_public():
    rule = next(r for r in load_vault_config().folder_rules if r.path == "Help/")
    assert rule.space == "core" and rule.sensitivity == "public"
