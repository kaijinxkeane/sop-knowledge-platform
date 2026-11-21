from __future__ import annotations

import os
from pathlib import Path

# A fixed signing key for tests only (never used outside the test run).
os.environ.setdefault("SOP_SECRET_KEY", "test-only-secret-key-" + "x" * 32)

import pytest

from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
