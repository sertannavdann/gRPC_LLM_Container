"""
Unit tests for shared.audit — append-only hash-chained audit store,
redaction, and actor context propagation.

Covers: trigger enforcement, hash-chain integrity + tamper detection,
redaction (nested + fingerprint stability), fail-closed writes,
concurrent writers, actor-context propagation, and the Phase-8 D-06
event shape (bundle_sha256 round trip).
"""

import multiprocessing
import os
import sqlite3
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import pytest

from shared.audit import (
    ActorContext,
    AuditStore,
    AuditWriteError,
    actor_context,
    fingerprint,
    get_actor,
    redact,
    reset_actor,
    set_actor,
)
import shared.audit.store as audit_store_module
from shared.audit.store import GENESIS_HASH


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary SQLite DB path for AuditStore."""
    return str(tmp_path / "test_audit.db")


@pytest.fixture
def store(tmp_db):
    """Create a fresh AuditStore backed by a temp DB."""
    return AuditStore(db_path=tmp_db)


def _insert(store, n=1, **overrides):
    """Insert n plain audit events, returning the assigned ids."""
    ids = []
    for i in range(n):
        kwargs = dict(
            org_id="org-1",
            actor_id="actor-1",
            action="test_action",
            resource_type="widget",
            resource_id=f"w{i}",
        )
        kwargs.update(overrides)
        ids.append(store.record(**kwargs))
    return ids


# ============================================================================
# Trigger enforcement (append-only)
# ============================================================================


class TestTriggerEnforcement:
    def test_raw_update_raises(self, store, tmp_db):
        _insert(store, 1)
        conn = sqlite3.connect(tmp_db)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("UPDATE audit_events SET action = 'tampered' WHERE id = 1")
                conn.commit()
        finally:
            conn.close()

    def test_raw_delete_raises(self, store, tmp_db):
        _insert(store, 1)
        conn = sqlite3.connect(tmp_db)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM audit_events WHERE id = 1")
                conn.commit()
        finally:
            conn.close()


# ============================================================================
# Hash chain
# ============================================================================


class TestHashChain:
    def test_n_inserts_valid_chain(self, store):
        n = 10
        _insert(store, n)
        result = store.verify_chain()
        assert result.valid is True
        assert result.checked == n

    def test_genesis_prev_hash_on_row_one(self, store):
        _insert(store, 1)
        row = store.query(limit=1)[0]
        assert row["id"] == 1
        assert row["prev_hash"] == GENESIS_HASH

    def test_empty_store_chain_is_valid(self, store):
        result = store.verify_chain()
        assert result.valid is True
        assert result.checked == 0


class TestTamperDetection:
    def test_mutated_row_detected(self, store, tmp_db):
        _insert(store, 5)

        conn = sqlite3.connect(tmp_db)
        conn.execute("DROP TRIGGER audit_events_no_update")
        conn.execute("UPDATE audit_events SET action = 'tampered' WHERE id = 3")
        conn.commit()
        conn.execute(
            """
            CREATE TRIGGER audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only');
            END
            """
        )
        conn.commit()
        conn.close()

        result = store.verify_chain()
        assert result.valid is False
        assert result.first_invalid_id == 3
        assert result.reason is not None


# ============================================================================
# Redaction
# ============================================================================


class TestRedaction:
    def test_nested_dict_secrets_redacted(self):
        payload = {
            "config": {
                "api_key": "sk-live-abcdef",
                "nested": {"password": "hunter2"},
            },
            "items": [{"token": "tok-123"}, {"safe": "value"}],
        }
        out = redact(payload)
        assert out["config"]["api_key"].startswith("[REDACTED sha256:")
        assert out["config"]["nested"]["password"].startswith("[REDACTED sha256:")
        assert out["items"][0]["token"].startswith("[REDACTED sha256:")
        assert out["items"][1]["safe"] == "value"
        assert "sk-live-abcdef" not in str(out)
        assert "hunter2" not in str(out)
        assert "tok-123" not in str(out)

    def test_plain_keys_untouched(self):
        payload = {"name": "widget", "count": 5, "active": True, "note": None}
        out = redact(payload)
        assert out == payload

    def test_stable_fingerprint(self):
        assert fingerprint("secret-value") == fingerprint("secret-value")
        assert fingerprint("secret-value") != fingerprint("other-value")

    def test_non_string_secret_value_redacted_without_fingerprint(self):
        out = redact({"api_key": 12345})
        assert out["api_key"] == "[REDACTED]"

    def test_record_redacts_before_storage(self, store):
        store.record(
            org_id="org-1",
            actor_id="actor-1",
            action="update_credential",
            resource_type="credential",
            before_state={"api_key": "sk-old-value"},
            after_state={"api_key": "sk-new-value"},
            details={"secret": "shhh"},
        )
        row = store.query(limit=1)[0]
        assert "sk-old-value" not in str(row)
        assert "sk-new-value" not in str(row)
        assert "shhh" not in str(row)
        assert "[REDACTED" in str(row["before_state"])


class TestFailClosed:
    def test_write_to_readonly_db_raises_audit_write_error(self, tmp_path):
        db_path = tmp_path / "readonly.db"
        store = AuditStore(db_path=str(db_path))

        os.chmod(str(db_path), stat.S_IREAD)
        os.chmod(str(tmp_path), stat.S_IREAD | stat.S_IEXEC)
        try:
            with pytest.raises(AuditWriteError):
                store.record(
                    org_id="org-1",
                    actor_id="actor-1",
                    action="test_action",
                    resource_type="widget",
                )
        finally:
            os.chmod(str(tmp_path), stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
            os.chmod(str(db_path), stat.S_IREAD | stat.S_IWRITE)


# ============================================================================
# Concurrency
# ============================================================================


def _concurrent_writer(db_path: str, count: int, worker_id: int) -> int:
    """
    Picklable module-level worker: opens its own AuditStore against the
    shared db_path and writes `count` events, retrying on AuditWriteError
    (busy contention) up to a bounded number of attempts.
    """
    store = AuditStore(db_path=db_path)
    written = 0
    for i in range(count):
        attempts = 0
        while True:
            attempts += 1
            try:
                store.record(
                    org_id="org-1",
                    actor_id=f"worker-{worker_id}",
                    action="concurrent_write",
                    resource_type="widget",
                    resource_id=f"{worker_id}-{i}",
                )
                written += 1
                break
            except AuditWriteError:
                if attempts >= 50:
                    raise
                time.sleep(0.01)
    return written


class TestConcurrency:
    def test_two_processes_produce_contiguous_chain(self, tmp_path):
        db_path = str(tmp_path / "concurrent.db")
        # Ensure the table/triggers exist before spawning writers.
        AuditStore(db_path=db_path)

        per_worker = 50
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(processes=2) as pool:
            results = pool.starmap(
                _concurrent_writer,
                [(db_path, per_worker, 1), (db_path, per_worker, 2)],
            )

        assert sum(results) == per_worker * 2

        store = AuditStore(db_path=db_path)
        ids = sorted(row["id"] for row in store.query(limit=200))
        assert ids == list(range(1, per_worker * 2 + 1))

        result = store.verify_chain()
        assert result.valid is True
        assert result.checked == per_worker * 2


# ============================================================================
# Actor context propagation
# ============================================================================


class TestActorContext:
    def test_set_get_reset_roundtrip(self):
        assert get_actor() is None
        token = set_actor(ActorContext(actor_id="a1", org_id="o1"))
        try:
            current = get_actor()
            assert current.actor_id == "a1"
            assert current.org_id == "o1"
        finally:
            reset_actor(token)
        assert get_actor() is None

    def test_actor_context_manager_roundtrip(self):
        assert get_actor() is None
        with actor_context(ActorContext(actor_id="a2", org_id="o2")) as ctx:
            assert get_actor() is ctx
        assert get_actor() is None

    def test_propagation_into_threadpool_via_copy_context(self):
        """
        contextvars are NOT automatically inherited by threads started via
        ThreadPoolExecutor — the caller must explicitly copy the context
        (as anyio.to_thread.run_sync does internally). Verify that pattern
        works for ActorContext.
        """
        token = set_actor(ActorContext(actor_id="a3", org_id="o3"))
        try:
            ctx = copy_context()

            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(ctx.run, get_actor).result()

            assert result is not None
            assert result.actor_id == "a3"
        finally:
            reset_actor(token)


# ============================================================================
# D-06: Phase 8 approval event shape
# ============================================================================


class TestD06ApprovalEventShape:
    def test_approval_event_round_trips(self, store):
        event_id = store.record(
            org_id="org-1",
            actor_id="approver-1",
            action="module_approved",
            resource_type="module",
            resource_id="weather/openweather",
            details={
                "bundle_sha256": "abc123def456",
                "timestamp": "2026-08-13T00:00:00+00:00",
            },
        )
        assert event_id >= 1

        rows = store.query(action="module_approved", limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert row["resource_type"] == "module"
        assert row["details"]["bundle_sha256"] == "abc123def456"

        result = store.verify_chain()
        assert result.valid is True


# ============================================================================
# Metrics (REQ-012): lazy module-level holder, degrades without OTel wiring
# ============================================================================


class _FakeCounter:
    def __init__(self):
        self.calls = []

    def add(self, amount, attributes=None):
        self.calls.append((amount, attributes or {}))


class _FakeAuditMetrics:
    def __init__(self):
        self.audit_events_total = _FakeCounter()
        self.audit_write_failures_total = _FakeCounter()


class TestAuditMetrics:
    def test_successful_record_increments_events_total(self, store, monkeypatch):
        fake = _FakeAuditMetrics()
        monkeypatch.setattr(audit_store_module, "_get_audit_metrics", lambda: fake)

        store.record(
            org_id="org-1", actor_id="actor-1", action="module_enabled",
            resource_type="module", resource_id="weather/openweather",
        )

        assert len(fake.audit_events_total.calls) == 1
        amount, attrs = fake.audit_events_total.calls[0]
        assert amount == 1
        assert attrs == {"action": "module_enabled", "resource_type": "module", "channel": "system"}
        assert fake.audit_write_failures_total.calls == []

    def test_successful_record_uses_ambient_actor_channel(self, store, monkeypatch):
        fake = _FakeAuditMetrics()
        monkeypatch.setattr(audit_store_module, "_get_audit_metrics", lambda: fake)

        with actor_context(ActorContext(actor_id="a1", org_id="org-1", channel="chat")):
            store.record(
                org_id="org-1", actor_id="a1", action="module_enabled",
                resource_type="module",
            )

        _, attrs = fake.audit_events_total.calls[0]
        assert attrs["channel"] == "chat"

    def test_failed_record_increments_write_failures_total(self, store, tmp_db, monkeypatch):
        fake = _FakeAuditMetrics()
        monkeypatch.setattr(audit_store_module, "_get_audit_metrics", lambda: fake)

        # Make the DB read-only so the write fails (fail-closed, D-03).
        os.chmod(tmp_db, stat.S_IREAD)
        try:
            with pytest.raises(AuditWriteError):
                store.record(
                    org_id="org-1", actor_id="actor-1", action="module_enabled",
                    resource_type="module",
                )
        finally:
            os.chmod(tmp_db, stat.S_IREAD | stat.S_IWRITE)

        assert fake.audit_events_total.calls == []
        assert len(fake.audit_write_failures_total.calls) == 1
        amount, attrs = fake.audit_write_failures_total.calls[0]
        assert amount == 1
        assert attrs == {"action": "module_enabled", "resource_type": "module"}

    def test_metrics_failure_does_not_block_write(self, store, monkeypatch):
        """A broken metrics backend must never prevent an audit write from
        succeeding — telemetry is best-effort, the write itself is not."""
        def _boom():
            raise RuntimeError("no meter provider configured")

        monkeypatch.setattr(audit_store_module, "_get_audit_metrics", _boom)

        event_id = store.record(
            org_id="org-1", actor_id="actor-1", action="module_enabled",
            resource_type="module",
        )
        assert event_id >= 1
