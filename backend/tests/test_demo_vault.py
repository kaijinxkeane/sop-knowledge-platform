"""The demo vault and its ground-truth labels stay consistent (fictional data only)."""

from pathlib import Path

import pytest
import yaml

import wiki_core
from tests.conftest import REPO_ROOT

VAULT = REPO_ROOT / "demo-vault"
LABELS = yaml.safe_load((REPO_ROOT / "demo-vault-labels.yaml").read_text())
SPACES = {"core", "it", "hr"}
SENSITIVITY = {"public", "internal", "restricted"}


def _files() -> set[str]:
    return {str(p.relative_to(VAULT)) for p in VAULT.rglob("*") if p.is_file()}


def test_every_file_is_labelled_exactly_once():
    labelled = set(LABELS["notes"]) | set(LABELS["attachments"]) | set(LABELS["ignored"])
    assert _files() == labelled


@pytest.mark.parametrize("path,label", sorted({**LABELS["notes"], **LABELS["attachments"]}.items()))
def test_labels_use_known_values(path, label):
    assert label["space"] in SPACES
    assert label["sensitivity"] in SENSITIVITY
    if "stage" in label:
        assert label["stage"] in LABELS["stages"]


@pytest.mark.parametrize("path,label", sorted(LABELS["notes"].items()))
def test_frontmatter_matches_declared_labels(path, label):
    text = (VAULT / path).read_text(encoding="utf-8")
    split = wiki_core.split_markdown_frontmatter(text)
    fm = wiki_core.parse_frontmatter_block(split[0]) if split else {}
    if label["label_source"] == "frontmatter":
        assert fm.get("sensitivity") == label["sensitivity"], path
    elif "sensitivity" in fm:
        pytest.fail(f"{path}: label_source is 'inferred' but the note declares sensitivity")
    if path.startswith("Inbox/"):
        assert split is None, "inbox notes are deliberately unlabelled"


def test_fake_personal_data_uses_reserved_ranges():
    # Safeguard test data must never be a real person's details.
    text = (VAULT / "Inbox/meeting notes 2026-10-14.md").read_text()
    assert "@example.com" in text and "+65 8000 0000" in text


def test_decks_have_speaker_notes():
    from pptx import Presentation

    deck = Presentation(VAULT / "Training Content/Attachments/Brand Foundations.pptx")
    assert len(deck.slides) == 18
    assert "colleagues' intake answers" in deck.slides[13].notes_slide.notes_text_frame.text


def test_init_script_exists_and_is_executable():
    script = REPO_ROOT / "deploy" / "init-demo-vault.sh"
    assert script.stat().st_mode & 0o111
    assert Path(script).read_text().count("DEVELOPMENT ONLY") == 1
