"""PDF export endpoint: only what you can read, audited, watermarked, switchable per space."""

from __future__ import annotations

import io
import uuid
from dataclasses import replace

from pypdf import PdfReader
from sqlalchemy import select

from app.api import exports
from app.db.models import AuditEvent
from app.spaces import load_space_profiles
from tests.db.test_governance import API, LEAD, SOP, STAFF, doc_id

PILLARS = "Methodology/Brand Pillars Framework.md"  # core restricted


def text_of(r) -> str:
    assert r.headers["content-type"] == "application/pdf", r.text
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)


async def test_export_one_sop_and_a_stage(indexed, sessions, client, make_user, sign_in):
    staff = await make_user(roles=STAFF)
    hs = await sign_in(staff)
    note = await doc_id(sessions, SOP)
    r = await client.post(f"{API}/exports", headers=hs, json={"document_id": str(note)})
    assert r.status_code == 200
    text = text_of(r)
    assert "Discovery Workshop" in text and f"Printed by {staff.user.display_name}" in text
    assert "Version 1" in text and "RESTRICTED" not in text
    async with sessions() as s:
        ev = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "pdf_exported"))
        ).scalar_one()
        assert ev.details == {"documents": [str(note)], "restricted": False}

    docs = (await client.get(f"{API}/documents", headers=hs)).json()
    d = next(x for x in docs if x["id"] == str(note))
    r = await client.post(
        f"{API}/exports", headers=hs, json={"programme": d["programme"], "stage": d["stage"]}
    )
    assert r.status_code == 200 and "Discovery Workshop" in text_of(r)


async def test_restricted_is_watermarked_and_hidden_is_404(
    indexed, sessions, client, make_user, sign_in
):
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    hs, hl = await sign_in(staff), await sign_in(lead)
    pillars = await doc_id(sessions, PILLARS)
    for target in (str(pillars), str(uuid.uuid4())):
        r = await client.post(f"{API}/exports", headers=hs, json={"document_id": target})
        assert r.status_code == 404 and "Pillars" not in r.text
    r = await client.post(f"{API}/exports", headers=hl, json={"document_id": str(pillars)})
    text = text_of(r)
    assert "RESTRICTED" in text and lead.user.display_name in text
    bad = await client.post(f"{API}/exports", headers=hl, json={"programme": "x"})
    assert bad.status_code == 422


async def test_a_space_can_turn_export_off(
    indexed, sessions, client, make_user, sign_in, monkeypatch
):
    profiles = load_space_profiles()
    profiles["core"] = replace(profiles["core"], pdf_export=False)
    monkeypatch.setattr(exports, "space_profiles", lambda: profiles)
    hs = await sign_in(await make_user(roles=STAFF))
    note = await doc_id(sessions, SOP)
    r = await client.post(f"{API}/exports", headers=hs, json={"document_id": str(note)})
    assert r.status_code == 403
