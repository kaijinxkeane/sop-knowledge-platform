"""The one-way rule applies to people's saves too."""

import uuid

import pytest

from app.policy.engine import GrantRule, Principal, Sensitivity
from app.vault.labels import Labels
from app.vault.writes import WriteDenied, check_write

PUB, INT, RES = Sensitivity.PUBLIC, Sensitivity.INTERNAL, Sensitivity.RESTRICTED
STAFF = Principal(
    uuid.uuid4(), frozenset(), (GrantRule("core", INT, frozenset({"ask", "contribute"})),)
)
LEAD = Principal(
    uuid.uuid4(),
    frozenset(),
    (GrantRule("core", RES, frozenset({"ask", "contribute", "review", "approve"})),),
)
READER = Principal(uuid.uuid4(), frozenset(), (GrantRule("core", PUB, frozenset({"ask"})),))


def L(space="core", sens=INT, shared=()):
    return Labels(space=space, sensitivity=sens, shared_with=list(shared))


def ok(p, old, new, **kw):
    check_write(p, old, new, old_status=kw.get("old_status"), new_status=kw.get("new_status"))


def denied(p, old, new, match, **kw):
    with pytest.raises(WriteDenied, match=match):
        ok(p, old, new, **kw)


def test_staff_can_create_internal_or_restricted():
    ok(STAFF, None, L(sens=INT))
    ok(STAFF, None, L(sens=RES))
    denied(STAFF, None, L(sens=PUB), "approval")
    ok(LEAD, None, L(sens=PUB))


def test_saving_needs_contribute():
    denied(READER, L(sens=PUB), L(sens=PUB), "can't save")
    denied(STAFF, None, L(space="hr"), "can't save")
    denied(STAFF, None, L(space=None), "choose a space")


def test_tightening_is_free_widening_needs_the_lead():
    ok(STAFF, L(sens=INT), L(sens=RES))
    denied(STAFF, L(sens=RES), L(sens=INT), "approval")
    ok(LEAD, L(sens=RES), L(sens=INT))


def test_sharing_and_moving_need_the_lead():
    denied(STAFF, L(), L(shared=[("hr", INT)]), "sharing")
    denied(STAFF, L(), L(space="hr"), "can't save")


def test_only_the_lead_publishes():
    denied(STAFF, L(), L(), "publish", old_status="draft", new_status="published")
    ok(STAFF, L(), L(), old_status="published", new_status="published")  # unchanged
    ok(LEAD, L(), L(), old_status="draft", new_status="published")
