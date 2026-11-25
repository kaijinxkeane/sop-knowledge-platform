"""A real render with LibreOffice, where it is installed (skipped otherwise)."""

from pathlib import Path

import pytest

from app.vault import slides

DECK = (
    Path(__file__).resolve().parents[2]
    / "demo-vault/Training Content/Attachments/Brand Foundations.pptx"
)

pytestmark = pytest.mark.skipif(slides.soffice() is None, reason="LibreOffice not installed")


def test_demo_deck_renders_one_png_per_slide(tmp_path):
    from pptx import Presentation

    expected = len(Presentation(str(DECK)).slides)
    out = tmp_path / "deck"
    assert slides._render_sync(DECK.read_bytes(), out) == expected
    first = (out / "1.png").read_bytes()
    assert first.startswith(b"\x89PNG") and len(first) > 5_000
