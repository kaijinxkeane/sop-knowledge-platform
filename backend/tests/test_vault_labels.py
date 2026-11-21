"""Rule-based labels: zero over-exposure on the demo vault, fail-closed defaults."""

import pytest
import yaml

from app.policy.engine import Sensitivity
from app.vault.labels import load_vault_config, resolve_labels, safeguard_hits
from app.vault.parse import is_supported, parse_file
from tests.conftest import REPO_ROOT

VAULT = REPO_ROOT / "demo-vault"
TRUTH = yaml.safe_load((REPO_ROOT / "demo-vault-labels.yaml").read_text())
ALL = {**TRUTH["notes"], **TRUTH["attachments"]}
CFG = load_vault_config()
SPACES = {"core", "it", "hr"}


def labels_for(rel):
    d = parse_file(rel, (VAULT / rel).read_bytes())
    text = "\n".join([d.title, *(c.text for c in d.chunks)])
    return resolve_labels(
        rel,
        d.frontmatter,
        text,
        known_spaces=SPACES,
        config=CFG,
        frontmatter_error=d.frontmatter_error,
    )


@pytest.mark.parametrize("rel", sorted(ALL))
def test_never_looser_than_ground_truth(rel):
    truth = ALL[rel]
    got = labels_for(rel)
    if not got.assigned:
        return  # quarantined: safe (only the review queue sees it)
    assert got.space == truth["space"]
    assert got.sensitivity >= Sensitivity[truth["sensitivity"].upper()], rel


def test_unsorted_inbox_is_quarantined_and_pii_detected():
    meeting = labels_for("Inbox/meeting notes 2026-10-14.md")
    assert not meeting.assigned and meeting.rows() == []
    assert {"email", "phone"} <= set(meeting.safeguards)


def test_frontmatter_beats_folder_rule():
    got = labels_for("IT/Booking AV Equipment.md")  # IT/ is internal; the note says public
    assert (got.space, got.sensitivity, got.source) == ("it", Sensitivity.PUBLIC, "frontmatter")


@pytest.mark.parametrize(
    "fm",
    [
        {"sensitivity": "Public"},
        {"sensitivity": "pubic"},
        {"sensitivity": None},
        {"sensitivity": ["public"]},
    ],
)
def test_bad_frontmatter_sensitivity_is_restricted(fm):
    got = resolve_labels("Public/x.md", fm, "", known_spaces=SPACES, config=CFG)
    assert got.sensitivity is Sensitivity.RESTRICTED


def test_unparseable_frontmatter_is_restricted_even_in_public_folder():
    got = resolve_labels(
        "Public/x.md", {}, "", known_spaces=SPACES, config=CFG, frontmatter_error=True
    )
    assert got.sensitivity is Sensitivity.RESTRICTED


def test_unknown_space_in_frontmatter_is_ignored():
    got = resolve_labels(
        "Inbox/x.md",
        {"space": "finance", "sensitivity": "public"},
        "",
        known_spaces=SPACES,
        config=CFG,
    )
    assert not got.assigned


def test_safeguards_force_restricted_over_everything():
    got = resolve_labels(
        "Public/x.md",
        {"sensitivity": "public"},
        "Call Jamie on +65 8000 0000",
        known_spaces=SPACES,
        config=CFG,
    )
    assert got.sensitivity is Sensitivity.RESTRICTED and "phone" in got.safeguards


def test_shared_with_never_looser_than_owner():
    got = resolve_labels(
        "HR/x.md",
        {"sensitivity": "internal", "shared_with": ["core:public"]},
        "",
        known_spaces=SPACES,
        config=CFG,
    )
    assert got.rows() == [("hr", "owner", "internal"), ("core", "shared", "internal")]


@pytest.mark.parametrize(
    "text,hit",
    [
        ("email me at a.b@example.com", "email"),
        ("phone +65 9123 4567", "phone"),
        ("NRIC S1234567D on file", "nric"),
        ("see the rate card", "term:rate card"),
    ],
)
def test_safeguard_patterns(text, hit):
    assert hit in safeguard_hits(text, CFG.flagged_terms)


@pytest.mark.parametrize(
    "text",
    ["Workshop starts 09:00", "Fee 8,800", "Version 1.3", "Seats 12; book 30 minutes before"],
)
def test_safeguards_do_not_fire_on_ordinary_numbers(text):
    assert safeguard_hits(text, CFG.flagged_terms) == []


@pytest.mark.parametrize(
    "path,ignored",
    [
        (".obsidian/app.json", True),
        ("_templates/SOP.md", True),
        ("HR/.DS_Store", True),
        (".git/config", True),
        ("HR/Leave Policy.md", False),
    ],
)
def test_ignored_paths(path, ignored):
    assert CFG.is_ignored(path) is ignored or not is_supported(path)
