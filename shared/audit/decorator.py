"""
@audit_action — HTTP-endpoint convenience wrapper around AuditStore.record().

Wraps sync and async callables (typically FastAPI route handlers). Captures
an optional before/after snapshot of the mutated resource, resolves actor
identity (ambient contextvar first, then a Starlette Request found among the
bound arguments, else "system"/"default"), and records one audit event on
successful completion. Handler exceptions propagate untouched — a failed
mutation is never recorded (REQ-011 scope: only successful mutations produce
audit rows in this phase). A store-write failure raises HTTPException(500)
so the caller sees the mutation as failed (D-03 fail-closed), even though
the underlying state change may already have applied.
"""
import functools
import inspect
import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException
from starlette.requests import Request

from .context import ActorContext, get_actor
from .store import AuditStore, AuditWriteError, get_audit_store

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _resolve_actor(bound_args: dict) -> ActorContext:
    """contextvar wins over a Request found in bound args; else "system"/"default"."""
    actor = get_actor()
    if actor is not None:
        return actor

    for value in bound_args.values():
        if isinstance(value, Request):
            user = getattr(value.state, "user", None)
            org_id = getattr(value.state, "org_id", None)
            actor_id = getattr(user, "user_id", None) if user is not None else None
            return ActorContext(
                actor_id=actor_id or "system",
                org_id=org_id or "default",
                ip_address=_client_ip(value),
                channel="http",
            )

    return ActorContext(actor_id="system", org_id="default")


def _resolve_resource_id(template: Optional[str], bound_args: dict) -> Optional[str]:
    if template is None:
        return None
    try:
        return template.format(**bound_args)
    except Exception as e:
        logger.warning(f"audit resource_id template {template!r} failed: {e}")
        return template


def _take_snapshot(
    snapshot: Optional[Callable[..., Any]], bound_args: dict, phase: str, func_name: str
) -> Any:
    if snapshot is None:
        return None
    try:
        return snapshot(**bound_args)
    except Exception as e:
        logger.warning(f"audit snapshot ({phase}) failed for {func_name}: {e}")
        return None


def audit_action(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    snapshot: Optional[Callable[..., Any]] = None,
    store: Optional[AuditStore] = None,
) -> Callable:
    """
    Decorate a sync or async handler so successful calls record an audit
    event via AuditStore.record().

    Args:
        action: audit action name (e.g. "module_enabled")
        resource_type: audit resource_type (e.g. "module")
        resource_id: optional str template over the handler's bound
            arguments, e.g. "{category}/{platform}"
        snapshot: optional callable invoked with the handler's bound
            arguments both before and after the call, to capture
            before_state/after_state. If omitted, after_state falls back to
            the handler's return value when it is a dict, else None, and
            before_state is None.
        store: AuditStore override (defaults to get_audit_store() resolved
            at call time, not decoration time, so tests can swap the
            singleton after import).
    """

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)

        def _bind(args, kwargs) -> dict:
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            return dict(bound.arguments)

        def _record(bound_args: dict, before: Any, result: Any) -> None:
            audit_store = store or get_audit_store()
            actor = _resolve_actor(bound_args)
            rid = _resolve_resource_id(resource_id, bound_args)
            if snapshot is not None:
                after = _take_snapshot(snapshot, bound_args, "after", func.__name__)
            else:
                after = result if isinstance(result, dict) else None
            try:
                audit_store.record(
                    org_id=actor.org_id,
                    actor_id=actor.actor_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=rid,
                    before_state=before,
                    after_state=after,
                    ip_address=actor.ip_address,
                )
            except AuditWriteError as e:
                logger.error(f"Audit write failed for {func.__name__}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Audit write failed; mutation not recorded — "
                        "the state change may have applied"
                    ),
                ) from e

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                bound_args = _bind(args, kwargs)
                before = _take_snapshot(snapshot, bound_args, "before", func.__name__)
                result = await func(*args, **kwargs)
                _record(bound_args, before, result)
                return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            bound_args = _bind(args, kwargs)
            before = _take_snapshot(snapshot, bound_args, "before", func.__name__)
            result = func(*args, **kwargs)
            _record(bound_args, before, result)
            return result

        return sync_wrapper

    return decorator
