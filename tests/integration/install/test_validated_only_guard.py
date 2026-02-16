"""
Integration test: Install attestation guard.

Verifies that:
1. Validated bundles install successfully
2. Non-validated bundles are rejected
3. Tampered bundles (hash mismatch) are rejected
4. Install success/rejection creates audit records
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.modules.manifest import ModuleManifest, ModuleStatus
from shared.modules.artifacts import ArtifactBundleBuilder
from tools.builtin import module_installer


@pytest.fixture
def temp_modules_dir(tmp_path):
    """Create temporary modules directory."""
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    return modules_dir


@pytest.fixture
def temp_audit_dir(tmp_path):
    """Create temporary audit directory."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    return audit_dir


@pytest.fixture
def mock_loader():
    """Create mock module loader."""
    loader = MagicMock()
    handle = MagicMock()
    handle.is_loaded = True
    handle.error = None
    loader.load_module.return_value = handle
    return loader


@pytest.fixture
def mock_registry():
    """Create mock module registry."""
    registry = MagicMock()
    return registry


@pytest.fixture
def setup_installer_deps(mock_loader, mock_registry, temp_modules_dir, temp_audit_dir):
    """Setup installer dependencies with temp directories."""
    # Patch environment variables
    with patch.dict('os.environ', {
        'MODULES_DIR': str(temp_modules_dir),
        'AUDIT_DIR': str(temp_audit_dir)
    }):
        # Reload module_installer to pick up new env vars
        import importlib
        importlib.reload(module_installer)

        # Set dependencies
        module_installer.set_installer_deps(
            loader=mock_loader,
            registry=mock_registry,
            credential_store=MagicMock()
        )

        yield

        # Cleanup
        module_installer._module_loader = None
        module_installer._module_registry = None


def create_test_module(modules_dir: Path, module_id: str, status: str) -> tuple:
    """
    Create test module with manifest and files.

    Returns:
        Tuple of (manifest, bundle_sha256)
    """
    category, platform = module_id.split("/")
    module_dir = modules_dir / category / platform
    module_dir.mkdir(parents=True)

    # Create manifest
    manifest = ModuleManifest(
        name=platform,
        category=category,
        platform=platform,
        status=status,
        display_name=platform.title(),
    )
    manifest.save(modules_dir)

    # Create adapter and test files
    adapter_code = f'''
from shared.adapters.base import BaseAdapter, register_adapter

@register_adapter
class {platform.title()}Adapter(BaseAdapter):
    def fetch_raw(self):
        return {{"data": "test"}}

    def transform(self, raw):
        return raw

    def get_schema(self):
        return {{"type": "object"}}
'''

    test_code = f'''
def test_adapter():
    assert True
'''

    (module_dir / "adapter.py").write_text(adapter_code)
    (module_dir / "test_adapter.py").write_text(test_code)

    # Compute bundle hash
    bundle = ArtifactBundleBuilder.build_from_dict(
        files={
            f"{category}/{platform}/manifest.json": (module_dir / "manifest.json").read_text(),
            f"{category}/{platform}/adapter.py": adapter_code,
            f"{category}/{platform}/test_adapter.py": test_code,
        },
        job_id="test",
        attempt_id=1,
        module_id=module_id
    )

    return manifest, bundle.bundle_sha256


def test_validated_bundle_installs_successfully(setup_installer_deps, temp_modules_dir):
    """Test that a validated bundle installs successfully."""
    manifest, bundle_hash = create_test_module(
        temp_modules_dir, "test/validated", ModuleStatus.VALIDATED.value
    )

    attestation = {
        "bundle_sha256": bundle_hash,
        "status": "VALIDATED",
    }

    result = module_installer.install_module("test/validated", attestation)

    assert result["status"] == "success"
    assert result["module_id"] == "test/validated"
    assert result["is_loaded"] is True


def test_non_validated_bundle_rejected(setup_installer_deps, temp_modules_dir):
    """Test that a non-validated bundle is rejected."""
    manifest, bundle_hash = create_test_module(
        temp_modules_dir, "test/pending", ModuleStatus.PENDING.value
    )

    result = module_installer.install_module("test/pending")

    assert result["status"] == "error"
    assert "not been validated" in result["error"]


def test_failed_bundle_rejected(setup_installer_deps, temp_modules_dir):
    """Test that a failed bundle is rejected."""
    manifest, bundle_hash = create_test_module(
        temp_modules_dir, "test/failed", ModuleStatus.FAILED.value
    )

    result = module_installer.install_module("test/failed")

    assert result["status"] == "error"
    assert "failed validation" in result["error"]


def test_tampered_bundle_hash_mismatch_rejected(setup_installer_deps, temp_modules_dir):
    """Test that a tampered bundle (hash mismatch) is rejected."""
    manifest, original_hash = create_test_module(
        temp_modules_dir, "test/tampered", ModuleStatus.VALIDATED.value
    )

    # Tamper with the file
    category, platform = "test", "tampered"
    adapter_file = temp_modules_dir / category / platform / "adapter.py"
    adapter_file.write_text(adapter_file.read_text() + "\n# Tampered!")

    # Try to install with original attestation
    attestation = {
        "bundle_sha256": original_hash,
        "status": "VALIDATED",
    }

    result = module_installer.install_module("test/tampered", attestation)

    assert result["status"] == "error"
    assert "integrity failure" in result["error"]
    assert "hash mismatch" in result["error"]


def test_install_success_creates_audit_record(setup_installer_deps, temp_modules_dir, temp_audit_dir):
    """Test that successful install creates audit record."""
    manifest, bundle_hash = create_test_module(
        temp_modules_dir, "test/audit_success", ModuleStatus.VALIDATED.value
    )

    attestation = {
        "bundle_sha256": bundle_hash,
        "status": "VALIDATED",
    }

    result = module_installer.install_module("test/audit_success", attestation)

    assert result["status"] == "success"

    # Check audit file exists
    audit_file = temp_audit_dir / "install_success.jsonl"
    assert audit_file.exists()

    # Verify audit entry
    with open(audit_file) as f:
        entries = [json.loads(line) for line in f]

    assert len(entries) >= 1
    last_entry = entries[-1]
    assert last_entry["module_id"] == "test/audit_success"
    assert last_entry["action"] == "install_success"
    assert last_entry["bundle_sha256"] == bundle_hash


def test_install_rejection_creates_audit_record(setup_installer_deps, temp_modules_dir, temp_audit_dir):
    """Test that install rejection creates audit record."""
    manifest, bundle_hash = create_test_module(
        temp_modules_dir, "test/audit_reject", ModuleStatus.PENDING.value
    )

    result = module_installer.install_module("test/audit_reject")

    assert result["status"] == "error"

    # Check audit file exists
    audit_file = temp_audit_dir / "install_rejections.jsonl"
    assert audit_file.exists()

    # Verify audit entry
    with open(audit_file) as f:
        entries = [json.loads(line) for line in f]

    assert len(entries) >= 1
    last_entry = entries[-1]
    assert last_entry["module_id"] == "test/audit_reject"
    assert last_entry["action"] == "install_rejected"
    assert last_entry["reason"] == "not_validated"


def test_missing_attestation_hash_rejected(setup_installer_deps, temp_modules_dir):
    """Test that attestation without bundle_sha256 is rejected."""
    manifest, bundle_hash = create_test_module(
        temp_modules_dir, "test/no_hash", ModuleStatus.VALIDATED.value
    )

    # Attestation without bundle_sha256
    attestation = {
        "status": "VALIDATED",
    }

    result = module_installer.install_module("test/no_hash", attestation)

    assert result["status"] == "error"
    assert "missing bundle_sha256" in result["error"]
