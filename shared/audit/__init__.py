"""
shared.audit — append-only, hash-chained, tamper-evident audit trail (REQ-010).

Public surface:
- AuditStore / AuditWriteError / ChainVerificationResult / get_audit_store / set_audit_store
- redact / fingerprint — store-layer secret redaction (D-04)
- ActorContext / set_actor / reset_actor / get_actor / actor_context / AuditContextMiddleware
  — ambient actor identity for downstream capture paths (decorator, dual-write, chat tools)
"""
from .context import (
    ActorContext,
    AuditContextMiddleware,
    actor_context,
    get_actor,
    reset_actor,
    set_actor,
)
from .decorator import audit_action
from .redaction import fingerprint, redact
from .store import (
    AuditStore,
    AuditWriteError,
    ChainVerificationResult,
    get_audit_store,
    set_audit_store,
)

__all__ = [
    "AuditStore",
    "AuditWriteError",
    "ChainVerificationResult",
    "get_audit_store",
    "set_audit_store",
    "redact",
    "fingerprint",
    "ActorContext",
    "set_actor",
    "reset_actor",
    "get_actor",
    "actor_context",
    "AuditContextMiddleware",
    "audit_action",
]
