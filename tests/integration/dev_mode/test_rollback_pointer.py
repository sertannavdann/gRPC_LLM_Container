"""
Integration test for version rollback pointer management.

Tests:
1. Install v1 (generated)
2. Promote v2 (dev-mode edit)
3. Rollback to v1
4. Verify active module is v1 behavior
5. Verify v2 is still available for re-activation
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from shared.modules.versioning import VersionManager, ModuleVersion
from shared.modules.audit import DevModeAuditLog


@pytest.fixture
def temp_workspace():
    """Create temporary workspace for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "versions.db"
    audit_dir = temp_dir / "audit"
    audit_dir.mkdir(parents=True)

    yield {
        "temp_dir": temp_dir,
        "db_path": str(db_path),
        "audit_dir": audit_dir
    }

    # Cleanup
    shutil.rmtree(temp_dir)


def test_rollback_pointer_movement(temp_workspace):
    """Test rollback is instant pointer movement without rebuild."""
    audit_log = DevModeAuditLog(temp_workspace["audit_dir"])
    version_manager = VersionManager(
        db_path=temp_workspace["db_path"],
        audit_log=audit_log
    )

    module_id = "test/example"

    # Step 1: Record v1 (generated)
    v1_id = version_manager.record_version(
        module_id=module_id,
        bundle_sha256="aaa111",
        actor="system",
        validation_report={"status": "VALIDATED"},
        source="generated",
        metadata={"description": "Initial generated version"}
    )

    # Verify v1 is active
    active = version_manager.get_active_version(module_id)
    assert active is not None
    assert active.version_id == v1_id
    assert active.bundle_sha256 == "aaa111"

    # Step 2: Record v2 (draft promoted)
    v2_id = version_manager.record_version(
        module_id=module_id,
        bundle_sha256="bbb222",
        actor="dev_user",
        validation_report={"status": "VALIDATED"},
        source="draft_promoted",
        metadata={"draft_id": "draft_123", "description": "Fixed bug via draft"}
    )

    # Manually set v2 as active (simulating promotion)
    version_manager.rollback_to_version(
        module_id=module_id,
        target_version_id=v2_id,
        actor="dev_user",
        reason="Promote draft to active"
    )

    # Verify v2 is active
    active = version_manager.get_active_version(module_id)
    assert active is not None
    assert active.version_id == v2_id
    assert active.bundle_sha256 == "bbb222"

    # Step 3: Rollback to v1
    rollback_result = version_manager.rollback_to_version(
        module_id=module_id,
        target_version_id=v1_id,
        actor="admin_user",
        reason="Bug found in v2, rolling back to v1"
    )

    assert rollback_result["status"] == "success"
    assert rollback_result["from_version"] == v2_id
    assert rollback_result["to_version"] == v1_id
    assert rollback_result["bundle_sha256"] == "aaa111"

    # Step 4: Verify active module is v1
    active = version_manager.get_active_version(module_id)
    assert active is not None
    assert active.version_id == v1_id
    assert active.bundle_sha256 == "aaa111"
    assert active.source == "generated"

    # Step 5: Verify v2 is still available
    all_versions = version_manager.list_versions(module_id)
    assert len(all_versions) == 2
    v2 = version_manager.get_version(v2_id)
    assert v2 is not None
    assert v2.bundle_sha256 == "bbb222"
    assert v2.status == "VALIDATED"  # Still valid, just not active

    # Step 6: Verify audit trail
    events = audit_log.get_events(module_id=module_id)
    rollback_events = [e for e in events if e.action == "version_rollback"]
    assert len(rollback_events) >= 1
    last_rollback = rollback_events[-1]
    assert last_rollback.details["from_version"] == v2_id
    assert last_rollback.details["to_version"] == v1_id
    assert last_rollback.details["reason"] == "Bug found in v2, rolling back to v1"


def test_rollback_requires_validated_status(temp_workspace):
    """Test that rollback only works for VALIDATED versions."""
    version_manager = VersionManager(db_path=temp_workspace["db_path"])

    module_id = "test/example"

    # Record a version
    v1_id = version_manager.record_version(
        module_id=module_id,
        bundle_sha256="aaa111",
        actor="system"
    )

    # Manually corrupt version status (simulate failed validation)
    import sqlite3
    with sqlite3.connect(temp_workspace["db_path"]) as conn:
        conn.execute(
            "UPDATE versions SET status = 'FAILED' WHERE version_id = ?",
            (v1_id,)
        )

    # Try to rollback to failed version
    result = version_manager.rollback_to_version(
        module_id=module_id,
        target_version_id=v1_id,
        actor="admin"
    )

    assert result["status"] == "error"
    assert "Only VALIDATED versions allowed" in result["error"]


def test_list_versions_ordered_by_time(temp_workspace):
    """Test that versions are listed in descending chronological order."""
    version_manager = VersionManager(db_path=temp_workspace["db_path"])

    module_id = "test/example"

    # Record 3 versions
    v1_id = version_manager.record_version(
        module_id=module_id,
        bundle_sha256="aaa111",
        actor="system"
    )

    v2_id = version_manager.record_version(
        module_id=module_id,
        bundle_sha256="bbb222",
        actor="system"
    )

    v3_id = version_manager.record_version(
        module_id=module_id,
        bundle_sha256="ccc333",
        actor="system"
    )

    # List versions
    versions = version_manager.list_versions(module_id)

    # Verify order (newest first)
    assert len(versions) == 3
    assert versions[0].version_id == v3_id  # Most recent
    assert versions[1].version_id == v2_id
    assert versions[2].version_id == v1_id  # Oldest
