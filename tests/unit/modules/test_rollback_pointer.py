"""
Unit tests for version pointer management and rollback.

Tests rollback functionality without requiring Docker services.
Uses tmp_path fixtures to verify pointer movement and version preservation.
"""
import json
import pytest
from pathlib import Path
from shared.modules.versioning import VersionManager, VersionRecord


@pytest.fixture
def setup_test_modules(tmp_path):
    """Create test module versions for rollback testing."""
    modules_dir = tmp_path / "modules"
    finance_cibc = modules_dir / "finance" / "cibc"
    finance_cibc.mkdir(parents=True)

    # Create v1 adapter (original)
    v1_adapter = '''
"""CIBC adapter v1."""
from shared.adapters.base import BaseAdapter

class CibcAdapter(BaseAdapter):
    VERSION = "1.0.0"

    def fetch_raw(self):
        return {"transactions": []}

    def transform(self, raw):
        return []
'''
    (finance_cibc / "adapter.py").write_text(v1_adapter)

    # Create test file
    test_code = '''
"""Tests for CIBC adapter."""
import pytest

def test_version():
    from adapter import CibcAdapter
    assert CibcAdapter.VERSION == "1.0.0"
'''
    (finance_cibc / "test_adapter.py").write_text(test_code)

    # Create manifest
    manifest = {
        "name": "cibc",
        "category": "finance",
        "platform": "cibc",
        "version": "1.0.0"
    }
    (finance_cibc / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return {
        "modules_dir": modules_dir,
        "module_id": "finance/cibc",
        "module_dir": finance_cibc,
        "v1_adapter": v1_adapter
    }


@pytest.fixture
def version_manager(tmp_path, setup_test_modules):
    """Create VersionManager with test directories."""
    versions_dir = tmp_path / "versions"
    modules_dir = setup_test_modules["modules_dir"]
    return VersionManager(
        versions_dir=versions_dir,
        modules_dir=modules_dir,
        audit_log=None  # No audit for unit tests
    )


def test_register_version(version_manager, setup_test_modules):
    """Test registering a new validated version."""
    version = version_manager.register_version(
        module_id="finance/cibc",
        bundle_sha256="abc123def456",
        actor="test_user",
        source="generated",
        metadata={"build_job": "job-001"}
    )

    assert version.version_id == "v1"
    assert version.bundle_sha256 == "abc123def456"
    assert version.created_by == "test_user"
    assert version.status == "VALIDATED"
    assert version.source == "generated"
    assert version.metadata["build_job"] == "job-001"


def test_list_versions(version_manager):
    """Test listing all versions for a module."""
    # Register multiple versions
    version_manager.register_version("finance/cibc", "hash-v1", source="generated")
    version_manager.register_version("finance/cibc", "hash-v2", source="promoted_from_draft")

    versions = version_manager.list_versions("finance/cibc")

    assert len(versions) == 2
    assert versions[0].version_id == "v2"  # Newest first
    assert versions[1].version_id == "v1"


def test_list_versions_empty(version_manager):
    """Test listing versions for module with no history."""
    versions = version_manager.list_versions("missing/module")
    assert versions == []


def test_get_active_version_none(version_manager):
    """Test getting active version when none exists."""
    active = version_manager.get_active_version("finance/cibc")
    assert active is None


def test_rollback_to_version(version_manager, setup_test_modules):
    """Test rolling back to a prior version."""
    # Register v1
    v1 = version_manager.register_version(
        "finance/cibc",
        "hash-v1",
        source="generated"
    )

    # Update module to v2
    module_dir = setup_test_modules["module_dir"]
    v2_adapter = '''
"""CIBC adapter v2 with bug."""
from shared.adapters.base import BaseAdapter

class CibcAdapter(BaseAdapter):
    VERSION = "2.0.0"

    def fetch_raw(self):
        raise Exception("Bug in v2!")  # Introduced bug

    def transform(self, raw):
        return []
'''
    (module_dir / "adapter.py").write_text(v2_adapter)

    # Register v2
    v2 = version_manager.register_version(
        "finance/cibc",
        "hash-v2",
        source="promoted_from_draft"
    )

    # Mark v2 as active
    versions = version_manager.list_versions("finance/cibc")
    for v in versions:
        if v.version_id == "v2":
            v.status = "ACTIVE"

    module_versions_dir = version_manager.versions_dir / "finance_cibc"
    versions_file = module_versions_dir / "versions.json"
    data = json.loads(versions_file.read_text())
    data["versions"] = [v.to_dict() for v in versions]
    versions_file.write_text(json.dumps(data, indent=2))

    # Rollback to v1
    result = version_manager.rollback_to_version(
        module_id="finance/cibc",
        target_version_id="v1",
        actor="admin",
        reason="v2 has critical bug"
    )

    assert result["status"] == "success"
    assert result["from_version"] == "v2"
    assert result["to_version"] == "v1"
    assert result["bundle_sha256"] == "hash-v1"

    # Verify active version changed
    active = version_manager.get_active_version("finance/cibc")
    assert active is not None
    assert active.version_id == "v1"

    # Verify v1 code was restored
    restored_code = (module_dir / "adapter.py").read_text()
    assert "VERSION = \"1.0.0\"" in restored_code
    assert "Bug in v2!" not in restored_code

    # Verify v2 still exists (not deleted)
    all_versions = version_manager.list_versions("finance/cibc")
    assert len(all_versions) == 2
    v2_version = next(v for v in all_versions if v.version_id == "v2")
    assert v2_version.status == "VALIDATED"  # Changed from ACTIVE


def test_rollback_to_missing_version(version_manager):
    """Test rollback to non-existent version fails."""
    version_manager.register_version("finance/cibc", "hash-v1")

    result = version_manager.rollback_to_version(
        module_id="finance/cibc",
        target_version_id="v99",
        actor="admin"
    )

    assert result["status"] == "error"
    assert "not found" in result["error"].lower()


def test_rollback_preserves_all_versions(version_manager, setup_test_modules):
    """Test that rollback doesn't delete any versions."""
    # Create 3 versions
    version_manager.register_version("finance/cibc", "hash-v1")
    version_manager.register_version("finance/cibc", "hash-v2")
    version_manager.register_version("finance/cibc", "hash-v3")

    # Rollback v3 -> v1
    version_manager.rollback_to_version("finance/cibc", "v1")

    # All 3 versions should still exist
    versions = version_manager.list_versions("finance/cibc")
    assert len(versions) == 3
    assert {v.version_id for v in versions} == {"v1", "v2", "v3"}

    # v1 should be active
    active = version_manager.get_active_version("finance/cibc")
    assert active.version_id == "v1"


def test_multiple_rollbacks(version_manager, setup_test_modules):
    """Test multiple rollback operations."""
    # Create versions
    version_manager.register_version("finance/cibc", "hash-v1")
    version_manager.register_version("finance/cibc", "hash-v2")
    version_manager.register_version("finance/cibc", "hash-v3")

    # Rollback v3 -> v2
    result1 = version_manager.rollback_to_version("finance/cibc", "v2")
    assert result1["status"] == "success"
    active1 = version_manager.get_active_version("finance/cibc")
    assert active1.version_id == "v2"

    # Rollback v2 -> v1
    result2 = version_manager.rollback_to_version("finance/cibc", "v1")
    assert result2["status"] == "success"
    active2 = version_manager.get_active_version("finance/cibc")
    assert active2.version_id == "v1"

    # Rollback v1 -> v3 (forward rollback)
    result3 = version_manager.rollback_to_version("finance/cibc", "v3")
    assert result3["status"] == "success"
    active3 = version_manager.get_active_version("finance/cibc")
    assert active3.version_id == "v3"


def test_get_version_files(version_manager, setup_test_modules):
    """Test retrieving file contents for a specific version."""
    # Register version
    version_manager.register_version("finance/cibc", "hash-v1")

    # Get files
    files = version_manager.get_version_files("finance/cibc", "v1")

    assert files is not None
    assert "adapter.py" in files
    assert "test_adapter.py" in files
    assert "manifest.json" in files
    assert "VERSION = \"1.0.0\"" in files["adapter.py"]


def test_get_version_files_missing(version_manager):
    """Test retrieving files for non-existent version."""
    files = version_manager.get_version_files("finance/cibc", "v99")
    assert files is None


def test_version_record_serialization():
    """Test VersionRecord to_dict and from_dict."""
    record = VersionRecord(
        version_id="v1",
        bundle_sha256="abc123",
        created_at="2026-02-16T00:00:00Z",
        created_by="test_user",
        status="ACTIVE",
        source="generated",
        metadata={"key": "value"}
    )

    # Serialize
    data = record.to_dict()
    assert data["version_id"] == "v1"
    assert data["bundle_sha256"] == "abc123"
    assert data["metadata"]["key"] == "value"

    # Deserialize
    restored = VersionRecord.from_dict(data)
    assert restored.version_id == "v1"
    assert restored.bundle_sha256 == "abc123"
    assert restored.metadata["key"] == "value"


def test_rollback_instant_no_rebuild(version_manager, setup_test_modules):
    """Test that rollback is instant pointer movement, not rebuild."""
    import time

    # Register v1
    version_manager.register_version("finance/cibc", "hash-v1")

    # Update to v2
    module_dir = setup_test_modules["module_dir"]
    (module_dir / "adapter.py").write_text("# v2 code")
    version_manager.register_version("finance/cibc", "hash-v2")

    # Measure rollback time (should be instant, <1 second)
    start = time.time()
    result = version_manager.rollback_to_version("finance/cibc", "v1")
    duration = time.time() - start

    assert result["status"] == "success"
    assert duration < 1.0  # Rollback should be near-instant (file copy only)

    # Verify v1 code restored
    restored_code = (module_dir / "adapter.py").read_text()
    assert "VERSION = \"1.0.0\"" in restored_code
