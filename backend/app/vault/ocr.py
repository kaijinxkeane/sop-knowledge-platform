"""Local OCR for text inside images (plan §3.1): scanned PDFs, pictures on slides
(Canva exports often turn text into images), images in Word files, and image
files on their own.

RapidOCR runs on the CPU with ONNX models shipped inside the package, so nothing
is downloaded and nothing leaves the machine. The engine loads once per process
(about 7 s) and only when a file actually holds an image. Text found this way
goes through the same labels, safeguards and name detector as any other text.
Failures return "" and log nothing about the image.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

MIN_SIDE = 48  # icons and bullets: nothing to read
MAX_PIXELS = 40_000_000  # refuse decompression bombs
MAX_SIDE = 2400  # larger images are scaled down first

_engine = None
_lock = threading.Lock()


@dataclass(frozen=True)
class OcrSettings:
    enabled: bool = True
    min_confidence: float = 0.6
    max_images: int = 60  # per file


def settings() -> OcrSettings:
    from app.vault.labels import vault_config

    return vault_config().ocr


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def _prepare(data: bytes) -> bytes | None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
            if min(w, h) < MIN_SIDE or w * h > MAX_PIXELS:
                return None
            img = img.convert("RGB")
            if max(w, h) > MAX_SIDE:
                scale = MAX_SIDE / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)))
            out = io.BytesIO()
            img.save(out, "PNG")
            return out.getvalue()
    except Exception:  # noqa: BLE001 - not an image we can read
        return None


def _lines(result, min_conf: float) -> list[str]:
    """Boxes on the same line are joined left to right, lines top to bottom."""
    boxes = []
    for box, text, conf in result or []:
        if float(conf) < min_conf or not str(text).strip():
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append((min(ys), max(ys), min(xs), str(text).strip()))
    boxes.sort()
    lines: list[list[tuple]] = []
    for b in boxes:
        if lines:
            top, bottom = lines[-1][0][0], lines[-1][0][1]
            overlap = min(bottom, b[1]) - max(top, b[0])
            if overlap > 0.5 * min(bottom - top, b[1] - b[0]):
                lines[-1].append(b)
                continue
        lines.append([b])
    return [" ".join(t for *_, t in sorted(line, key=lambda x: x[2])) for line in lines]


def read_image(data: bytes, cfg: OcrSettings | None = None) -> str:
    cfg = cfg or settings()
    if not cfg.enabled:
        return ""
    png = _prepare(data)
    if png is None:
        return ""
    try:
        with _lock:
            result, _ = _get_engine()(png)
    except Exception:  # noqa: BLE001 - OCR must never stop indexing
        log.warning("ocr_failed")
        return ""
    return "\n".join(_lines(result, cfg.min_confidence))


class ImageReader:
    """OCR for one file: skips repeated images (logos) and stops at max_images."""

    def __init__(self, cfg: OcrSettings | None = None):
        self.cfg = cfg or settings()
        self.seen: set[str] = set()
        self.count = 0

    def __call__(self, data: bytes) -> str:
        if not self.cfg.enabled or self.count >= self.cfg.max_images:
            return ""
        digest = hashlib.sha256(data).hexdigest()
        if digest in self.seen:
            return ""
        self.seen.add(digest)
        self.count += 1
        return read_image(data, self.cfg)
