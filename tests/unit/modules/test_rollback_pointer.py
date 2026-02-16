"""
Unit tests for version pointer management and rollback.

Tests rollback functionality without requiring Docker services.
Uses tmp_path fixtures for SQLite DB isolation.
"""
import json
import pytest
from pathlib import Path
from shared.modules.versioning import VersionManager, ModuleVersion


@pytest.fixture
def version_manager(tmp_path):
    """Create a VersionManager with tmp_path SQLite DB."""
    db_path = str(tmp_path / "versions.db")
    return VersionManager(db_path=db_path)


@pytest.fixture
def populated_manager(version_manager):
    """VersionManager with two versions recorded."""
    v1 = version_manager.record_version(
        module_id="test/weather",
        bundle_sha256="aaa111",
        actor="builder",
        source="generated",
        validation_report={"status": "VALIDATED", "tests_passed": 3},
    )
    v2 = version_manager.record_version(
        module_id="test/weather",
        bundle_sha256="bbb222",
        actor="developer",
        source="draft_promoted",
        validation_report={"status": "VALIDATED", "tests_passed": 5},
    )
    return version_manager, v1, v2


# ── record_version ──────────────────────────────────────────────


def test_record_version(version_manager):
    vid = version_manager.record_version(
        module_id="test/hello",
        bundle_sha256="abc123",
        actor="system",
    )
    assert vid.startswith("test_hello_v_")


def test_first_version_becomes_active(version_manager):
    version_manager.record_version("test/hello", "abc123", actor="system")
    active = version_manager.get_active_version("test/hello")
    assert active is not None
    assert active.bundle_sha256 == "abc123"


def test_second_version_does_not_override_active(version_manager):
    version_manager.record_version("test/hello", "abc111", actor="system")
    version_manager.record_version("test/hello", "abc222", actor="system")
    active = version_manager.get_active_version("test/hello")
    assert active.bundle_sha256 == "abc111"  # still first


# ── list_versions ───────────────────────────────────────────────


def test_list_versions(populated_manager):
    mgr, v1, v2 = populated_manager
    versions = mgr.list_versions("test/weather")
    assert len(versions) == 2
    # newest first
    assert versions[0].version_id == v2
    assert versions[1].version_id == v1


def test_list_versions_empty(version_manager):
    assert version_manager.list_versions("nonexistent/mod") == []


# ── get_active_version ──────────────────────────────────────────


def test_get_active_version_none(version_manager):
    assert version_manager.get_active_version("nonexistent/mod") is None


# ── rollback_to_version ─────────────────────────────────────────


def test_rollback_to_version(populated_manager):
    mgr, v1, v2 = populated_manager
    # Activate v2 first
    mgr.rollback_to_version("test/weather", v2, actor="admin")
    active = mgr.get_active_version("test/weather")
    assert active.version_id == v2

    # Now rollback to v1
    result = mgr.rollback_to_version("test/weather", v1, actor="admin", reason="regression")
    assert result["status"] == "success"
    assert result["to_version"] == v1

    active = mgr.get_active_version("test/weather")
    assert active.version_id == v1


def test_rollback_to_missing_version(version_manager):
    version_manager.record_version("test/hello", "abc", actor="system")
    result = version_manager.rollback_to_version("test/hello", "nonexistent_v")
    assert result["status"] == "error"
    assert "not found" in result["error"]


def test_rollback_preserves_all_versions(populated_manager):
    mgr, v1, v2 = populated_manager
    mgr.rollback_to_version("test/weather", v1, actor="admin")
    versions = mgr.list_versions("test/weather")
    assert len(versions) == 2  # both still present


def test_multiple_rollbacks(populated_manager):
    mgr, v1, v2 = populated_manager
    mgr.rollback_to_version("test/weather", v2, actor="admin")
    mgr.rollback_to_version("test/weather", v1, actor="admin")
    mgr.rollback_to_version("test/weather", v2, actor="admin")
    active = mgr.get_active_version("test/weather")
    assert active.version_id == v2


def test_rollback_instant_no_rebuild(populated_manager):
    """Rollback is pointer movement only — no code regeneration."""
    mgr, v1, v2 = populated_manager
    result = mgr.rollback_to_version("test/weather", v1, actor="admin")
    assert result["status"] == "success"
    assert result["bundle_sha256"] == "aaa111"


# ── ModuleVersion ───────────────────────────────────────────────


def test_module_version_serialization():
    mv = ModuleVersion(
        version_id="v_20260215",
        module_id="test/hello",
        bundle_sha256="abc",
        status="VALIDATED",
        created_at="2026-02-15T00:00:00Z",
        created_by="system",
    )
    data = mv.to_dict()
    assert data["version_id"] == "v_20260215"
    restored = ModuleVersion.from_dict(data)
    assert restored.version_id == mv.version_id
    assert restored.bundle_sha256 == mv.bundle_sha256


def test_module_version_from_dict_ignores_extra():
    data = {
        "version_id": "v1",
        "module_id": "test/x",
        "bundle_sha256": "abc",
        "status": "VALIDATED",
        "created_at": "2026-01-01",
        "created_by": "test",
        "org_id": "default",  # extra field from SQLite
        "unknown_field": "ignored",
    }
    mv = ModuleVersion.from_dict(data)
    assert mv.version_id == "v1"
