"""Parsing the demo vault: Obsidian notes, slide decks, PDF worksheets, DOCX."""

import io

import pytest

from app.vault.parse import is_supported, parse_file, parse_note
from tests.conftest import REPO_ROOT

VAULT = REPO_ROOT / "demo-vault"
DISCOVERY = "Programmes/Signature Personal Brand Programme/01 Discovery/Discovery Workshop SOP.md"
DECK = "Training Content/Attachments/Brand Foundations.pptx"
WORKSHEET = "Training Content/Attachments/Values Card Sort Worksheet.pdf"


def parse(rel):
    return parse_file(rel, (VAULT / rel).read_bytes())


def test_note_frontmatter_links_embeds_tags_and_sections():
    d = parse(DISCOVERY)
    assert d.kind == "note" and d.doc_type == "sop"
    assert d.title == "Running the Discovery Workshop"
    assert d.frontmatter["owner"] == "Avery Tan"  # [[wikilink]] unwrapped
    assert d.frontmatter["stage"] == "discovery"
    targets = {(link.target, link.embed) for link in d.links}
    assert ("Intake Questionnaire Guide", False) in targets
    assert ("Brand Foundations.pptx", True) in targets
    assert ("Values Card Sort Worksheet.pdf", False) in targets
    assert {"workshop", "discovery"} <= set(d.tags)
    headings = [c.heading for c in d.chunks]
    assert "Running the Discovery Workshop › 3. Values card sort (45 minutes)" in headings


def test_note_without_frontmatter_takes_h1_title():
    d = parse("Inbox/printer jam fix.md")
    assert d.title == "printer jam fix" and d.frontmatter == {} and not d.frontmatter_error


def test_unclosed_frontmatter_is_flagged():
    d = parse_note("x.md", "---\nsensitivity: public\n# never closed\n")
    assert d.frontmatter_error


def test_tags_ignore_code_blocks_and_headings():
    d = parse_note("x.md", "# Title\nSee #real-tag here.\n```\n#not-a-tag\n```\n")
    assert d.tags == ["real-tag"]


def test_long_sections_are_split():
    body = "# T\n\n" + "\n\n".join("word " * 120 for _ in range(10))
    chunks = parse_note("x.md", body).chunks
    assert len(chunks) > 1 and all(len(c.text) <= 1500 for c in chunks)


def test_deck_is_read_slide_by_slide_with_speaker_notes():
    d = parse(DECK)
    assert d.kind == "attachment" and d.doc_type == "deck"
    assert len(d.parts) == 18
    slide14 = next(c for c in d.chunks if c.number == 14)
    assert slide14.part == "slide" and slide14.heading.startswith("Slide 14:")
    assert "colleagues' intake answers silently" in slide14.text
    assert "Speaker notes:" in slide14.text


def test_pdf_worksheet_pages_and_form_fields():
    d = parse(WORKSHEET)
    assert d.doc_type == "pdf" and d.chunks[0].part == "page" and d.chunks[0].number == 1
    assert "Values Card Sort Worksheet" in d.chunks[0].text
    assert "Form fields:" in d.chunks[0].text and "Top value 1" in d.chunks[0].text


def test_docx_by_heading():
    import docx

    doc = docx.Document()
    doc.add_heading("Laptop returns", level=1)
    doc.add_paragraph("Wipe the laptop before returning it to IT.")
    buf = io.BytesIO()
    doc.save(buf)
    d = parse_file("IT/returns.docx", buf.getvalue())
    assert d.doc_type == "document"
    assert d.chunks[0].heading == "Laptop returns" and "Wipe the laptop" in d.chunks[0].text


@pytest.mark.parametrize(
    "path,ok",
    [
        ("a.md", True),
        ("b.PPTX", True),
        ("c.pdf", True),
        ("d.docx", True),
        ("e.png", True),  # read with local OCR
        ("e.svg", False),
        ("f.txt", False),
    ],
)
def test_supported_types(path, ok):
    assert is_supported(path) is ok
