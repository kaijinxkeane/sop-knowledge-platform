"""Small-to-big expansion: more of the same documents, never other documents."""

from __future__ import annotations

import uuid

import yaml

from app.agents.concierge import retrieve
from app.db.scoped import apply_reader_scope
from app.eval.answers import principal_for_roles
from app.retrieval.search import expand, search
from app.spaces import space_profiles
from tests.conftest import CONFIG_DIR, REPO_ROOT
from tests.db.conftest import fake_query

ROLES = yaml.safe_load((CONFIG_DIR / "roles.yaml").read_text())
T = yaml.safe_load((REPO_ROOT / "demo-vault-labels.yaml").read_text())
TRUTH = {**T["notes"], **T["attachments"]}


def _who(*roles):
    p = principal_for_roles(list(roles), ROLES)
    return p.__class__(uuid.uuid4(), p.roles, p.grants)


async def test_short_documents_are_passed_whole_in_order(indexed, sessions):
    p = _who("employee", "core-staff")
    q = "Give me the full agenda of the Discovery Workshop"
    async with sessions() as s:
        await apply_reader_scope(s, p)
        hits = await search(s, p, q, query_vector=await fake_query(q), space="core", limit=6)
        out = await expand(s, hits)
        await s.rollback()
    dw = [h for h in out if h.title == "Running the Discovery Workshop"]
    assert len(dw) == 6  # every section, not just the two best
    assert [h.ord for h in dw] == sorted(h.ord for h in dw)
    assert {h.document_id for h in out} == {h.document_id for h in hits}  # no new documents


async def test_budget_is_respected(indexed, sessions):
    p = _who("employee", "core-lead")
    q = "Brand Foundations slides"
    async with sessions() as s:
        await apply_reader_scope(s, p)
        hits = await search(s, p, q, query_vector=await fake_query(q), space="core", limit=6)
        out = await expand(s, hits, budget=1500)
        await s.rollback()
    first = sum(len(h.text) for h in out if h.document_id == out[0].document_id)
    rest = sum(len(h.text) for h in out if h.document_id != out[0].document_id)
    assert rest == 0 or first + rest <= 1500 or len({h.document_id for h in out}) == 1


async def test_expansion_never_exceeds_what_the_user_may_read(indexed, sessions):
    for roles in (("employee",), ("employee", "core-staff"), ("employee", "it-lead")):
        p = _who(*roles)
        for q in (
            "rate card floor price",
            "disciplinary warning",
            "brand pillars scoring",
            "laptop encryption",
            "discovery workshop agenda",
        ):
            _, per_space = await retrieve(
                sessions, p, q, await fake_query(q), space_profiles(), None
            )
            for hits in per_space.values():
                for h in hits:
                    t = TRUTH[h.vault_path]
                    assert p.can_read(t["space"], t["sensitivity"]), (roles, q, h.vault_path)
