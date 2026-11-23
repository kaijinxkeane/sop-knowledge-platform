"""Policy engine: fail-closed sensitivity, scopes, actions and grant validation."""

import uuid

import pytest

from app.identity import load_roles_config
from app.policy.engine import (
    GrantError,
    GrantRule,
    Principal,
    Sensitivity,
    document_visible,
    resolve_sensitivity,
    validate_grant,
)

PUB, INT, RES = Sensitivity.PUBLIC, Sensitivity.INTERNAL, Sensitivity.RESTRICTED
SPACES = ["core", "it", "hr"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("public", PUB),
        ("internal", INT),
        ("restricted", RES),
        (" public ", PUB),
        (None, RES),
        ("", RES),
        ("Public", RES),
        ("pubic", RES),
        ("secret", RES),
        (0, RES),
        (["public"], RES),
        ({"level": "public"}, RES),
    ],
)
def test_resolve_sensitivity_fails_closed(raw, expected):
    assert resolve_sensitivity(raw) is expected


def principal(*grants: GrantRule) -> Principal:
    return Principal(uuid.uuid4(), frozenset({"r"}), tuple(grants))


EMPLOYEE = [GrantRule(s, PUB, frozenset({"ask"})) for s in SPACES]
CORE_STAFF = GrantRule("core", INT, frozenset({"ask", "contribute"}))
CORE_LEAD = GrantRule("core", RES, frozenset({"ask", "review", "approve"}))
GAPS = GrantRule(None, PUB, frozenset({"view_gap_reports"}))


def test_scopes_take_the_highest_level_per_space():
    p = principal(*EMPLOYEE, CORE_STAFF)
    assert p.scopes() == {"core": INT, "it": PUB, "hr": PUB}
    assert principal(*EMPLOYEE, CORE_STAFF, CORE_LEAD).scopes()["core"] is RES


def test_global_grants_never_open_content():
    p = principal(GAPS)
    assert p.scopes() == {}
    assert p.can("view_gap_reports") and not p.can("view_gap_reports", "hr")
    assert not p.can_read("hr", "public")


def test_actions_and_admin_implies_all_space_actions():
    p = principal(CORE_STAFF, GrantRule("it", INT, frozenset({"admin"})))
    assert p.can("contribute", "core") and not p.can("approve", "core")
    assert {"ask", "contribute", "review", "approve", "admin"} <= p.space_actions()["it"]
    assert not p.can("manage_users")


def test_document_visibility():
    employee = principal(*EMPLOYEE)
    lead = principal(*EMPLOYEE, CORE_LEAD)
    assert document_visible(employee, [("core", "public")])
    assert not document_visible(employee, [("core", "internal")])
    # missing / invalid labels behave as restricted
    for bad in (None, "Public", "pubic"):
        assert not document_visible(employee, [("core", bad)])
        assert document_visible(lead, [("core", bad)])
    # unassigned documents are visible to nobody
    assert not document_visible(lead, [])
    # shared with another space: either row can grant access
    assert document_visible(employee, [("core", "restricted"), ("hr", "public")])
    # a space the user has no grant on
    assert not document_visible(employee, [("finance", "public")])


@pytest.mark.parametrize(
    "space,sens,actions,msg",
    [
        (None, "public", ["ask"], "company-wide"),  # can't open every space at once
        ("core", "public", ["manage_users"], "space grants"),
        ("finance", "public", ["ask"], "unknown space"),
        ("core", "secret", ["ask"], "unknown sensitivity"),
        ("core", "public", [], "at least one"),
    ],
)
def test_validate_grant_rejects_unsafe_grants(space, sens, actions, msg):
    with pytest.raises(GrantError, match=msg):
        validate_grant(space, sens, actions, SPACES)


def test_default_roles_config_is_valid_and_matches_the_plan():
    roles = load_roles_config()
    assert {"employee", "core-staff", "core-lead", "hr-staff", "platform-admin"} <= set(roles)
    core_lead = roles["core-lead"]["grants"]
    assert core_lead == [
        {
            "space": "core",
            "max_sensitivity": "restricted",
            "actions": ["ask", "contribute", "review", "approve"],
        }
    ]
    # platform-admin manages users but grants no content by itself
    assert all(g["space"] is None for g in roles["platform-admin"]["grants"])
    # employees only ever reach public material
    assert {g["max_sensitivity"] for g in roles["employee"]["grants"]} == {"public"}


def test_resolved_levels_pass_through_but_plain_ints_do_not():
    from app.policy.engine import Sensitivity, resolve_sensitivity

    assert resolve_sensitivity(Sensitivity.PUBLIC) is Sensitivity.PUBLIC
    assert resolve_sensitivity(0) is Sensitivity.RESTRICTED


def test_document_visibility_rules():
    import uuid

    from app.policy.engine import GrantRule, Principal, Sensitivity, can_view_document

    me = Principal(
        uuid.uuid4(), frozenset(), (GrantRule("core", Sensitivity.INTERNAL, frozenset({"ask"})),)
    )
    lead = Principal(
        uuid.uuid4(),
        frozenset(),
        (GrantRule("core", Sensitivity.RESTRICTED, frozenset({"ask", "review"})),),
    )
    rows = [("core", "internal")]
    assert can_view_document(me, rows)
    assert not can_view_document(me, rows, safeguards=["names_pending"])  # floor
    assert can_view_document(lead, rows, safeguards=["names_pending"])
    assert not can_view_document(me, rows, status="draft")
    assert can_view_document(lead, rows, status="draft")
    assert can_view_document(me, [], author_id=me.user_id)  # authors see their own
    assert not can_view_document(me, [("core", "Public")])  # still fail-closed


def test_named_readers_and_unapproved_changes():
    """Handover notes have no space rows: only people named on them can read them.
    Unapproved changes are for the author and contributors/reviewers of the space."""
    from app.policy.engine import can_see_unapproved, can_view_document

    reader = principal(GrantRule("core", Sensitivity.RESTRICTED, frozenset({"ask"})))
    staff = principal(GrantRule("core", Sensitivity.INTERNAL, frozenset({"ask", "contribute"})))
    assert not can_view_document(reader, [])  # no rows, not named: nobody
    assert can_view_document(reader, [], readers=[reader.user_id])
    assert not can_view_document(staff, [], readers=[reader.user_id])
    rows = [("core", "internal")]
    assert can_see_unapproved(staff, rows)
    assert not can_see_unapproved(reader, rows)
    assert can_see_unapproved(reader, rows, author_id=reader.user_id)


def test_partial_project_shares():
    """Selected folders/SOPs of one department, read-only, safeguard floor applies."""
    import dataclasses

    from app.policy.engine import PartialShare, can_view_document

    base = principal(*EMPLOYEE)
    p = dataclasses.replace(
        base,
        partial=(PartialShare("hr", INT, folders=("HR/Onboarding/",), documents=("d1",)),),
    )
    hr_internal = [("hr", "internal")]
    assert can_view_document(p, hr_internal, path="HR/Onboarding/a.md")
    assert can_view_document(p, hr_internal, path="HR/Other.md", doc_id="d1")
    assert not can_view_document(p, hr_internal, path="HR/Other.md", doc_id="d2")
    assert not can_view_document(base, hr_internal, path="HR/Onboarding/a.md")
    # above the shared level, or floored by a safeguard, or unpublished: no
    assert not can_view_document(p, [("hr", "restricted")], path="HR/Onboarding/a.md")
    assert not can_view_document(
        p, hr_internal, path="HR/Onboarding/a.md", safeguards=["personal-data"]
    )
    assert not can_view_document(p, hr_internal, path="HR/Onboarding/a.md", status="draft")
    # a folder named in HR's share never opens another department's document there
    assert not can_view_document(p, [("core", "internal")], path="HR/Onboarding/a.md")
