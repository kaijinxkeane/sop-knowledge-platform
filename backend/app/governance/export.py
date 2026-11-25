"""PDF export of SOPs (frontend spec §9.3): a clean, neutral layout.

The header names the SOP, its version, owner, author, approver and approval
date, and who printed it when. Restricted content carries a watermark with the
reader's name, the date and "Restricted" on every page.

The note's Markdown is turned into plain paragraphs, headings, lists and
tables. Nothing in the note is interpreted as markup: text is escaped first,
links become their text, images and embeds are left out.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.governance.versions import split_frontmatter


@dataclass
class ExportDoc:
    title: str
    text: str  # the Markdown the reader may read (approved or their own latest)
    version: str  # "Version 3" or "Draft (after version 2)"
    sop_id: str
    owner: str | None = None
    author: str | None = None
    approver: str | None = None
    approved_on: date | None = None


@dataclass
class ExportJob:
    docs: list[ExportDoc]
    printed_by: str
    printed_on: date
    restricted: bool
    heading: str | None = None  # a programme stage: shown on a cover line
    meta: dict = field(default_factory=dict)


_STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_STYLES["BodyText"], fontSize=10, leading=14)
SMALL = ParagraphStyle(
    "small", parent=BODY, fontSize=8, leading=11, textColor=colors.HexColor("#555555")
)
TITLE = ParagraphStyle("title", parent=_STYLES["Title"], fontSize=18, leading=22, alignment=0)
H = {
    1: ParagraphStyle("h1", parent=_STYLES["Heading1"], fontSize=15, leading=19),
    2: ParagraphStyle("h2", parent=_STYLES["Heading2"], fontSize=13, leading=17),
    3: ParagraphStyle("h3", parent=_STYLES["Heading3"], fontSize=11, leading=15),
}
CODE = ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=8.5, leading=11)

_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
_EMBED = re.compile(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)|(?<![_\w])_(?!\s)(.+?)(?<!\s)_(?!\w)")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_COMMENT = re.compile(r"%%.*?%%", re.S)


def inline(text: str) -> str:
    """Markdown inline text -> reportlab paragraph markup (escaped first)."""
    text = _EMBED.sub("", text)
    text = _WIKILINK.sub(lambda m: m.group(2) or m.group(1).rsplit("/", 1)[-1], text)
    text = _LINK.sub(r"\1", text)
    out = escape(text)
    out = _CODE_SPAN.sub(lambda m: f'<font face="Courier">{m.group(1)}</font>', out)
    out = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", out)
    out = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", out)
    return out


_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")


def markdown_flowables(md: str) -> list:
    """Headings, paragraphs, lists, tables, code blocks and quotes."""
    _, _, body = split_frontmatter(md)
    body = _COMMENT.sub("", body)
    lines = body.splitlines()
    out: list = []
    para: list[str] = []
    items: list[tuple[bool, str]] = []
    i = 0

    def flush_para():
        if para:
            out.append(Paragraph(inline(" ".join(s.strip() for s in para)), BODY))
            para.clear()

    def flush_list():
        if items:
            ordered = items[0][0]
            out.append(
                ListFlowable(
                    [ListItem(Paragraph(inline(t), BODY), leftIndent=12) for _, t in items],
                    bulletType="1" if ordered else "bullet",
                    start="1" if ordered else None,
                    leftIndent=14,
                    bulletFontSize=8,
                )
            )
            items.clear()

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush_para(), flush_list()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append(Preformatted("\n".join(lines[i + 1 : j]), CODE))
            i = j + 1
            continue
        if not line.strip():
            flush_para(), flush_list()
            i += 1
            continue
        if m := _HEADING.match(line):
            flush_para(), flush_list()
            out.append(Paragraph(inline(m.group(2)), H[min(len(m.group(1)), 3)]))
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush_para(), flush_list()
            rows = []
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                if j != i + 1:
                    cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    rows.append([Paragraph(inline(c), SMALL) for c in cells])
                j += 1
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            t = Table(rows, repeatRows=1, hAlign="LEFT")
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            out.append(t)
            i = j
            continue
        if m := _LIST.match(line):
            flush_para()
            ordered = m.group(2)[0].isdigit()
            if items and items[0][0] != ordered:
                flush_list()
            items.append((ordered, m.group(3)))
            i += 1
            continue
        if line.lstrip().startswith(">"):
            flush_para(), flush_list()
            quote = re.sub(r"^\s*>\s?(\[![\w-]+\][+-]?\s*)?", "", line)
            out.append(Paragraph(inline(quote), ParagraphStyle("q", parent=BODY, leftIndent=12)))
            i += 1
            continue
        if items and line.startswith(("  ", "\t")):
            ordered, prev = items[-1]
            items[-1] = (ordered, prev + " " + line.strip())
            i += 1
            continue
        flush_list()
        para.append(line)
        i += 1
    flush_para(), flush_list()
    return out


def _header(d: ExportDoc) -> list:
    rows = [
        ("SOP ID", d.sop_id),
        ("Version", d.version),
        ("Owner", d.owner or "—"),
        ("Author", d.author or "—"),
        ("Approved by", d.approver or "—"),
        ("Approved on", d.approved_on.isoformat() if d.approved_on else "—"),
    ]
    table = Table(
        [[Paragraph(f"<b>{escape(k)}</b>", SMALL), Paragraph(escape(v), SMALL)] for k, v in rows],
        colWidths=[28 * mm, None],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1)])
    )
    return [KeepTogether([Paragraph(escape(d.title), TITLE), table]), Spacer(1, 6 * mm)]


def render_pdf(job: ExportJob) -> bytes:
    buf = io.BytesIO()
    printed = f"Printed by {job.printed_by} on {job.printed_on.isoformat()}"
    title = job.heading or (job.docs[0].title if job.docs else "SOP")

    def page(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(18 * mm, 10 * mm, printed)
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"Page {doc.page}")
        if job.restricted:
            canvas.drawString(18 * mm, h - 10 * mm, "RESTRICTED")
            canvas.translate(w / 2, h / 2)
            canvas.rotate(35)
            canvas.setFillColor(colors.Color(0.75, 0.1, 0.1, alpha=0.12))
            canvas.setFont("Helvetica-Bold", 40)
            canvas.drawCentredString(0, 20, "RESTRICTED")
            canvas.setFont("Helvetica-Bold", 16)
            canvas.drawCentredString(0, -12, f"{job.printed_by} · {job.printed_on.isoformat()}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="",
        subject="",
        creator="SOP platform",
    )
    story: list = []
    if job.heading:
        story += [
            Paragraph(escape(job.heading), TITLE),
            Paragraph(escape(printed), SMALL),
            PageBreak(),
        ]
    for n, d in enumerate(job.docs):
        if n:
            story.append(PageBreak())
        story += _header(d)
        story += markdown_flowables(d.text)
    pdf.build(story, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
