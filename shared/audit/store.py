"""
Audit Store — append-only, hash-chained, tamper-evident SQLite audit log.

Follows the SQLite pattern from shared/billing/usage_store.py and
shared/auth/user_prefs.py (WAL mode, connection-per-call, row_factory).

Immutability (D-02): `audit_events_no_update` / `audit_events_no_delete`
triggers abort any UPDATE/DELETE attempt. Each row also carries a
prev_hash / row_hash pair forming a SHA-256 hash chain from a genesis
constant, so tampering (which must bypass the triggers directly, e.g. via
a raw connection with triggers dropped) is detectable via verify_chain().

Fail-closed writes (D-03): record() raises AuditWriteError on ANY failure.
Auditability is the compliance guarantee this store exists to provide —
callers must treat AuditWriteError as "the mutation cannot proceed",
mirroring the fail-closed contract from 07-CONTEXT.md D-03 (a deliberate
divergence from Phase 2 metering's fail-open UsageStore behavior).
"""
import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .redaction import redact

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

# Columns eligible for direct equality filtering in query()/count()/iter_events().
_FILTERABLE_COLUMNS = {"org_id", "actor_id", "action", "resource_type", "resource_id"}


class AuditWriteError(Exception):
    """
    Raised when an audit_events write fails for any reason.

    Fail-closed (D-03): callers must treat this as a hard failure and abort
    the mutation being audited — never silently swallow it.
    """


@dataclass
class ChainVerificationResult:
    """Result of AuditStore.verify_chain()."""

    valid: bool
    checked: int
    first_invalid_id: Optional[int] = None
    reason: Optional[str] = None


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _canonical_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _build_hash_payload(
    id_: int,
    timestamp: str,
    org_id: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    before_state: Any,
    after_state: Any,
    ip_address: Optional[str],
    details: Any,
    prev_hash: str,
) -> dict:
    return {
        "id": id_,
        "timestamp": timestamp,
        "org_id": org_id,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "before_state": before_state,
        "after_state": after_state,
        "ip_address": ip_address,
        "details": details,
        "prev_hash": prev_hash,
    }


class AuditStore:
    """SQLite-backed, append-only, hash-chained audit event store."""

    def __init__(self, db_path: str = "data/audit_events.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"AuditStore initialized: {self.db_path}")

    # -- connection helpers ------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT,
                    before_state TEXT,
                    after_state TEXT,
                    ip_address TEXT,
                    details TEXT,
                    prev_hash TEXT NOT NULL,
                    row_hash TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_org_ts "
                "ON audit_events(org_id, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_actor_ts "
                "ON audit_events(actor_id, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_action_ts "
                "ON audit_events(action, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_resource "
                "ON audit_events(resource_type, resource_id)"
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only');
                END
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is append-only');
                END
                """
            )

    # -- writes --------------------------------------------------------------

    def record(
        self,
        org_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        ip_address: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> int:
        """
        Append one audit event. Returns the assigned id.

        Redaction (D-04) is applied unconditionally to before_state,
        after_state, and details before serialization — no caller can
        opt out. On ANY failure, raises AuditWriteError (fail-closed, D-03).
        """
        before_state = redact(before_state) if before_state is not None else None
        after_state = redact(after_state) if after_state is not None else None
        details = redact(details) if details is not None else None

        timestamp = datetime.now(timezone.utc).isoformat()
        conn: Optional[sqlite3.Connection] = None
        try:
            # isolation_level=None => autocommit; we drive the transaction
            # manually via explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK so
            # id assignment + hash-chain read are serialized against other
            # concurrent writers (BEGIN IMMEDIATE takes the write lock up
            # front rather than at first write statement).
            conn = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
            conn.execute("PRAGMA busy_timeout=10000")
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")

            last = conn.execute(
                "SELECT id, row_hash FROM audit_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last is None:
                new_id = 1
                prev_hash = GENESIS_HASH
            else:
                new_id = last["id"] + 1
                prev_hash = last["row_hash"]

            payload = _build_hash_payload(
                new_id,
                timestamp,
                org_id,
                actor_id,
                action,
                resource_type,
                resource_id,
                before_state,
                after_state,
                ip_address,
                details,
                prev_hash,
            )
            row_hash = _canonical_hash(payload)

            conn.execute(
                """
                INSERT INTO audit_events
                    (id, timestamp, org_id, actor_id, action, resource_type,
                     resource_id, before_state, after_state, ip_address,
                     details, prev_hash, row_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    timestamp,
                    org_id,
                    actor_id,
                    action,
                    resource_type,
                    resource_id,
                    json.dumps(before_state) if before_state is not None else None,
                    json.dumps(after_state) if after_state is not None else None,
                    ip_address,
                    json.dumps(details) if details is not None else None,
                    prev_hash,
                    row_hash,
                ),
            )
            conn.execute("COMMIT")
            return new_id
        except Exception as e:
            if conn is not None:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
            logger.error(f"Audit write failed: {e}")
            raise AuditWriteError(f"Failed to record audit event: {e}") from e
        finally:
            if conn is not None:
                conn.close()

    # -- reads -----------------------------------------------------------

    def _build_where(self, filters: dict) -> tuple[str, list]:
        clauses = []
        params: list = []
        for key, value in filters.items():
            if key in ("start_time", "since"):
                clauses.append("timestamp >= ?")
                params.append(value)
            elif key in ("end_time", "until"):
                clauses.append("timestamp <= ?")
                params.append(value)
            elif key in _FILTERABLE_COLUMNS:
                clauses.append(f"{key} = ?")
                params.append(value)
            else:
                raise ValueError(f"Unsupported audit query filter: {key}")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        for key in ("before_state", "after_state", "details"):
            if d.get(key):
                d[key] = json.loads(d[key])
        return d

    def query(self, limit: int = 100, offset: int = 0, **filters) -> list:
        """Query events, most recent first. Filters: org_id/actor_id/action/
        resource_type/resource_id (equality), start_time/end_time (timestamp range)."""
        where, params = self._build_where(filters)
        sql = f"SELECT * FROM audit_events{where} ORDER BY id DESC LIMIT ? OFFSET ?"
        with self._connect() as conn:
            rows = conn.execute(sql, [*params, limit, offset]).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self, **filters) -> int:
        """Count events matching the same filter set as query()."""
        where, params = self._build_where(filters)
        sql = f"SELECT COUNT(*) FROM audit_events{where}"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row[0])

    def iter_events(self, batch_size: int = 1000, **filters) -> Iterator[dict]:
        """Ascending-id cursor pagination over all matching events (for export/replay)."""
        where, params = self._build_where(filters)
        # Build once: WHERE <filters> AND id > ?  OR  WHERE id > ? when no filters.
        if where:
            sql = f"SELECT * FROM audit_events{where} AND id > ? ORDER BY id ASC LIMIT ?"
        else:
            sql = "SELECT * FROM audit_events WHERE id > ? ORDER BY id ASC LIMIT ?"

        last_id = 0
        while True:
            with self._connect() as conn:
                rows = conn.execute(sql, [*params, last_id, batch_size]).fetchall()
            if not rows:
                break
            for row in rows:
                last_id = row["id"]
                yield self._row_to_dict(row)
            if len(rows) < batch_size:
                break

    # -- verification ------------------------------------------------------

    def _compute_row_hash(self, row: sqlite3.Row) -> str:
        before_state = json.loads(row["before_state"]) if row["before_state"] else None
        after_state = json.loads(row["after_state"]) if row["after_state"] else None
        details = json.loads(row["details"]) if row["details"] else None
        payload = _build_hash_payload(
            row["id"],
            row["timestamp"],
            row["org_id"],
            row["actor_id"],
            row["action"],
            row["resource_type"],
            row["resource_id"],
            before_state,
            after_state,
            row["ip_address"],
            details,
            row["prev_hash"],
        )
        return _canonical_hash(payload)

    def verify_chain(
        self, start_id: Optional[int] = None, end_id: Optional[int] = None
    ) -> ChainVerificationResult:
        """
        Recompute row_hash for every row in [start_id, end_id] (inclusive,
        defaults to the whole table), checking prev_hash linkage and id
        contiguity. Returns the first invalid id and reason on failure.
        """
        clauses = []
        params: list = []
        if start_id is not None:
            clauses.append("id >= ?")
            params.append(start_id)
        if end_id is not None:
            clauses.append("id <= ?")
            params.append(end_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_events{where} ORDER BY id ASC", params
            ).fetchall()

            if not rows:
                return ChainVerificationResult(valid=True, checked=0)

            first_row = rows[0]
            if first_row["id"] == 1:
                expected_prev_hash: Optional[str] = GENESIS_HASH
            else:
                seed = conn.execute(
                    "SELECT row_hash FROM audit_events WHERE id = ?",
                    (first_row["id"] - 1,),
                ).fetchone()
                expected_prev_hash = seed["row_hash"] if seed else None

        expected_id = first_row["id"]
        checked = 0
        for row in rows:
            checked += 1
            if row["id"] != expected_id:
                return ChainVerificationResult(
                    valid=False,
                    checked=checked,
                    first_invalid_id=row["id"],
                    reason=f"id gap: expected {expected_id}, found {row['id']}",
                )
            if expected_prev_hash is not None and row["prev_hash"] != expected_prev_hash:
                return ChainVerificationResult(
                    valid=False,
                    checked=checked,
                    first_invalid_id=row["id"],
                    reason="prev_hash linkage mismatch",
                )
            computed = self._compute_row_hash(row)
            if computed != row["row_hash"]:
                return ChainVerificationResult(
                    valid=False,
                    checked=checked,
                    first_invalid_id=row["id"],
                    reason="row_hash mismatch (tampered row)",
                )
            expected_prev_hash = row["row_hash"]
            expected_id += 1

        return ChainVerificationResult(valid=True, checked=checked)


# -- module-level singleton -------------------------------------------------

_singleton: Optional[AuditStore] = None


def get_audit_store() -> AuditStore:
    """Lazy singleton AuditStore, path from AUDIT_DB_PATH env var."""
    global _singleton
    if _singleton is None:
        _singleton = AuditStore(db_path=os.getenv("AUDIT_DB_PATH", "data/audit_events.db"))
    return _singleton


def set_audit_store(store: AuditStore) -> None:
    """Override the module-level singleton (servers/tests)."""
    global _singleton
    _singleton = store
