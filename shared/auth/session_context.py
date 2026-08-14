"""
Session Identity Context — ambient AUTHENTICATED principal for non-HTTP
entry points (chat/gRPC).

Distinct from `shared.audit.ActorContext`: that carries an actor_id/org_id
pair used purely for audit attribution and has no notion of `role` or
authorization. This module carries the full `shared.auth.models.User`
(including `role`) resolved from a validated credential (an `x-api-key`
gRPC metadata entry today), and is the authorization source privileged
tool actions (e.g. `ApproveModuleStrategy`/`RejectModuleStrategy` in
tools/builtin/module_admin.py) must consult via `get_session_user()`
before performing a mutation. HTTP entry points do not need this module —
they already carry `request.state.user` via `shared.auth.middleware`.

Mirrors the contextvar/Token/contextmanager structure of
shared/audit/context.py exactly, so the two modules stay easy to reason
about side by side. contextvars propagate correctly across asyncio tasks
and anyio.to_thread offloads, which is why this is contextvar-backed
rather than a plain global.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

from .models import User

logger = logging.getLogger(__name__)


class SessionAuthError(Exception):
    """Raised when session authentication/authorization cannot proceed."""


_session_user_ctx: ContextVar[Optional[User]] = ContextVar(
    "_session_user_ctx", default=None
)


def set_session_user(user: User) -> Token:
    """Set the ambient authenticated session User. Returns a Token for reset_session_user()."""
    return _session_user_ctx.set(user)


def reset_session_user(token: Token) -> None:
    """Reset the ambient session User to its prior value."""
    _session_user_ctx.reset(token)


def get_session_user() -> Optional[User]:
    """Return the current ambient authenticated User, or None if unset."""
    return _session_user_ctx.get()


@contextmanager
def session_user(user: User) -> Iterator[User]:
    """Context manager form of set_session_user/reset_session_user. Resets on exit, including on exception."""
    token = set_session_user(user)
    try:
        yield user
    finally:
        reset_session_user(token)
