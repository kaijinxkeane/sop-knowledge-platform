"""Department profiles from config/spaces/*.yaml (plan §5, "Department agent
configuration"): what each space covers, who to contact, and agent rules.
A new department is a new YAML file, no code change.

Departments created in the app (Admin → Departments) are YAML files of the
same shape in `settings.spaces_dir`. They never override a configured one, and
every process picks them up when that folder changes (no restart)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings


@dataclass(frozen=True)
class SpaceProfile:
    name: str
    title: str
    description: str
    contact: str
    persona: str = ""
    rules: tuple[str, ...] = field(default_factory=tuple)
    local_only: bool = False
    pdf_export: bool = True  # leads can turn PDF export off for the whole space


def space_files(
    config_dir: Path | None = None, extra_dir: Path | None = None
) -> list[tuple[str, dict]]:
    """(name, settings) for every department: configured ones first, then those
    created in the app. A name is used once; the configured file wins."""
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    settings = get_settings()
    folders = [(config_dir or settings.config_dir) / "spaces", extra_dir or settings.spaces_dir]
    for i, folder in enumerate(folders):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            name = str(raw.get("name") or path.stem)
            if name in seen:
                continue
            seen.add(name)
            out.append((name, {**raw, "created_in_app": i == 1}))
    return out


def spaces_stamp() -> tuple:
    """Changes whenever a department is created in the app (cache key)."""
    folder = get_settings().spaces_dir
    if not folder.is_dir():
        return ()
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in folder.glob("*.yaml")))


def load_space_profiles(config_dir: Path | None = None) -> dict[str, SpaceProfile]:
    out = {}
    for name, raw in space_files(config_dir):
        agent = raw.get("agent") or {}
        out[name] = SpaceProfile(
            name=name,
            title=str(raw.get("title") or name),
            description=" ".join(str(raw.get("description") or raw.get("title") or name).split()),
            contact=str(raw.get("contact") or "Please ask your manager."),
            persona=" ".join(str(agent.get("persona") or "").split()),
            rules=tuple(str(r) for r in agent.get("rules") or ()),
            local_only=bool(raw.get("local_only", False)),
            pdf_export=raw.get("pdf_export", True) is not False,
        )
    return out


@lru_cache(maxsize=4)
def _profiles(_stamp: tuple) -> dict[str, SpaceProfile]:
    return load_space_profiles()


def space_profiles() -> dict[str, SpaceProfile]:
    return _profiles(spaces_stamp())
