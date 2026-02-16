"""
Cross-feature integration test: SHA-256 hash chain integrity.

Verifies that content-addressed hashes flow immutably from artifact creation
through validation attestation to the install guard, and that any tampering
is detected.

Components integrated:
- shared/modules/artifacts.py
- tools/builtin/module_installer.py
- shared/modules/audit.py
"""
import pytest
import json
from pathlib import Path

from shared.modules.artifacts import ArtifactBundleBuilder, ArtifactIndex, verify_bundle_hash
from shared.modules.audit import BuildAuditLog, AttemptRecord, AttemptStatus
from shared.modules.manifest import ModuleStatus

from conftest import create_test_module


class TestHashChainIntegrity:

    def test_bundle_hash_stable_across_build_validate_install(
        self, setup_installer, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Build artifact bundle, use its hash as attestation, install succeeds."""
        modules_dir = temp_workspace["modules_dir"]
        manifest, bundle_hash = create_test_module(
            modules_dir, "test/hashcheck", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        attestation = {"bundle_sha256": bundle_hash, "status": "VALIDATED"}
        result = setup_installer.install_module("test/hashcheck", attestation)

        assert result["status"] == "success"
        assert result["module_id"] == "test/hashcheck"

    def test_single_byte_change_breaks_hash_chain(
        self, setup_installer, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Modify one byte after building bundle — install rejects."""
        modules_dir = temp_workspace["modules_dir"]
        manifest, original_hash = create_test_module(
            modules_dir, "test/tamper", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        # Tamper with adapter.py after hash was computed
        adapter_file = modules_dir / "test" / "tamper" / "adapter.py"
        adapter_file.write_text(adapter_file.read_text() + "\n# tampered")

        attestation = {"bundle_sha256": original_hash, "status": "VALIDATED"}
        result = setup_installer.install_module("test/tamper", attestation)

        assert result["status"] == "error"
        assert "hash mismatch" in result["error"]

    def test_hash_determinism_across_recomputation(self):
        """Build bundle twice from identical files — identical hashes."""
        files = {
            "weather/test/adapter.py": "class A: pass",
            "weather/test/test_adapter.py": "def test(): pass",
            "weather/test/manifest.json": '{"name": "test"}',
        }

        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=files, job_id="job-1", attempt_id=1, module_id="weather/test",
        )
        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=files, job_id="job-2", attempt_id=2, module_id="weather/test",
        )

        assert bundle1.bundle_sha256 == bundle2.bundle_sha256

    def test_bundle_diff_detects_file_changes(self):
        """diff_bundles identifies exactly which files changed."""
        original = {
            "w/t/adapter.py": "class A: pass",
            "w/t/test_adapter.py": "def test(): pass",
        }
        modified = {
            "w/t/adapter.py": "class A:\n    x = 1",
            "w/t/test_adapter.py": "def test(): pass",
        }

        b1 = ArtifactBundleBuilder.build_from_dict(
            files=original, job_id="j1", attempt_id=1, module_id="w/t",
        )
        b2 = ArtifactBundleBuilder.build_from_dict(
            files=modified, job_id="j2", attempt_id=1, module_id="w/t",
        )

        diff = ArtifactBundleBuilder.diff_bundles(b1, b2)
        assert diff["identical"] is False
        assert "w/t/adapter.py" in diff["changed"]
        assert "w/t/test_adapter.py" in diff["unchanged"]

    def test_audit_record_captures_bundle_hash(self, tmp_path):
        """AttemptRecord round-trips bundle_sha256."""
        files = {"a.py": "class A: pass"}
        bundle = ArtifactBundleBuilder.build_from_dict(
            files=files, job_id="audit-j", attempt_id=1, module_id="t/m",
        )

        record = AttemptRecord(
            attempt_number=1,
            bundle_sha256=bundle.bundle_sha256,
            stage="scaffold",
            status=AttemptStatus.SUCCESS,
        )

        audit_log = BuildAuditLog(job_id="audit-j", module_id="t/m")
        audit_log.add_attempt(record)

        serialized = audit_log.to_dict()
        restored = BuildAuditLog.from_dict(serialized)

        assert restored.attempts[0].bundle_sha256 == bundle.bundle_sha256
