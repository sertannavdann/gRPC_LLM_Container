"""
Audit Redaction — deep secret redaction for audit event payloads.

Applied unconditionally at the AuditStore layer before any before_state,
after_state, or details payload is persisted (D-04). No caller can opt out:
this module has no "disable redaction" switch by design.
"""
import hashlib
import re
from typing import Any

# Matches dict keys that carry secret-shaped values. Case-insensitive.
SECRET_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|credential|authorization|private[_-]?key)"
)

_JSON_SCALAR_TYPES = (str, int, float, bool, type(None))


def fingerprint(value: Any) -> str:
    """
    SHA-256 fingerprint (first 16 hex chars) of a value's string form.

    Used so redacted secret values remain comparable across audit rows
    (change detection) without ever disclosing the original value.
    """
    if not isinstance(value, str):
        value = str(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _redact_leaf(value: Any) -> str:
    if isinstance(value, str):
        return f"[REDACTED sha256:{fingerprint(value)}]"
    return "[REDACTED]"


def redact(payload: Any) -> Any:
    """
    Recursively redact secret-keyed values in a JSON-like structure.

    - Dict keys matching SECRET_KEY_PATTERN have their values replaced with
      a redaction marker (string values retain a stable SHA-256 fingerprint).
    - Dicts and lists are recursed into.
    - JSON scalar leaves (str/int/float/bool/None) pass through unchanged.
    - Any other leaf (not JSON-serializable) is coerced via str().
    """
    if isinstance(payload, dict):
        redacted: dict = {}
        for key, value in payload.items():
            if isinstance(key, str) and SECRET_KEY_PATTERN.search(key):
                redacted[key] = _redact_leaf(value)
            else:
                redacted[key] = redact(value)
        return redacted

    if isinstance(payload, list):
        return [redact(item) for item in payload]

    if isinstance(payload, _JSON_SCALAR_TYPES):
        return payload

    return str(payload)
