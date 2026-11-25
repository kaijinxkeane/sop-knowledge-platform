"""PDF export rendering: escaped text, a header, a watermark on restricted content."""

import io
from datetime import date

from pypdf import PdfReader

from app.governance.export import ExportDoc, ExportJob, inline, markdown_flowables, render_pdf

NOTE = """---
status: published
---
# Discovery Workshop

Open with the **brand story**, then see [[Methodology/Voice and Story Method|the voice method]].

1. Book the room
2. Print name cards

- [ ] Send the agenda
- Bring <font color="red">markers</font> & tape

| Step | Owner |
|---|---|
| Intake | Trainer |

![[Journey Map.png]]
%% a private Obsidian comment %%
"""


def text_of(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def job(restricted: bool) -> ExportJob:
    return ExportJob(
        docs=[
            ExportDoc(
                title="Discovery Workshop",
                text=NOTE,
                version="Version 3",
                sop_id="AB12CD34",
                owner="Core team",
                author="Avery Tan",
                approver="Jordan Lee",
                approved_on=date(2026, 11, 20),
            )
        ],
        printed_by="Pat Example",
        printed_on=date(2026, 11, 25),
        restricted=restricted,
    )


def test_note_text_is_never_markup():
    assert (
        inline('<font color="red">x</font> & y') == '&lt;font color="red"&gt;x&lt;/font&gt; &amp; y'
    )
    assert inline("see [[A/B|the B]] and [site](https://evil.example)") == "see the B and site"
    assert inline("![[secret.png]]![x](http://t/p.png)") == ""
    assert len(markdown_flowables(NOTE)) >= 6


def test_header_body_and_watermark():
    text = text_of(render_pdf(job(restricted=True)))
    for want in (
        "Discovery Workshop",
        "AB12CD34",
        "Version 3",
        "Avery Tan",
        "Jordan Lee",
        "2026-11-20",
        "Printed by Pat Example on 2026-11-25",
        "brand story",
        "the voice method",
        "Book the room",
        "Intake",
        "RESTRICTED",
    ):
        assert want in text, want
    assert "private Obsidian comment" not in text and "status: published" not in text
    assert "RESTRICTED" not in text_of(render_pdf(job(restricted=False)))
