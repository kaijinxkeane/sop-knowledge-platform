"""Read vault files into searchable chunks (plan §3.1). Local only; no models.

- Markdown notes (Obsidian): frontmatter, [[wikilinks]], ![[embeds]], #tags,
  chunked by heading.
- .pptx decks: one chunk per slide (title, text, tables, speaker notes).
- .pdf: one chunk per page, including fillable form-field labels.
- .docx: chunked by heading.
- Images (.png/.jpg/.jpeg) and text inside images in decks, scanned PDF pages
  and Word files: local OCR (app/vault/ocr.py), marked "Text in image".
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.vault.ocr import ImageReader
from wiki_core import parse_frontmatter_block, split_markdown_frontmatter

NOTE_EXT = {".md"}
ATTACHMENT_EXT = {
    ".pptx": "deck",
    ".pdf": "pdf",
    ".docx": "document",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
SCANNED_PAGE = 30  # a PDF page with less text than this is read with OCR
MAX_CHUNK = 1500  # characters

_WIKILINK = re.compile(r"(!?)\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")
_TAG = re.compile(r"(?<![\w/#&])#([A-Za-z][\w/-]*)")
_FENCE = re.compile(r"```.*?```", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass
class Chunk:
    text: str
    heading: str | None = None
    part: str | None = None  # slide | page
    number: int | None = None


@dataclass
class Part:
    part: str
    number: int
    title: str
    speaker_notes: str = ""


@dataclass
class Link:
    target: str  # note or file name as written (folder and extension stripped for notes)
    embed: bool


@dataclass
class Parsed:
    kind: str  # note | attachment
    doc_type: str
    title: str
    frontmatter: dict = field(default_factory=dict)
    frontmatter_error: bool = False
    body: str = ""
    links: list[Link] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)


def is_supported(path: str) -> bool:
    ext = PurePosixPath(path).suffix.lower()
    return ext in NOTE_EXT or ext in ATTACHMENT_EXT


def parse_file(path: str, data: bytes) -> Parsed:
    ext = PurePosixPath(path).suffix.lower()
    if ext in NOTE_EXT:
        return parse_note(path, data.decode("utf-8", errors="replace"))
    if ext == ".pptx":
        return parse_pptx(path, data)
    if ext == ".pdf":
        return parse_pdf(path, data)
    if ext == ".docx":
        return parse_docx(path, data)
    if ext in IMAGE_EXT:
        return parse_image(path, data)
    raise ValueError(f"unsupported file type: {ext}")


# --- markdown ----------------------------------------------------------------


def link_name(target: str) -> str:
    """Normalise a link target for matching: last path part, .md dropped, lower-case."""
    name = target.strip().rsplit("/", 1)[-1]
    if name.lower().endswith(".md"):
        name = name[:-3]
    return name.strip().lower()


def _clean_value(value):
    if isinstance(value, str):
        v = value.strip()
        m = re.fullmatch(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", v)
        return m.group(1).strip() if m else v
    if isinstance(value, list):
        return [_clean_value(v) for v in value]
    return value


def parse_note(path: str, text: str) -> Parsed:
    fm: dict = {}
    error = False
    body = text
    split = split_markdown_frontmatter(text)
    if split:
        try:
            raw = parse_frontmatter_block(split[0]) or {}
            fm = {k: _clean_value(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
            error = not isinstance(raw, dict)
        except Exception:  # noqa: BLE001 - unparseable frontmatter fails closed later
            error = True
        body = split[1]
    elif text.startswith("---"):
        error = True  # frontmatter that never closes

    title = str(fm.get("title") or "").strip()
    if not title:
        h1 = next(
            (
                m.group(2)
                for line in body.splitlines()
                if (m := _HEADING.match(line)) and len(m.group(1)) == 1
            ),
            None,
        )
        title = h1 or PurePosixPath(path).stem

    links, seen = [], set()
    for m in _WIKILINK.finditer(body):
        target, embed = m.group(2).strip(), bool(m.group(1))
        key = (link_name(target) if not _is_file(target) else target.lower(), embed)
        if key not in seen:
            seen.add(key)
            links.append(Link(target=target, embed=embed))

    tags = set()
    fm_tags = fm.get("tags")
    if isinstance(fm_tags, list):
        tags.update(str(t).lstrip("#").lower() for t in fm_tags if t)
    elif isinstance(fm_tags, str) and fm_tags.strip():
        tags.update(t.lstrip("#").lower() for t in re.split(r"[,\s]+", fm_tags) if t)
    tags.update(t.lower() for t in _TAG.findall(_FENCE.sub("", body)))

    return Parsed(
        kind="note",
        doc_type=str(fm.get("doc_type") or "guide"),
        title=title,
        frontmatter=fm,
        frontmatter_error=error,
        body=body,
        links=links,
        tags=sorted(tags),
        chunks=_markdown_chunks(body),
    )


def _is_file(target: str) -> bool:
    return PurePosixPath(target).suffix.lower() in set(ATTACHMENT_EXT)


def _markdown_chunks(body: str) -> list[Chunk]:
    sections: list[tuple[list[str], list[str]]] = []
    path: list[str] = []
    lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            if any(x.strip() for x in lines):
                sections.append((list(path), lines))
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2).strip()]
            lines = [line]
        else:
            lines.append(line)
    if any(x.strip() for x in lines):
        sections.append((list(path), lines))
    chunks = []
    for heading_path, sec in sections:
        heading = " › ".join(heading_path) or None
        for piece in _split("\n".join(sec).strip()):
            chunks.append(Chunk(text=piece, heading=heading))
    return chunks


def _split(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK:
        return [text] if text else []
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) + 2 > MAX_CHUNK:
            out.append(cur.strip())
            cur = ""
        while len(para) > MAX_CHUNK:  # a single huge paragraph
            out.append(para[:MAX_CHUNK])
            para = para[MAX_CHUNK:]
        cur = f"{cur}\n\n{para}" if cur else para
    if cur.strip():
        out.append(cur.strip())
    return out


# --- attachments -------------------------------------------------------------


def _pictures(shapes):
    """Picture shapes on a slide (pictures and picture placeholders), inside groups too."""
    from pptx.shapes.group import GroupShape
    from pptx.shapes.picture import Picture
    from pptx.shapes.placeholder import PlaceholderPicture

    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _pictures(shape.shapes)
        elif isinstance(shape, Picture | PlaceholderPicture):
            yield shape


def _image_blob(shape) -> bytes | None:
    try:
        return shape.image.blob
    except Exception:  # noqa: BLE001 - linked or unsupported picture
        return None


def parse_pptx(path: str, data: bytes) -> Parsed:
    from pptx import Presentation

    ocr = ImageReader()
    deck = Presentation(io.BytesIO(data))
    title = (deck.core_properties.title or "").strip() or PurePosixPath(path).stem
    chunks, parts = [], []
    for n, slide in enumerate(deck.slides, start=1):
        slide_title = ""
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            slide_title = slide.shapes.title.text_frame.text.strip()
        texts = []
        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    texts.append(" | ".join(c.text.strip() for c in row.cells))
        for pic in _pictures(slide.shapes):
            blob = _image_blob(pic)
            seen = ocr(blob) if blob else ""
            if seen:
                texts.append(f"Text in image: {seen}")
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        parts.append(Part("slide", n, slide_title, notes))
        body = "\n".join(t for t in [slide_title, *texts] if t)
        if notes:
            body += f"\nSpeaker notes: {notes}"
        if body.strip():
            chunks.append(
                Chunk(
                    text=body,
                    heading=f"Slide {n}: {slide_title}".rstrip(": "),
                    part="slide",
                    number=n,
                )
            )
    return Parsed(kind="attachment", doc_type="deck", title=title, chunks=chunks, parts=parts)


def parse_pdf(path: str, data: bytes) -> Parsed:
    from pypdf import PdfReader

    ocr = ImageReader()
    reader = PdfReader(io.BytesIO(data))
    meta_title = ((reader.metadata or {}).get("/Title") or "").strip() if reader.metadata else ""
    title = meta_title or PurePosixPath(path).stem
    chunks, parts = [], []
    for n, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        labels = []
        for annot in page.get("/Annots") or []:
            obj = annot.get_object()
            if obj.get("/Subtype") == "/Widget":
                label = obj.get("/TU") or obj.get("/T")
                if label:
                    labels.append(str(label))
        if len(text) < SCANNED_PAGE:
            seen = "\n".join(filter(None, (ocr(b) for b in _page_images(page))))
            if seen:
                text = (text + "\n" if text else "") + f"Text in image: {seen}"
        if labels:
            text += "\nForm fields: " + "; ".join(labels)
        first = text.splitlines()[0][:120] if text else ""
        parts.append(Part("page", n, first))
        if text:
            chunks.append(Chunk(text=text, heading=f"Page {n}", part="page", number=n))
    return Parsed(kind="attachment", doc_type="pdf", title=title, chunks=chunks, parts=parts)


def parse_docx(path: str, data: bytes) -> Parsed:
    import docx

    document = docx.Document(io.BytesIO(data))
    title = (document.core_properties.title or "").strip() or PurePosixPath(path).stem
    md_lines = []
    for para in document.paragraphs:
        style = (para.style.name or "").lower() if para.style is not None else ""
        if style.startswith("heading") and para.text.strip():
            level = int(style.split()[-1]) if style.split()[-1].isdigit() else 1
            md_lines.append(f"{'#' * min(level, 6)} {para.text.strip()}")
        else:
            md_lines.append(para.text)
    for table in document.tables:
        for row in table.rows:
            md_lines.append(" | ".join(c.text.strip() for c in row.cells))
    ocr = ImageReader()
    seen = []
    for rel in document.part.rels.values():
        if "image" in rel.reltype and not rel.is_external:
            text = ocr(rel.target_part.blob)
            if text:
                seen.append(text)
    if seen:
        md_lines += ["", "## Text in images", *seen]
    return Parsed(
        kind="attachment",
        doc_type="document",
        title=title,
        chunks=_markdown_chunks("\n".join(md_lines)),
    )


def _page_images(page):
    try:
        for img in page.images:
            yield img.data
    except Exception:  # noqa: BLE001 - unsupported image encoding
        return


def parse_image(path: str, data: bytes) -> Parsed:
    from app.vault.ocr import read_image

    title = PurePosixPath(path).stem
    text = read_image(data)
    chunks = [Chunk(text=f"Text in image: {text}", heading="Image")] if text else []
    return Parsed(kind="attachment", doc_type="image", title=title, chunks=chunks)
