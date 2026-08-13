"""
Audit Actor Context — ambient identity for audit event capture.

Provides a contextvar-backed ActorContext so any code path (HTTP handler,
background task, chat tool) can attribute audit events to the acting
identity without threading actor_id/org_id through every call signature.
contextvars propagate correctly across asyncio tasks and anyio.to_thread
offloads, which is why this is contextvar-backed rather than a plain global.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActorContext:
    """Immutable actor identity for the current logical operation."""

    actor_id: str
    org_id: str
    ip_address: Optional[str] = None
    channel: str = "http"


_actor_ctx: ContextVar[Optional[ActorContext]] = ContextVar(
    "_audit_actor_ctx", default=None
)


def set_actor(actor: ActorContext) -> Token:
    """Set the ambient actor context. Returns a Token for reset_actor()."""
    return _actor_ctx.set(actor)


def reset_actor(token: Token) -> None:
    """Reset the ambient actor context to its prior value."""
    _actor_ctx.reset(token)


def get_actor() -> Optional[ActorContext]:
    """Return the current ambient ActorContext, or None if unset."""
    return _actor_ctx.get()


@contextmanager
def actor_context(actor: ActorContext) -> Iterator[ActorContext]:
    """Context manager form of set_actor/reset_actor."""
    token = set_actor(actor)
    try:
        yield actor
    finally:
        reset_actor(token)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


class AuditContextMiddleware(BaseHTTPMiddleware):
    """
    Sets an ActorContext for the request scope from request.state.user /
    request.state.org_id, attached by an upstream auth middleware
    (shared/auth/middleware.py). Tolerates absence for public paths where
    no authenticated user exists — audit capture simply has no ambient
    actor in that scope.
    """

    async def dispatch(self, request: Request, call_next):
        user = getattr(request.state, "user", None)
        org_id = getattr(request.state, "org_id", None)

        token: Optional[Token] = None
        if user is not None and org_id is not None:
            actor_id = getattr(user, "user_id", None) or str(user)
            actor = ActorContext(
                actor_id=actor_id,
                org_id=org_id,
                ip_address=_client_ip(request),
                channel="http",
            )
            token = set_actor(actor)

        try:
            return await call_next(request)
        finally:
            if token is not None:
                reset_actor(token)
