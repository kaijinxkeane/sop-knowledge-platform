"""Request dependencies: database session, signed-in user, permission checks."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_sessionmaker
from app.identity import get_user, principal_for
from app.policy.engine import Principal
from app.security.tokens import ACCESS, TokenError, decode

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@dataclass
class CurrentUser:
    user: User
    principal: Principal


UNAUTHENTICATED = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "not signed in", headers={"WWW-Authenticate": "Bearer"}
)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if creds is None:
        raise UNAUTHENTICATED
    try:
        user_id = decode(creds.credentials, ACCESS)
    except TokenError:
        raise UNAUTHENTICATED from None
    user = await get_user(session, user_id)
    # Checked on every request: deactivation and role changes apply immediately.
    if user is None or not user.is_active or not user.totp_enabled:
        raise UNAUTHENTICATED
    from app.projects.service import principal_with_projects

    # Project access is worked out per request too: it ends the day a project does.
    principal = await principal_with_projects(session, user, principal_for(user))
    return CurrentUser(user=user, principal=principal)


def require_global(action: str):
    async def check(me: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not me.principal.can(action):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
        return me

    return check


class RateLimiter:
    """Sliding-window limit per client address (single API process)."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


auth_limiter = RateLimiter(limit=20, window_seconds=300)


def limit_auth(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not auth_limiter.check(client):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts; try later")


# --- vault, indexer and embeddings (overridable in tests) ------------------------


def get_git():
    from app.config import get_settings
    from app.vault.git import GitVault

    return GitVault(get_settings().vault_path)


def get_session_factory():
    return get_sessionmaker()


def get_embedder():
    from app.retrieval.embed import embed_documents

    return embed_documents


def get_query_embedder():
    from app.retrieval.embed import embed_query

    return embed_query


ask_limiter = RateLimiter(limit=30, window_seconds=300)  # per signed-in user


def get_gateway():
    from app.retrieval.embed import _gateway

    return _gateway()
