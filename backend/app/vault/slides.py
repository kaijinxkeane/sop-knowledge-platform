"""Slide pictures for decks: headless LibreOffice -> PDF -> one PNG per slide.

Rendered once per deck *content* (keyed by its SHA-256, so a version never
renders twice) into the cache directory shared by the API and the worker.
Callers check access before asking; the cache is never served directly.
Retractions clear the whole cache (`forget_all`).

Nothing here reads the deck's text or sends it anywhere: LibreOffice runs
locally with networking off, in a throwaway profile.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import get_settings

log = logging.getLogger("sop.slides")

WIDTH = 1600  # pixels; slides are 16:9 or 4:3
TIMEOUT = 180  # seconds for one deck
MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
_locks: dict[str, asyncio.Lock] = {}


class SlidesUnavailable(Exception):
    """LibreOffice isn't installed, or the deck couldn't be converted."""


def soffice() -> str | None:
    configured = get_settings().soffice_path
    for candidate in (
        configured,
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        MAC_SOFFICE,
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def cache_root() -> Path:
    return get_settings().cache_dir / "slides"


def _dir_for(data: bytes) -> Path:
    return cache_root() / hashlib.sha256(data).hexdigest()


def cached_count(data: bytes) -> int | None:
    """Number of rendered slides, or None if this version isn't rendered yet."""
    done = _dir_for(data) / "count"
    try:
        return int(done.read_text())
    except (OSError, ValueError):
        return None


def _render_sync(data: bytes, out: Path) -> int:
    exe = soffice()
    if exe is None:
        raise SlidesUnavailable("LibreOffice is not installed")
    import pypdfium2 as pdfium

    with tempfile.TemporaryDirectory(prefix="sop-slides-") as tmp:
        src = Path(tmp) / "deck.pptx"
        src.write_bytes(data)
        profile = Path(tmp) / "profile"
        cmd = [
            exe,
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--convert-to",
            "pdf",
            "--outdir",
            tmp,
            str(src),
        ]
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR")}
        env["HOME"] = tmp
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=TIMEOUT,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise SlidesUnavailable(type(exc).__name__) from None
        pdf_path = Path(tmp) / "deck.pdf"
        if not pdf_path.exists():
            raise SlidesUnavailable("conversion produced no file")
        staging = out.with_name(out.name + ".tmp")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            for i, page in enumerate(pdf, start=1):
                scale = WIDTH / page.get_width()
                page.render(scale=scale).to_pil().save(staging / f"{i}.png", optimize=True)
            n = len(pdf)
        finally:
            pdf.close()
        (staging / "count").write_text(str(n))
        shutil.rmtree(out, ignore_errors=True)
        staging.rename(out)
        return n


async def ensure_rendered(data: bytes) -> int:
    """Render this deck version if it isn't cached yet; returns its slide count."""
    n = cached_count(data)
    if n is not None:
        return n
    out = _dir_for(data)
    lock = _locks.setdefault(out.name, asyncio.Lock())
    async with lock:
        n = cached_count(data)
        if n is None:
            n = await asyncio.to_thread(_render_sync, data, out)
            log.info("slides_rendered", extra={"fields": {"slides": n}})
    return n


async def slide_png(data: bytes, number: int) -> bytes | None:
    n = await ensure_rendered(data)
    if not 1 <= number <= n:
        return None
    return (_dir_for(data) / f"{number}.png").read_bytes()


def forget_all() -> None:
    """Drop every cached picture (after a retraction)."""
    shutil.rmtree(cache_root(), ignore_errors=True)
