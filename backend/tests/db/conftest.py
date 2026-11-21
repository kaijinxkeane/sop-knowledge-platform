"""Fixtures for tests that need Postgres (the docker compose stack, port 5433).

A throwaway database `sop_test` is created and migrated once per run; every
test starts from empty tables. Without Postgres these tests are skipped,
unless SOP_REQUIRE_DB=1 (CI), where they fail instead.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from urllib.parse import urlparse

import asyncpg
import httpx
import pyotp
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api import deps
from app.classify.rules import Proposal
from app.classify.service import ClassifierService
from app.db.models import User
from app.identity import roles_by_name, sync_roles, sync_spaces
from app.main import create_app
from app.policy.engine import Sensitivity
from app.security import passwords, totp
from app.vault.git import GitVault
from app.vault.indexer import Indexer
from tests.conftest import REPO_ROOT

TEST_URL = os.environ.get(
    "SOP_TEST_DATABASE_URL", "postgresql+asyncpg://sop:sop-dev-only@localhost:5433/sop_test"
)
PASSWORD = "a-long-test-password"
TABLES = (
    "document_access, documents, notice_acknowledgements, refresh_tokens, "
    "one_time_tokens, user_roles, grants, roles, users, spaces, audit_events, vault_state, "
    "known_names"
)


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/db/" in str(item.fspath):
            item.add_marker(pytest.mark.db)


async def _recreate(url: str) -> None:
    u = urlparse(url.replace("+asyncpg", ""))
    name = u.path.lstrip("/")
    admin = await asyncpg.connect(
        user=u.username,
        password=u.password,
        host=u.hostname,
        port=u.port,
        database="postgres",
        timeout=3,
    )
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    try:
        asyncio.run(_recreate(TEST_URL))
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        if os.environ.get("SOP_REQUIRE_DB") == "1":
            pytest.fail(f"Postgres required but unreachable: {type(exc).__name__}")
        pytest.skip("Postgres not reachable (run `make up`)")
    env = {**os.environ, "DATABASE_URL": TEST_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        capture_output=True,
    )
    return TEST_URL


@pytest.fixture
async def sessions(database_url):
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await sync_spaces(s)
        await sync_roles(s)
        await s.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(sessions):
    app = create_app()

    async def override():
        async with sessions() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[deps.get_db] = override
    deps.auth_limiter.reset()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


class Person:
    """A test user with a known password and TOTP secret."""

    def __init__(self, user: User, secret: str | None):
        self.user, self.secret, self.email, self._offset = user, secret, user.email, 0

    def code(self) -> str:
        # Each sign-in needs a fresh time step (replay protection), so step forward.
        c = pyotp.TOTP(self.secret).at(time.time() + 30 * self._offset)
        self._offset = min(self._offset + 1, 1)
        return c


@pytest.fixture
def make_user(sessions):
    async def _make(
        email: str | None = None, roles=("employee",), enrolled=True, home_space=None
    ) -> Person:
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        secret = totp.new_secret() if enrolled else None
        async with sessions() as s:
            user = User(
                email=email,
                display_name=email.split("@")[0],
                password_hash=passwords.hash_password(PASSWORD),
                home_space=home_space,
                totp_enabled=enrolled,
                totp_secret_enc=totp.encrypt_secret(secret) if secret else None,
                roles=await roles_by_name(s, list(roles)),
            )
            s.add(user)
            await s.commit()
        return Person(user, secret)

    return _make


@pytest.fixture
def sign_in(client):
    async def _sign_in(person: Person) -> dict:
        r = await client.post(
            "/api/v1/auth/login", json={"email": person.email, "password": PASSWORD}
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "totp_required"
        r = await client.post(
            "/api/v1/auth/totp/verify", json={"token": r.json()["token"], "code": person.code()}
        )
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _sign_in


# --- the demo vault as a git repo, indexed with fake (offline) models ------------


async def fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic bag-of-words vectors, so semantic ranking is testable offline."""
    out = []
    for t in texts:
        v = [0.0] * 1024
        for w in re.findall(r"[a-z]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 1024] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


async def fake_query(q: str) -> list[float]:
    return (await fake_embed([q]))[0]


async def broken(*_):
    raise ConnectionError("ollama down")


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    shutil.copytree(REPO_ROOT / "demo-vault", root)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=Seed", "-c", "user.email=seed@example.com", "commit", "-qm", "seed")
    return GitVault(root)


async def no_names(doc):
    """Fake Classifier: finds no names and can't place anything."""
    return Proposal(space=None, sensitivity=Sensitivity.RESTRICTED, model="fake")


@pytest.fixture
async def indexed(vault, sessions, client):
    """The demo vault indexed, name-checked (fake model) and wired into the API."""
    report = await Indexer(vault, sessions, fake_embed).sync()
    await ClassifierService(sessions, no_names).run_pending(limit=100)
    app = client._transport.app
    app.dependency_overrides[deps.get_git] = lambda: vault
    app.dependency_overrides[deps.get_session_factory] = lambda: sessions
    app.dependency_overrides[deps.get_embedder] = lambda: fake_embed
    app.dependency_overrides[deps.get_query_embedder] = lambda: fake_query
    return report
