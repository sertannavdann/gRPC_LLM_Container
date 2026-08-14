"""
Unit tests for tiered per-org usage retention pruning (REQ-017) and the
shared GC/retention worker pass (D-11).

Covers UsageStore.delete_before/list_org_ids and
orchestrator.retention_worker.prune_expired_usage against a real
UsageStore(tmp_path SQLite DB) seeded with rows at explicit created_at
values across tiers, plus a stub api_key_store. Also covers
gc_and_retention_pass()'s fault isolation between the GC and retention
policies (D-11).
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from shared.billing.usage_store import UsageStore
from orchestrator.retention_worker import (
    TIER_RETENTION_DAYS,
    gc_and_retention_pass,
    prune_expired_usage,
)


class StubOrg:
    def __init__(self, plan):
        self.plan = plan


class StubAPIKeyStore:
    def __init__(self, orgs: dict):
        self._orgs = orgs

    def get_organization(self, org_id):
        return self._orgs.get(org_id)


@pytest.fixture
def usage_store(tmp_path):
    return UsageStore(db_path=str(tmp_path / "billing.db"))


def _insert_record(store: UsageStore, org_id: str, created_at: str, run_units: float = 1.0):
    """Insert a usage row with an explicit created_at, bypassing record()'s now()."""
    with store._connect() as conn:
        conn.execute(
            """INSERT INTO usage_records
               (id, org_id, user_id, thread_id, tool_name, run_units,
                tier, cpu_seconds, gpu_seconds, latency_ms, created_at, period)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"{org_id}-{created_at}",
                org_id,
                None,
                None,
                "test_tool",
                run_units,
                "standard",
                0.0,
                0.0,
                0.0,
                created_at,
                created_at[:7],
            ),
        )


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ── TIER_RETENTION_DAYS convention ──────────────────────────────────


def test_tier_retention_days_convention():
    assert TIER_RETENTION_DAYS["free"] == 7
    assert TIER_RETENTION_DAYS["team"] == 90
    assert TIER_RETENTION_DAYS["enterprise"] == -1


# ── UsageStore.delete_before ────────────────────────────────────────


def test_delete_before_deletes_only_older_rows_for_org(usage_store):
    _insert_record(usage_store, "org-a", _iso_days_ago(10))
    _insert_record(usage_store, "org-a", _iso_days_ago(1))

    cutoff = _iso_days_ago(5)
    deleted = usage_store.delete_before("org-a", cutoff)

    assert deleted == 1
    remaining = usage_store.get_usage_history("org-a", limit=10)
    assert len(remaining) == 1


def test_delete_before_leaves_other_orgs_untouched(usage_store):
    _insert_record(usage_store, "org-a", _iso_days_ago(10))
    _insert_record(usage_store, "org-b", _iso_days_ago(10))

    usage_store.delete_before("org-a", _iso_days_ago(5))

    assert len(usage_store.get_usage_history("org-a", limit=10)) == 0
    assert len(usage_store.get_usage_history("org-b", limit=10)) == 1


def test_delete_before_leaves_newer_rows_untouched(usage_store):
    _insert_record(usage_store, "org-a", _iso_days_ago(1))

    deleted = usage_store.delete_before("org-a", _iso_days_ago(5))

    assert deleted == 0
    assert len(usage_store.get_usage_history("org-a", limit=10)) == 1


def test_delete_before_uses_parameterized_query(usage_store):
    # Regression guard against SQL injection via org_id — a malicious org_id
    # containing SQL should be treated as a literal, not executed.
    _insert_record(usage_store, "org-a", _iso_days_ago(10))
    malicious_org_id = "org-a' OR '1'='1"

    deleted = usage_store.delete_before(malicious_org_id, _iso_days_ago(5))

    assert deleted == 0
    assert len(usage_store.get_usage_history("org-a", limit=10)) == 1


# ── UsageStore.list_org_ids ──────────────────────────────────────────


def test_list_org_ids_returns_distinct_orgs(usage_store):
    _insert_record(usage_store, "org-a", _iso_days_ago(1))
    _insert_record(usage_store, "org-a", _iso_days_ago(2))
    _insert_record(usage_store, "org-b", _iso_days_ago(1))

    org_ids = usage_store.list_org_ids()

    assert sorted(org_ids) == ["org-a", "org-b"]


def test_list_org_ids_empty_store(usage_store):
    assert usage_store.list_org_ids() == []


# ── prune_expired_usage ──────────────────────────────────────────────


def test_prune_expired_usage_free_tier_prunes_old_rows(usage_store):
    _insert_record(usage_store, "org-free", _iso_days_ago(10))
    _insert_record(usage_store, "org-free", _iso_days_ago(1))
    api_key_store = StubAPIKeyStore({"org-free": StubOrg("free")})

    result = prune_expired_usage(usage_store, api_key_store)

    assert result["pruned"]["org-free"] == 1
    assert len(usage_store.get_usage_history("org-free", limit=10)) == 1


def test_prune_expired_usage_team_tier_uses_90_day_window(usage_store):
    _insert_record(usage_store, "org-team", _iso_days_ago(100))
    _insert_record(usage_store, "org-team", _iso_days_ago(10))
    api_key_store = StubAPIKeyStore({"org-team": StubOrg("team")})

    result = prune_expired_usage(usage_store, api_key_store)

    assert result["pruned"]["org-team"] == 1
    assert len(usage_store.get_usage_history("org-team", limit=10)) == 1


def test_prune_expired_usage_enterprise_never_pruned(usage_store):
    _insert_record(usage_store, "org-ent", _iso_days_ago(3650))
    api_key_store = StubAPIKeyStore({"org-ent": StubOrg("enterprise")})

    result = prune_expired_usage(usage_store, api_key_store)

    assert "org-ent" not in result["pruned"]
    assert len(usage_store.get_usage_history("org-ent", limit=10)) == 1


def test_prune_expired_usage_missing_org_defaults_to_free(usage_store):
    _insert_record(usage_store, "org-unknown", _iso_days_ago(10))
    api_key_store = StubAPIKeyStore({})  # no record for org-unknown

    result = prune_expired_usage(usage_store, api_key_store)

    assert result["pruned"]["org-unknown"] == 1


def test_prune_expired_usage_no_api_key_store_defaults_to_free(usage_store):
    _insert_record(usage_store, "org-x", _iso_days_ago(10))

    result = prune_expired_usage(usage_store, api_key_store=None)

    assert result["pruned"]["org-x"] == 1


def test_prune_expired_usage_one_org_failure_does_not_abort_others(usage_store):
    _insert_record(usage_store, "org-good", _iso_days_ago(10))

    class FailingAPIKeyStore:
        def get_organization(self, org_id):
            if org_id == "org-good":
                raise RuntimeError("boom")
            return None

    result = prune_expired_usage(usage_store, FailingAPIKeyStore())

    assert len(result["errors"]) == 1
    assert result["errors"][0]["org_id"] == "org-good"


def test_prune_expired_usage_empty_store_returns_empty_result(usage_store):
    result = prune_expired_usage(usage_store, api_key_store=None)

    assert result == {"pruned": {}, "errors": []}


def test_retention_worker_no_manual_z_suffix():
    """Regression guard for WR-03: no manually appended 'Z' ISO-8601 suffix."""
    import inspect
    import orchestrator.retention_worker as rw

    source = inspect.getsource(rw)
    assert 'isoformat() + "Z"' not in source


# ── gc_and_retention_pass: fault isolation (D-11) ────────────────────


def test_gc_and_retention_pass_runs_both_policies(tmp_path, usage_store):
    modules_dir = tmp_path / "modules"
    artifacts_dir = tmp_path / "artifacts"
    modules_dir.mkdir()
    artifacts_dir.mkdir()
    _insert_record(usage_store, "org-a", _iso_days_ago(10))
    api_key_store = StubAPIKeyStore({"org-a": StubOrg("free")})

    result = gc_and_retention_pass(
        modules_dir,
        artifacts_dir,
        usage_store=usage_store,
        api_key_store=api_key_store,
        version_manager=None,
    )

    assert result["gc"] == {"scanned": 0, "purged": [], "protected": [], "errors": []}
    assert result["retention"]["pruned"]["org-a"] == 1


def test_gc_and_retention_pass_gc_failure_does_not_block_retention(tmp_path, usage_store, monkeypatch):
    modules_dir = tmp_path / "modules"
    artifacts_dir = tmp_path / "artifacts"
    modules_dir.mkdir()
    artifacts_dir.mkdir()
    _insert_record(usage_store, "org-a", _iso_days_ago(10))
    api_key_store = StubAPIKeyStore({"org-a": StubOrg("free")})

    def _boom(*args, **kwargs):
        raise RuntimeError("gc exploded")

    import shared.modules.gc as gc_module
    monkeypatch.setattr(gc_module, "sweep_gc_pending", _boom)

    result = gc_and_retention_pass(
        modules_dir,
        artifacts_dir,
        usage_store=usage_store,
        api_key_store=api_key_store,
        version_manager=None,
    )

    assert "error" in result["gc"]
    assert result["retention"]["pruned"]["org-a"] == 1


def test_gc_and_retention_pass_retention_failure_does_not_block_gc(tmp_path):
    modules_dir = tmp_path / "modules"
    artifacts_dir = tmp_path / "artifacts"
    modules_dir.mkdir()
    artifacts_dir.mkdir()

    class FailingUsageStore:
        def list_org_ids(self):
            raise RuntimeError("retention exploded")

    result = gc_and_retention_pass(
        modules_dir,
        artifacts_dir,
        usage_store=FailingUsageStore(),
        api_key_store=None,
        version_manager=None,
    )

    assert result["gc"] == {"scanned": 0, "purged": [], "protected": [], "errors": []}
    assert "errors" in result["retention"] and result["retention"]["errors"]


def test_gc_and_retention_pass_no_usage_store_skips_retention(tmp_path):
    modules_dir = tmp_path / "modules"
    artifacts_dir = tmp_path / "artifacts"
    modules_dir.mkdir()
    artifacts_dir.mkdir()

    result = gc_and_retention_pass(modules_dir, artifacts_dir, usage_store=None)

    assert result["retention"] == {"skipped": "no usage_store provided"}
