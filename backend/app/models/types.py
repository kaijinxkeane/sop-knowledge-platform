"""Provider-neutral types for the model gateway (plan §5.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant"]
Location = Literal["local", "cloud"]

# Pseudo-space for vault content that has not been classified yet. Unclassified
# content is treated as the strictest case: it may only go to local models.
UNCLASSIFIED = "__unclassified__"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class ContentScope:
    """Which vault content a request carries, for data-boundary enforcement.

    ``spaces`` lists every space whose text appears in the request (retrieved
    passages, note bodies). Use ``ContentScope.none()`` only when the request
    carries no vault content at all (e.g. routing a user's question).
    """

    spaces: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def none(cls) -> ContentScope:
        return cls(frozenset())

    @classmethod
    def of(cls, *spaces: str) -> ContentScope:
        return cls(frozenset(spaces))

    @classmethod
    def unclassified(cls) -> ContentScope:
        return cls(frozenset({UNCLASSIFIED}))


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass(frozen=True)
class ChatResult:
    text: str
    tier: str
    provider: str
    model: str
    stop_reason: str | None
    usage: Usage
    latency_ms: int
    request_id: str | None = None


class GatewayError(Exception):
    """Base class for gateway failures."""


class DataBoundaryError(GatewayError):
    """A request would send local-only content to a cloud provider. Never retried."""


class ProviderUnavailableError(GatewayError):
    """The provider could not be reached or is overloaded; safe to retry later."""


class ProviderConfigError(GatewayError):
    """The provider is misconfigured (missing key, unknown model, bad credentials)."""


class ModelRefusalError(GatewayError):
    """The model declined the request (stop_reason == "refusal")."""
