"""Local OCR: text inside images is searchable (plan §3.1). No network."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from app.vault import ocr
from app.vault.ocr import ImageReader, OcrSettings, read_image
from app.vault.parse import is_supported, parse_file

LINES = ("Discovery Workshop", "three minutes per person")


def picture(lines=LINES, size=(900, 260), fmt="PNG") -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=40)
    for i, line in enumerate(lines):
        d.text((30, 40 + 90 * i), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def norm(s: str) -> str:
    return " ".join(s.lower().split()).replace(" ", "")


def found(text: str, line: str) -> bool:
    return norm(line) in norm(text)


def test_image_file_is_read_line_by_line():
    assert is_supported("Core/whiteboard.png") and is_supported("Core/photo.JPG")
    parsed = parse_file("Core/whiteboard.png", picture())
    assert parsed.doc_type == "image" and parsed.kind == "attachment"
    (chunk,) = parsed.chunks
    assert chunk.text.startswith("Text in image:")
    assert all(found(chunk.text, line) for line in LINES)
    # top to bottom
    text = norm(chunk.text)
    assert text.index(norm(LINES[0])) < text.index(norm(LINES[1]))
    assert found(parse_file("Core/photo.jpg", picture(fmt="JPEG")).chunks[0].text, LINES[1])


def test_text_in_a_slide_picture():
    from pptx import Presentation
    from pptx.util import Inches

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Opening"
    slide.shapes.add_picture(io.BytesIO(picture()), Inches(1), Inches(2), width=Inches(6))
    buf = io.BytesIO()
    deck.save(buf)
    parsed = parse_file("Core/deck.pptx", buf.getvalue())
    (chunk,) = parsed.chunks
    assert chunk.number == 1 and "Opening" in chunk.text
    assert "Text in image:" in chunk.text and found(chunk.text, LINES[1])


def test_scanned_pdf_page_but_not_pages_with_text():
    from reportlab.lib.utils import ImageReader as RLImage
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawImage(RLImage(io.BytesIO(picture())), 50, 500, width=450, height=130)
    c.showPage()
    c.drawString(72, 720, "This page has plenty of real text, so it is not scanned at all.")
    c.drawImage(RLImage(io.BytesIO(picture(("Hidden extra",)))), 50, 400, width=450, height=130)
    c.showPage()
    c.save()
    p1, p2 = parse_file("Core/scan.pdf", buf.getvalue()).chunks
    assert p1.number == 1 and found(p1.text, LINES[0])
    assert p2.number == 2 and "Text in image" not in p2.text


def test_images_in_a_word_file():
    import docx

    d = docx.Document()
    d.add_heading("Checklist", 1)
    d.add_paragraph("See the photo of the whiteboard.")
    d.add_picture(io.BytesIO(picture()))
    buf = io.BytesIO()
    d.save(buf)
    text = "\n".join(c.text for c in parse_file("Core/c.docx", buf.getvalue()).chunks)
    assert "whiteboard" in text and found(text, LINES[1])


def test_off_switch_tiny_images_repeats_and_limit(monkeypatch):
    off = OcrSettings(enabled=False)
    assert read_image(picture(), off) == ""
    assert read_image(picture(size=(40, 40))) == ""  # an icon
    assert read_image(b"not an image") == ""
    calls = []
    monkeypatch.setattr(ocr, "read_image", lambda data, cfg=None: calls.append(1) or "x")
    reader = ImageReader(OcrSettings(max_images=2))
    a, b, c = picture(("a",)), picture(("b",)), picture(("c",))
    assert [reader(x) for x in (a, a, b, c)] == ["x", "", "x", ""]  # logo once, then the cap
    assert len(calls) == 2


def test_ocr_failures_never_raise(monkeypatch):
    class Broken:
        def __call__(self, *_):
            raise RuntimeError("boom")

    monkeypatch.setattr(ocr, "_engine", Broken())
    assert read_image(picture()) == ""
