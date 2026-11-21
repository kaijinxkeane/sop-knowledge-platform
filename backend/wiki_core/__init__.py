"""Deterministic llm-wiki helpers for the platform.

The canonical implementation is the single-file CLI at ``scripts/llm-wiki``
(also bundled into ``claude-plugin/bin/llm-wiki``, with its own test suite).
Rather than fork it, this package loads that file as a module and re-exports the
helpers the platform uses, so there is exactly one copy of the logic.

Locating the script, in order:
1. ``$LLM_WIKI_SCRIPT``
2. ``<repo>/scripts/llm-wiki`` (development checkout)
3. ``/app/vendor/llm-wiki`` (container image)
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "scripts" / "llm-wiki",
    Path("/app/vendor/llm-wiki"),
]


def _locate() -> Path:
    override = os.environ.get("LLM_WIKI_SCRIPT")
    paths = ([Path(override)] if override else []) + _CANDIDATES
    for path in paths:
        if path.is_file():
            return path
    raise ImportError(f"llm-wiki script not found; looked in: {', '.join(map(str, paths))}")


def _load() -> ModuleType:
    path = _locate()
    loader = importlib.machinery.SourceFileLoader("_llm_wiki_cli", str(path))
    spec = importlib.util.spec_from_loader("_llm_wiki_cli", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_llm_wiki_cli"] = module  # needed for dataclasses in the module
    loader.exec_module(module)
    return module


_cli = _load()

SCRIPT_PATH: Path = Path(_cli.__file__)

# Frontmatter and link helpers (llm-wiki's minimal, dependency-free parser).
split_markdown_frontmatter = _cli.split_markdown_frontmatter
parse_frontmatter_block = _cli.parse_frontmatter_block
extract_markdown_links = _cli.extract_markdown_links
wikilink_slug = _cli.wikilink_slug
slugify = _cli.slugify
parse_date = _cli.parse_date

# Retract helpers: the value plus its common encodings, and the file scanner.
retract_patterns = _cli.retract_patterns
scan_retract_roots = _cli.scan_retract_roots

# Full CLI entry point (lint, retract, ...), for jobs that shell out in-process.
cli_main = _cli.main

__all__ = [
    "SCRIPT_PATH",
    "cli_main",
    "extract_markdown_links",
    "parse_date",
    "parse_frontmatter_block",
    "retract_patterns",
    "scan_retract_roots",
    "slugify",
    "split_markdown_frontmatter",
    "wikilink_slug",
]
