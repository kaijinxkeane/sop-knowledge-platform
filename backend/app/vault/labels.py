"""Which space and sensitivity a file gets, before any AI (plan §4.1).

Order of authority (highest first):
  1. labels in the note's own frontmatter (`space:`, `sensitivity:`, `shared_with:`)
  2. folder rules in config/vault.yaml
  3. (Phase 2b) AI proposals approved by a human
  4. deterministic safeguards: personal data or flagged terms force `restricted`
  5. default: `restricted` and unassigned (quarantined: nobody can read it yet)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings
from app.policy.engine import Sensitivity, resolve_sensitivity

_PATTERNS = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "phone": re.compile(r"(?:\+\d{1,3}[\s-]?)\d{4}[\s-]?\d{4}\b|\b[689]\d{3}[\s-]\d{4}\b"),
    "nric": re.compile(r"\b[STFGM]\d{7}[A-Z]\b"),
    "bank_account": re.compile(r"\b\d{3}-\d{5,6}-\d{1,3}\b"),
}


@dataclass(frozen=True)
class FolderRule:
    path: str
    space: str
    sensitivity: str | None


@dataclass(frozen=True)
class VaultConfig:
    ignore: tuple[str, ...]
    stages: tuple[str, ...]
    attachments_folder: str
    folder_rules: tuple[FolderRule, ...]
    flagged_terms: tuple[str, ...]

    def is_ignored(self, path: str) -> bool:
        if any(seg.startswith(".") for seg in path.split("/")):
            return True  # hidden files and folders (.git, .obsidian, .DS_Store, ...)
        return any(path.startswith(p) or path == p.rstrip("/") for p in self.ignore)

    def rule_for(self, path: str) -> FolderRule | None:
        matches = [r for r in self.folder_rules if path.startswith(r.path)]
        return max(matches, key=lambda r: len(r.path)) if matches else None


def load_vault_config(config_dir: Path | None = None) -> VaultConfig:
    data = yaml.safe_load(((config_dir or get_settings().config_dir) / "vault.yaml").read_text())
    rules = []
    for r in data.get("folder_rules") or []:
        sens = r.get("sensitivity")
        if sens is not None and resolve_sensitivity(sens).label != sens:
            raise ValueError(f"folder rule {r['path']!r}: unknown sensitivity {sens!r}")
        rules.append(FolderRule(path=r["path"], space=r["space"], sensitivity=sens))
    return VaultConfig(
        ignore=tuple(data.get("ignore") or ()),
        stages=tuple(data.get("stages") or ()),
        attachments_folder=str(data.get("attachments_folder") or "Attachments").strip("/"),
        folder_rules=tuple(rules),
        flagged_terms=tuple(t.lower() for t in data.get("flagged_terms") or ()),
    )


@lru_cache(maxsize=1)
def vault_config() -> VaultConfig:
    return load_vault_config()


@dataclass
class Labels:
    space: str | None
    sensitivity: Sensitivity
    shared_with: list[tuple[str, Sensitivity]] = field(default_factory=list)
    source: str = "default"  # frontmatter | folder_rule | default
    safeguards: list[str] = field(default_factory=list)

    @property
    def assigned(self) -> bool:
        return self.space is not None

    def rows(self) -> list[tuple[str, str, str]]:
        """(space, role, sensitivity) rows for document_access."""
        if self.space is None:
            return []
        rows = [(self.space, "owner", self.sensitivity.label)]
        rows += [(s, "shared", lvl.label) for s, lvl in self.shared_with if s != self.space]
        return rows


def safeguard_hits(text: str, flagged_terms: tuple[str, ...]) -> list[str]:
    hits = [name for name, rx in _PATTERNS.items() if rx.search(text)]
    lower = text.lower()
    hits += [f"term:{t}" for t in flagged_terms if t in lower]
    return hits


def resolve_labels(
    path: str,
    frontmatter: dict,
    text: str,
    *,
    known_spaces: set[str],
    config: VaultConfig,
    frontmatter_error: bool = False,
) -> Labels:
    rule = config.rule_for(path)
    source = "default"

    space = None
    fm_space = frontmatter.get("space")
    if isinstance(fm_space, str) and fm_space.strip() in known_spaces:
        space, source = fm_space.strip(), "frontmatter"
    elif rule is not None and rule.space in known_spaces:
        space, source = rule.space, "folder_rule"

    if frontmatter_error:
        sensitivity = Sensitivity.RESTRICTED
    elif "sensitivity" in frontmatter:
        sensitivity = resolve_sensitivity(frontmatter.get("sensitivity"))  # typos -> restricted
        source = "frontmatter" if space is not None else source
    elif rule is not None and rule.sensitivity is not None and space == rule.space:
        sensitivity = Sensitivity[rule.sensitivity.upper()]
    else:
        sensitivity = Sensitivity.RESTRICTED

    shared: list[tuple[str, Sensitivity]] = []
    raw_shared = frontmatter.get("shared_with")
    if isinstance(raw_shared, list):
        for item in raw_shared:
            # "hr" (at the note's own sensitivity) or "hr:internal"
            name, _, level = str(item).partition(":")
            if name.strip() in known_spaces:
                lvl = resolve_sensitivity(level.strip()) if level else sensitivity
                shared.append((name.strip(), max(lvl, sensitivity)))

    hits = safeguard_hits(text, config.flagged_terms)
    if hits:
        sensitivity = Sensitivity.RESTRICTED
        shared = [(s, Sensitivity.RESTRICTED) for s, _ in shared]
    return Labels(
        space=space, sensitivity=sensitivity, shared_with=shared, source=source, safeguards=hits
    )
