"""Slide pictures: rendered once per deck version, served only to readers."""

from __future__ import annotations

import pytest

from app.vault import slides
from tests.db.test_governance import API, STAFF, doc_id

DECK = "Training Content/Attachments/Brand Foundations.pptx"
PNG = b"\\x89PNG\\r\\n\\x1a\\nfake"


@pytest.fixture
def fake_render(monkeypatch, tmp_path):
    """Stand in for LibreOffice: count renders, write two fake slides."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "cache_dir", tmp_path)
    calls = []

    def render(data, out):
        calls.append(len(data))
        out.mkdir(parents=True)
        for n in (1, 2):
            (out / f"{n}.png").write_bytes(PNG)
        (out / "count").write_text("2")
        return 2

    monkeypatch.setattr(slides, "_render_sync", render)
    return calls


async def test_slide_pictures_are_cached_and_checked(
    indexed, sessions, client, make_user, sign_in, fake_render
):
    hs = await sign_in(await make_user(roles=STAFF))
    deck = await doc_id(sessions, DECK)
    r = await client.get(f"{API}/documents/{deck}/slides/1", headers=hs)
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, no-store"
    await client.get(f"{API}/documents/{deck}/slides/2", headers=hs)
    assert len(fake_render) == 1  # rendered once for the whole deck
    assert (await client.get(f"{API}/documents/{deck}/slides/3", headers=hs)).status_code == 404
    # Someone without access: 404, and nothing is rendered for them.
    nobody = await sign_in(await make_user(roles=("employee",)))
    assert (await client.get(f"{API}/documents/{deck}/slides/1", headers=nobody)).status_code == 404
    slides.forget_all()
    assert slides.cached_count(b"anything") is None


async def test_no_libreoffice_is_a_503(
    indexed, sessions, client, make_user, sign_in, monkeypatch, tmp_path
):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "cache_dir", tmp_path)
    monkeypatch.setattr(slides, "soffice", lambda: None)
    hs = await sign_in(await make_user(roles=STAFF))
    deck = await doc_id(sessions, DECK)
    assert (await client.get(f"{API}/documents/{deck}/slides/1", headers=hs)).status_code == 503
