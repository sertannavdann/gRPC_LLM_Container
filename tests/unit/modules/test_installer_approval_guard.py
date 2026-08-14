"""
Unit tests for the install-time approval guard (D-16).

Verifies install_module() refuses any module whose manifest.status is not
APPROVED, and clears the guard once status is APPROVED. Also covers the
ApprovalPolicy scaffold's hard default (D-18).

Uses tmp_path fixtures for filesystem isolation, mirroring the
tmp_path/manifest fixture approach used across shared/modules unit tests.
"""
import importlib

import pytest
from unittest.mock import MagicMock, patch

from shared.modules.artifacts import compute_code_bundle_hash
from shared.modules.manifest import ModuleManifest, ModuleStatus
from shared.modules.policy import ApprovalPolicy, DEFAULT_APPROVAL_POLICY


@pytest.fixture
def temp_modules_dir(tmp_path):
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    return modules_dir


@pytest.fixture
def temp_audit_dir(tmp_path):
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    return audit_dir


@pytest.fixture
def mock_loader():
    loader = MagicMock()
    handle = MagicMock()
    handle.is_loaded = True
    handle.error = None
    loader.load_module.return_value = handle
    return loader


@pytest.fixture
def setup_installer_deps(mock_loader, temp_modules_dir, temp_audit_dir):
    """Setup installer dependencies with temp dirs, mirroring test_validated_only_guard.py."""
    with patch.dict("os.environ", {
        "MODULES_DIR": str(temp_modules_dir),
        "AUDIT_DIR": str(temp_audit_dir),
    }):
        from tools.builtin import module_installer
        importlib.reload(module_installer)

        module_installer.set_installer_deps(
            loader=mock_loader,
            registry=MagicMock(),
            credential_store=MagicMock(),
        )

        yield module_installer

        module_installer._module_loader = None
        module_installer._module_registry = None


def _create_module(modules_dir, module_id: str, status: str) -> None:
    category, platform = module_id.split("/")
    manifest = ModuleManifest(
        name=platform,
        category=category,
        platform=platform,
        status=status,
        display_name=platform.title(),
    )
    manifest.save(modules_dir)

    module_dir = modules_dir / category / platform
    (module_dir / "adapter.py").write_text("class A: pass\n")
    (module_dir / "test_adapter.py").write_text("def test_a(): assert True\n")

    if status == ModuleStatus.APPROVED.value:
        # Approval-time hash must be recorded for the unconditional install
        # guard (CR-01/WR-01) to accept this module.
        manifest.approved_bundle_sha256 = compute_code_bundle_hash(module_dir, module_id)
        manifest.save(modules_dir)


class TestInstallGuardRequiresApproved:
    def test_validated_status_is_rejected(self, setup_installer_deps, temp_modules_dir):
        """A VALIDATED (but not yet APPROVED) module must be rejected (D-16)."""
        _create_module(temp_modules_dir, "test/pending_approval", ModuleStatus.VALIDATED.value)

        result = setup_installer_deps.install_module("test/pending_approval")

        assert result["status"] == "error"
        assert "not been approved" in result["error"]

    def test_validated_status_rejection_logs_not_approved_reason(
        self, setup_installer_deps, temp_modules_dir, temp_audit_dir
    ):
        import json

        _create_module(temp_modules_dir, "test/reason_check", ModuleStatus.VALIDATED.value)
        setup_installer_deps.install_module("test/reason_check")

        audit_file = temp_audit_dir / "install_rejections.jsonl"
        assert audit_file.exists()
        entries = [json.loads(line) for line in audit_file.read_text().splitlines()]
        last_entry = entries[-1]
        assert last_entry["module_id"] == "test/reason_check"
        assert last_entry["reason"] == "not_approved"

    def test_approved_status_clears_guard(self, setup_installer_deps, temp_modules_dir, mock_loader):
        """An APPROVED module proceeds past the status guard and installs."""
        _create_module(temp_modules_dir, "test/approved_mod", ModuleStatus.APPROVED.value)

        result = setup_installer_deps.install_module("test/approved_mod")

        assert result["status"] == "success"
        assert result["is_loaded"] is True
        mock_loader.load_module.assert_called_once()

    def test_pending_status_is_rejected(self, setup_installer_deps, temp_modules_dir):
        """A PENDING module (never validated) is also rejected by the APPROVED guard."""
        _create_module(temp_modules_dir, "test/pending_mod", ModuleStatus.PENDING.value)

        result = setup_installer_deps.install_module("test/pending_mod")

        assert result["status"] == "error"
        assert "not been approved" in result["error"]


class TestApprovalPolicyScaffold:
    def test_auto_approve_defaults_false(self):
        assert ApprovalPolicy().auto_approve is False

    def test_auto_approve_can_be_overridden(self):
        assert ApprovalPolicy(auto_approve=True).auto_approve is True

    def test_default_policy_singleton_is_hard_default(self):
        assert DEFAULT_APPROVAL_POLICY.auto_approve is False

    def test_scaffold_fields_present(self):
        policy = ApprovalPolicy()
        assert policy.trusted_categories == []
        assert policy.require_all_tests_pass is True
