"""The vault's git repository (plan §3.1-3.2).

Every app save is a commit with the signed-in user as author (the platform is
the committer) and an `SOP-User:` trailer, so authorship maps back to a user
id even if names change. Paths are always checked to stay inside the vault.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

PLATFORM_NAME = "SOP Platform"
PLATFORM_EMAIL = "platform@sop.local"
USER_TRAILER = "SOP-User"
UNATTRIBUTED_TRAILER = "SOP-Unattributed"
PLATFORM_TRAILER = "SOP-Platform"  # the platform's own bookkeeping (e.g. approval write-back)


class VaultPathError(ValueError):
    pass


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    user_id: uuid.UUID | None
    unattributed: bool
    platform: bool = False


class GitVault:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    # --- paths ---------------------------------------------------------------

    def safe_path(self, rel: str) -> Path:
        rel = (rel or "").replace("\\", "/").strip()
        pure = PurePosixPath(rel)
        if (
            not rel
            or pure.is_absolute()
            or ".." in pure.parts
            or any(part.startswith(".") for part in pure.parts)
        ):
            raise VaultPathError("invalid vault path")
        full = (self.root / pure).resolve()
        if self.root not in full.parents:
            raise VaultPathError("path escapes the vault")
        return full

    # --- git plumbing ----------------------------------------------------------

    def _git(self, *args: str, check: bool = True, input: bytes | None = None) -> str:
        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "GIT_COMMITTER_NAME": PLATFORM_NAME,
            "GIT_COMMITTER_EMAIL": PLATFORM_EMAIL,
        }
        proc = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self.root}",
                "-c",
                "core.quotepath=off",
                "-C",
                str(self.root),
                *args,
            ],
            capture_output=True,
            input=input,
            env=env,
            timeout=60,
        )
        if check and proc.returncode != 0:
            raise GitError(f"git {args[0]} failed ({proc.returncode})")
        return proc.stdout.decode("utf-8", errors="replace")

    @contextmanager
    def lock(self):
        """Serialise writes from the API and the worker."""
        lock_path = self.root / ".git" / "sop-platform.lock"
        with open(lock_path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def is_repo(self) -> bool:
        return (self.root / ".git").exists()

    def head(self) -> str | None:
        out = self._git("rev-parse", "--verify", "-q", "HEAD", check=False).strip()
        return out or None

    def tracked_files(self) -> list[str]:
        return [p for p in self._git("ls-files", "-z").split("\0") if p]

    def changed_since(self, commit: str | None) -> tuple[list[str], list[str]]:
        """(changed or added paths, deleted paths) between `commit` and HEAD."""
        head = self.head()
        if head is None:
            return [], []
        if commit is None:
            return self.tracked_files(), []
        if commit == head:
            return [], []
        changed, deleted = [], []
        out = self._git("diff", "--name-status", "--no-renames", "-z", commit, head)
        fields = [f for f in out.split("\0") if f]
        for status, path in zip(fields[::2], fields[1::2], strict=False):
            (deleted if status.startswith("D") else changed).append(path)
        return changed, deleted

    def uncommitted(self) -> list[str]:
        out = self._git("status", "--porcelain", "-z", "--untracked-files=all")
        return [entry[3:] for entry in out.split("\0") if len(entry) > 3]

    def last_commit(self, rel: str) -> CommitInfo | None:
        fmt = "%H%x1f%an%x1f%ae%x1f%cI%x1f%B%x1e"
        out = self._git("log", "-1", f"--format={fmt}", "--", rel, check=False)
        return _parse_log(out)[0] if out.strip() else None

    def history(self, rel: str, limit: int = 50) -> list[CommitInfo]:
        fmt = "%H%x1f%an%x1f%ae%x1f%cI%x1f%B%x1e"
        return _parse_log(self._git("log", f"-{limit}", f"--format={fmt}", "--", rel, check=False))

    def show(self, rel: str, commit: str) -> bytes:
        """The file at `commit`. A file moved since (Library → Move) is found
        under the name it had then, so past versions keep working."""
        out = self._show(rel, commit)
        if out is None:
            old = self.path_at(rel, commit)
            if old and old != rel:
                out = self._show(old, commit)
        if out is None:
            raise GitError("version not found")
        return out

    def path_at(self, rel: str, commit: str) -> str | None:
        """The name the file now at `rel` had at `commit`, following moves."""
        log = self._git(
            "log", "--follow", "--format=%x1e%H", "--name-only", "HEAD", "--", rel, check=False
        )
        ancestors = set(self._git("rev-list", commit, check=False).split())
        if not ancestors:
            return None
        for block in log.split("\x1e"):
            lines = [x for x in block.strip().splitlines() if x.strip()]
            if len(lines) >= 2 and lines[0] in ancestors:
                return lines[-1].strip()
        return None

    def move(self, old: str, new: str) -> None:
        """Move a file inside the vault (the caller commits both paths)."""
        src, dst = self.safe_path(old), self.safe_path(new)
        if not src.is_file():
            raise VaultPathError("nothing to move")
        if dst.exists():
            raise VaultPathError("a file with that name is already there")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        try:
            src.parent.rmdir()  # leave no empty folder behind (git doesn't track them)
        except OSError:
            pass

    def _show(self, rel: str, commit: str) -> bytes | None:
        proc = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self.root}",
                "-C",
                str(self.root),
                "show",
                f"{commit}:{rel}",
            ],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout

    def commit(
        self,
        paths: list[str],
        message: str,
        *,
        author_name: str,
        author_email: str,
        user_id: uuid.UUID | None = None,
        unattributed: bool = False,
        platform: bool = False,
    ) -> str:
        trailers = []
        if platform:
            trailers.append(f"{PLATFORM_TRAILER}: true")
        if user_id is not None:
            trailers.append(f"{USER_TRAILER}: {user_id}")
        if unattributed:
            trailers.append(f"{UNATTRIBUTED_TRAILER}: true")
        full = message.strip() + ("\n\n" + "\n".join(trailers) if trailers else "") + "\n"
        self._git("add", "-A", "--", *paths)
        author = f"{_clean(author_name)} <{_clean(author_email)}>"
        self._git(
            "commit",
            "-q",
            "--no-verify",
            f"--author={author}",
            "-F",
            "-",
            "--",
            *paths,
            input=full.encode(),
        )
        return self.head() or ""


def _clean(value: str) -> str:
    return "".join(ch for ch in value if ch not in "<>\n\r").strip() or "unknown"


def _parse_log(out: str) -> list[CommitInfo]:
    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, name, email, when, body = record.split("\x1f", 4)
        user_id, unattributed, platform = None, False, False
        for line in body.splitlines():
            key, _, value = line.partition(":")
            if key.strip() == USER_TRAILER:
                try:
                    user_id = uuid.UUID(value.strip())
                except ValueError:
                    pass
            elif key.strip() == UNATTRIBUTED_TRAILER:
                unattributed = True
            elif key.strip() == PLATFORM_TRAILER:
                platform = True
        commits.append(
            CommitInfo(
                sha=sha.strip(),
                author_name=name,
                author_email=email,
                committed_at=datetime.fromisoformat(when.strip()),
                user_id=user_id,
                unattributed=unattributed,
                platform=platform,
            )
        )
    return commits
