"""Hash chain logic (no database): tampering anywhere breaks verification."""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.audit import GENESIS, _check_details, compute_hash, verify_chain


@dataclasses.dataclass
class Ev:
    id: int
    ts: datetime
    actor_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict
    prev_hash: str
    hash: str


def chain(n=4):
    prev, out, t0 = GENESIS, [], datetime(2026, 11, 21, tzinfo=UTC)
    for i in range(n):
        ts, actor = t0 + timedelta(seconds=i), uuid.uuid4()
        h = compute_hash(prev, ts, actor, f"a{i}", "user", str(i), {"k": i})
        out.append(Ev(i + 1, ts, actor, f"a{i}", "user", str(i), {"k": i}, prev, h))
        prev = h
    return out


def test_intact_chain_verifies():
    assert verify_chain(chain()) == (True, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("action", "edited"),
        ("details", {"k": 99}),
        ("target_id", "x"),
        ("ts", datetime(2020, 1, 1, tzinfo=UTC)),
    ],
)
def test_edit_is_detected(field, value):
    events = chain()
    setattr(events[1], field, value)
    assert verify_chain(events) == (False, 2)


def test_deleted_event_is_detected():
    events = chain()
    del events[1]
    assert verify_chain(events) == (False, 3)


def test_details_key_order_does_not_matter():
    ts = datetime(2026, 11, 21, tzinfo=UTC)
    assert compute_hash(GENESIS, ts, None, "a", None, None, {"x": 1, "y": 2}) == compute_hash(
        GENESIS, ts, None, "a", None, None, {"y": 2, "x": 1}
    )


@pytest.mark.parametrize("key", ["password", "totp_code", "refresh_token", "question", "content"])
def test_secret_or_content_details_refused(key):
    with pytest.raises(ValueError):
        _check_details({key: "x"})
