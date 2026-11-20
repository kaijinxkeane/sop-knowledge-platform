"""Generate the demo vault's binary training content (fictional data only).

    uv run python scripts/generate_demo_assets.py

Writes into demo-vault/Training Content/Attachments/:
- Brand Foundations.pptx   (18 slides with speaker notes; slide 14 cited by the SOPs)
- Executive Presence.pptx  (9 slides with speaker notes)
- Values Card Sort Worksheet.pdf  (fillable form fields)
- Brand Audit Worksheet.pdf       (fillable form fields)
Output is deterministic so regenerating does not create noisy diffs in content.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[2] / "demo-vault" / "Training Content" / "Attachments"

BRAND_FOUNDATIONS = [
    (
        "Welcome to Brand Foundations",
        "Signature Personal Brand Programme · Discovery",
        "Welcome everyone, introduce yourself and the assistant. Keep the opening warm and brief.",
    ),
    (
        "Today's agenda",
        "Opening · Values card sort · Brand gap discussion · Close",
        "Walk through the agenda and the 3-hour timing. Point out the break after the card sort.",
    ),
    (
        "Ground rules",
        "Curiosity over judgment · Phones away · What's shared here stays here",
        "Ask the group to add one ground rule of their own.",
    ),
    (
        "The 3-minute brand story",
        "Tell us about a moment you were proud of your work",
        "Each participant gets 3 minutes. The assistant writes recurring words on the whiteboard.",
    ),
    (
        "What a personal brand is",
        "The reputation you earn when you are not in the room",
        "Use one personal story here; avoid celebrity examples.",
    ),
    (
        "What it is not",
        "Not a logo · Not self-promotion · Not a persona",
        "Address the common worry that personal branding means bragging.",
    ),
    (
        "Reputation has three sources",
        "How you see yourself · How others see you · What you have done",
        "These three sources come back in the Brand Pillars Framework later in the programme.",
    ),
    (
        "Why it matters at work",
        "Opportunities follow clarity",
        "Invite one participant to share a time a clear reputation helped them.",
    ),
    (
        "Values come first",
        "Brands built on values last longer than brands built on tactics",
        "Transition into the values card sort.",
    ),
    (
        "Values card sort: instructions",
        "Pairs · 40 cards · Always me / Sometimes me / Not me",
        "Hand out one worksheet per participant. 15 minutes per person.",
    ),
    (
        "Choosing your top five",
        "Explain each choice to your partner in one sentence",
        "Partners should ask 'where would a colleague see this?'",
    ),
    (
        "Debrief",
        "What surprised you?",
        "Group debrief, 15 minutes. Capture themes on the whiteboard.",
    ),
    ("Break", "10 minutes", "Reset the room for the brand gap discussion."),
    (
        "Opening the brand gap discussion",
        "Self-view vs colleague view",
        "Ask each participant to read their colleagues' intake answers silently first. "
        "Then ask: which answer surprised you most, and why? Keep the tone exploratory.",
    ),
    (
        "Spotting gaps",
        "Where the two views differ, there is a story to understand",
        "Gaps are information, not failures. Normalise this explicitly.",
    ),
    ("Closing the gap", "Behaviours people can see", "Pause here for questions before moving on."),
    (
        "One action for two weeks",
        "Small, visible, repeatable",
        "Each participant writes one action on a card and shares it with their partner.",
    ),
    (
        "Next: Brand Pillars",
        "Strategy session in 2-3 weeks",
        "Book the Strategy session before people leave the room.",
    ),
]

EXECUTIVE_PRESENCE = [
    ("Executive Presence Workshop", "Full-day programme", "Welcome; collect camera consent forms."),
    (
        "What presence is",
        "Gravitas · Communication · Appearance",
        "Ask for a leader they admire and what they notice first.",
    ),
    ("Gravitas", "Calm under pressure", "Short story about a board meeting that went wrong."),
    ("Communication", "Pace, pause, pitch", "Demonstrate the 2-second pause."),
    ("Appearance", "Fit for the room", "Keep this light; link to the dress code."),
    (
        "Voice and pace drill",
        "Pairs · 2-minute talk · record on phone",
        "Each person records once, then listens back privately.",
    ),
    (
        "On camera",
        "One camera, one light, three takes",
        "Camera-shy participants may do their first take audio-only.",
    ),
    ("Feedback format", "Keep / Try", "No other feedback format is allowed in the room."),
    ("Your commitment", "One behaviour for the next 30 days", "Hand out commitment cards."),
]


def build_deck(path: Path, slides: list[tuple[str, str, str]]) -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    layout = prs.slide_layouts[1]
    for title, body, notes in slides:
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
        for paragraph in slide.placeholders[1].text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(28)
        slide.notes_slide.notes_text_frame.text = notes
    prs.core_properties.title = path.stem
    prs.core_properties.author = "Demo Training Co. (fictional)"
    prs.save(path)


def build_worksheet(path: Path, title: str, intro: str, fields: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle(title)
    c.setAuthor("Demo Training Co. (fictional)")
    width, height = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawString(56, height - 72, title)
    c.setFont("Helvetica", 11)
    c.drawString(56, height - 96, intro)
    y = height - 140
    form = c.acroForm
    for i, label in enumerate(fields):
        c.drawString(56, y, label)
        form.textfield(
            name=f"field_{i + 1}",
            tooltip=label,
            x=56,
            y=y - 30,
            width=width - 112,
            height=22,
            borderWidth=1,
            forceBorder=True,
        )
        y -= 70
    c.showPage()
    c.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    build_deck(OUT / "Brand Foundations.pptx", BRAND_FOUNDATIONS)
    build_deck(OUT / "Executive Presence.pptx", EXECUTIVE_PRESENCE)
    build_worksheet(
        OUT / "Values Card Sort Worksheet.pdf",
        "Values Card Sort Worksheet",
        "Sort the 40 value cards, then record your top five and one sentence for each.",
        [f"Top value {n}: and where would a colleague see it?" for n in range(1, 6)]
        + ["One action for the next two weeks"],
    )
    build_worksheet(
        OUT / "Brand Audit Worksheet.pdf",
        "Brand Audit Worksheet",
        "Compare how you see yourself with how colleagues described you in the intake.",
        [
            "Three words I use to describe myself",
            "Three words colleagues used",
            "The biggest gap I noticed",
            "A story that explains the gap",
        ],
    )
    for f in sorted(OUT.iterdir()):
        print(f"{f.name}: {f.stat().st_size} bytes")


if __name__ == "__main__":
    main()
