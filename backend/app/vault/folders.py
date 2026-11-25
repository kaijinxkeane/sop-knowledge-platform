"""Which department a vault folder belongs to (Library folders, the sorter).

A folder belongs to the department whose folder rule covers it (longest match,
config/vault.yaml plus departments created in the app). Some folders keep their
own rules and are never arranged from the Library: handovers and projects
(per-person and per-project access) and the built-in Help. Inbox and Drafts
hold notes on their way somewhere: documents can leave them, never be moved in.
"""

from __future__ import annotations

from app.vault.labels import VaultConfig

ARRIVALS = ("Inbox", "Drafts")


def _sealed(config: VaultConfig) -> tuple[str, ...]:
    return (config.handover_folder, config.project_folder, "Help")


def _under(folder: str, roots: tuple[str, ...]) -> bool:
    return any(folder == r or folder.startswith(r + "/") for r in roots)


def department_of(folder: str, config: VaultConfig) -> str | None:
    """The department of a folder documents may be filed in, or None."""
    if not folder or _under(folder, _sealed(config) + ARRIVALS):
        return None
    rule = config.rule_for(folder + "/")
    return rule.space if rule else None


def may_leave(folder: str, config: VaultConfig) -> bool:
    """Documents in this folder may be moved from the Library."""
    return not _under(folder, _sealed(config))
