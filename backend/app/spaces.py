"""Department profiles from config/spaces/*.yaml (plan §5, "Department agent
configuration"): what each space covers, who to contact, and agent rules.
A new department is a new YAML file, no code change."""

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


def load_space_profiles(config_dir: Path | None = None) -> dict[str, SpaceProfile]:
    out = {}
    for path in sorted(((config_dir or get_settings().config_dir) / "spaces").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = raw.get("name") or path.stem
        agent = raw.get("agent") or {}
        out[name] = SpaceProfile(
            name=name,
            title=str(raw.get("title") or name),
            description=" ".join(str(raw.get("description") or raw.get("title") or name).split()),
            contact=str(raw.get("contact") or "Please ask your manager."),
            persona=" ".join(str(agent.get("persona") or "").split()),
            rules=tuple(str(r) for r in agent.get("rules") or ()),
            local_only=bool(raw.get("local_only", False)),
        )
    return out


@lru_cache(maxsize=1)
def space_profiles() -> dict[str, SpaceProfile]:
    return load_space_profiles()
