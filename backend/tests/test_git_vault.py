"""Git layer: path safety, authorship trailers, change detection."""

import subprocess
import uuid

import pytest

from app.vault.git import GitVault, VaultPathError


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "a.md").write_text("# A\n")
    g = GitVault(tmp_path)
    g.commit(["a.md"], "seed", author_name="Admin", author_email="admin@example.com")
    return g


@pytest.mark.parametrize(
    "bad",
    [
        "../etc/passwd",
        "/abs.md",
        ".git/config",
        "a/../../x.md",
        "",
        ".obsidian/app.json",
        "notes/.hidden.md",
    ],
)
def test_paths_cannot_escape_or_touch_hidden_files(repo, bad):
    with pytest.raises(VaultPathError):
        repo.safe_path(bad)


def test_commit_records_author_and_user_trailer(repo):
    uid = uuid.uuid4()
    (repo.root / "b.md").write_text("# B\n")
    sha = repo.commit(
        ["b.md"], "Create b", author_name="Avery <Tan>", author_email="a@x.com", user_id=uid
    )
    info = repo.last_commit("b.md")
    assert info.sha == sha and info.user_id == uid and not info.unattributed
    assert info.author_name == "Avery Tan" and info.author_email == "a@x.com"
    committer = subprocess.run(
        ["git", "-C", str(repo.root), "log", "-1", "--format=%cn"], capture_output=True, text=True
    ).stdout.strip()
    assert committer == "SOP Platform"


def test_changed_since(repo):
    first = repo.head()
    (repo.root / "a.md").write_text("# A2\n")
    (repo.root / "c.md").write_text("# C\n")
    repo.commit(["a.md", "c.md"], "edit", author_name="x", author_email="x@x.com")
    second = repo.head()
    assert repo.changed_since(first) == (["a.md", "c.md"], [])
    (repo.root / "c.md").unlink()
    repo.commit(["c.md"], "delete", author_name="x", author_email="x@x.com")
    assert repo.changed_since(second) == ([], ["c.md"])
    assert repo.changed_since(first) == (["a.md"], [])  # created and deleted in between
    assert repo.changed_since(repo.head()) == ([], [])


def test_uncommitted_and_unattributed(repo):
    (repo.root / "stray.md").write_text("# stray\n")
    assert repo.uncommitted() == ["stray.md"]
    repo.commit(
        ["stray.md"],
        "nightly",
        author_name="SOP Platform",
        author_email="platform@sop.local",
        unattributed=True,
    )
    assert repo.last_commit("stray.md").unattributed and repo.uncommitted() == []
