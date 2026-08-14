"""
Integration test: full validate -> approve -> install(attestation) chain.

Regression test for CR-01 (08-REVIEW.md): approve_module() used to rewrite
manifest.json, which was inside the hashed bundle the installer verified —
so an attested install of a legitimately approved module always failed with
"Artifact integrity failure: bundle hash mismatch". This test exercises the
real transition sequence against a single on-disk module (not a
pre-fabricated APPROVED fixture) to lock the fix in place.

Also covers WR-01 (post-approval tampering must be caught unconditionally)
and the fail-closed guard for pre-fix manifests with no recorded approval
hash (T-08-08).
"""
import importlib

import pytest
from unittest.mock import MagicMock, patch

from shared.modules.artifacts import compute_code_bundle_hash
from shared.modules.approval import approve_module
from shared.modules.manifest import ModuleManifest, ModuleStatus


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
    """Setup installer dependencies with temp dirs, mirroring
    test_installer_approval_guard.py's fixture style."""
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


def _write_module(modules_dir, module_id: str, status: str):
    """Write a module manifest + code files directly to disk (no installer
    dependency), mirroring a real build_module() -> validate_module() output."""
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
    (module_dir / "adapter.py").write_text(
        "from shared.adapters.base import BaseAdapter, register_adapter\n\n"
        "@register_adapter\n"
        "class DemoAdapter(BaseAdapter):\n"
        "    def fetch_raw(self):\n"
        "        return {'data': 'test'}\n\n"
        "    def transform(self, raw):\n"
        "        return raw\n\n"
        "    def get_schema(self):\n"
        "        return {'type': 'object'}\n"
    )
    (module_dir / "test_adapter.py").write_text("def test_adapter():\n    assert True\n")
    return module_dir


@pytest.fixture
def stub_audit_log():
    log = MagicMock()
    log.log_action = MagicMock()
    return log


class TestApprovalAttestationChain:
    """CR-01 regression: validate -> approve -> install(attestation) chain."""

    def test_attested_install_after_approval_gets_past_integrity_check(
        self, setup_installer_deps, temp_modules_dir, stub_audit_log
    ):
        module_id = "test/chain_ok"
        module_dir = _write_module(temp_modules_dir, module_id, ModuleStatus.VALIDATED.value)

        # Capture a validate-time attestation, exactly as validate_module()
        # would when it hashes the freshly-scaffolded code bundle.
        attestation = {"bundle_sha256": compute_code_bundle_hash(module_dir, module_id)}

        approve_result = approve_module(
            module_id=module_id,
            actor="admin1",
            audit_log=stub_audit_log,
            modules_dir=temp_modules_dir,
        )
        assert approve_result["status"] == "success"

        result = setup_installer_deps.install_module(module_id, validation_attestation=attestation)

        # The loader may legitimately be unavailable/behave oddly in a unit
        # environment; assert on the ABSENCE of an integrity/approval error
        # rather than overall install success (per plan Task 2 spec).
        error_text = str(result.get("error", ""))
        assert "integrity" not in error_text.lower()
        assert "not been approved" not in error_text
        assert "missing_approval_hash" not in error_text

    def test_tampering_after_approval_is_rejected(
        self, setup_installer_deps, temp_modules_dir, stub_audit_log
    ):
        module_id = "test/chain_tamper"
        module_dir = _write_module(temp_modules_dir, module_id, ModuleStatus.VALIDATED.value)

        attestation = {"bundle_sha256": compute_code_bundle_hash(module_dir, module_id)}

        approve_result = approve_module(
            module_id=module_id,
            actor="admin1",
            audit_log=stub_audit_log,
            modules_dir=temp_modules_dir,
        )
        assert approve_result["status"] == "success"

        # Tamper with adapter.py after approval.
        adapter_file = module_dir / "adapter.py"
        adapter_file.write_text(adapter_file.read_text() + "\n# tampered after approval\n")

        result = setup_installer_deps.install_module(module_id, validation_attestation=attestation)

        assert result["status"] == "error"
        assert "integrity" in result["error"].lower()

    def test_tampering_rejected_even_without_attestation(
        self, setup_installer_deps, temp_modules_dir, stub_audit_log
    ):
        """WR-01: the default (unattested) install path must also catch
        post-approval tampering — hash verification is unconditional."""
        module_id = "test/chain_tamper_no_attestation"
        module_dir = _write_module(temp_modules_dir, module_id, ModuleStatus.VALIDATED.value)

        approve_result = approve_module(
            module_id=module_id,
            actor="admin1",
            audit_log=stub_audit_log,
            modules_dir=temp_modules_dir,
        )
        assert approve_result["status"] == "success"

        adapter_file = module_dir / "adapter.py"
        adapter_file.write_text(adapter_file.read_text() + "\n# tampered\n")

        result = setup_installer_deps.install_module(module_id)

        assert result["status"] == "error"
        assert "integrity" in result["error"].lower()

    def test_pre_fix_approved_manifest_with_no_hash_requires_reapproval(
        self, setup_installer_deps, temp_modules_dir
    ):
        """T-08-08 fail-closed: an APPROVED manifest with a blank
        approved_bundle_sha256 (pre-fix data) must be refused, not trusted."""
        module_id = "test/pre_fix_manifest"
        module_dir = _write_module(temp_modules_dir, module_id, ModuleStatus.APPROVED.value)
        # Deliberately leave approved_bundle_sha256 at its default "" —
        # simulates a manifest approved before this integrity binding shipped.
        manifest = ModuleManifest.load(module_dir / "manifest.json")
        assert manifest.approved_bundle_sha256 == ""

        result = setup_installer_deps.install_module(module_id)

        assert result["status"] == "error"
        assert "re-approval" in result["error"] or "re-approve" in result["error"]
