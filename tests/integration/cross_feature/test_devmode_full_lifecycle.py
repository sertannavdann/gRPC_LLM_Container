"""
Cross-feature integration test: Dev-mode full lifecycle.

Verifies draft management, sandbox validation, version recording,
and rollback — all with auditing across component boundaries.

Components integrated:
- shared/modules/drafts.py (DraftManager)
- shared/modules/versioning.py (VersionManager)
- shared/modules/artifacts.py (ArtifactBundleBuilder)
- shared/modules/audit.py (DevModeAuditLog)
"""
import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock

from shared.modules.drafts import DraftManager, DraftState
from shared.modules.versioning import VersionManager
from shared.modules.artifacts import ArtifactBundleBuilder
from shared.modules.audit import DevModeAuditLog
from shared.modules.manifest import ModuleStatus

from conftest import create_test_module


class TestDevModeFullLifecycle:

    def test_draft_edit_validate_promote_version_record(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Full lifecycle: create -> edit -> validate -> promote -> version recorded."""
        modules_dir = temp_workspace["modules_dir"]
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"])

        create_test_module(
            modules_dir, "test/lifecycle", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
            audit_log=audit_log,
        )
        vm = VersionManager(
            db_path=temp_workspace["db_path"],
            audit_log=audit_log,
        )

        # Create draft
        create_result = dm.create_draft("test/lifecycle", actor="dev1")
        assert create_result["status"] == "success"
        draft_id = create_result["draft_id"]

        # Edit adapter
        edited_code = valid_adapter_code.replace("celsius", "fahrenheit")
        edit_result = dm.edit_file(draft_id, "adapter.py", edited_code, actor="dev1")
        assert edit_result["status"] == "success"

        # Validate with mock validator that passes
        validator_func = MagicMock(return_value={
            "status": "success",
            "report": {"self_check": "passed", "static_results": []},
        })
        val_result = dm.validate_draft(
            draft_id, actor="dev1", validator_func=validator_func,
        )
        assert val_result["status"] == "success"
        assert val_result["bundle_sha256"] is not None

        # Record version
        v_id = vm.record_version(
            module_id="test/lifecycle",
            bundle_sha256=val_result["bundle_sha256"],
            actor="dev1",
            source="draft_promoted",
        )

        # Promote with mock installer
        installer_func = MagicMock(return_value={"status": "success"})
        promo_result = dm.promote_draft(
            draft_id, actor="dev1", installer_func=installer_func,
        )
        assert promo_result["status"] == "success"

        # Verify version is recorded
        active = vm.get_active_version("test/lifecycle")
        assert active is not None
        assert active.bundle_sha256 == val_result["bundle_sha256"]

        # Verify audit events
        events = audit_log.get_events()
        actions = [e.action for e in events]
        assert "draft_created" in actions
        assert "draft_edited" in actions
        assert "draft_validated" in actions
        assert "draft_promoted" in actions

    def test_promote_then_rollback_restores_prior_version(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Promote draft, then rollback to original version."""
        modules_dir = temp_workspace["modules_dir"]
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"])

        create_test_module(
            modules_dir, "test/rollback", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        vm = VersionManager(
            db_path=temp_workspace["db_path"],
            audit_log=audit_log,
        )

        # Record v1
        v1_id = vm.record_version(
            module_id="test/rollback",
            bundle_sha256="aaa111",
            actor="system",
            source="generated",
        )

        # Small delay to ensure unique version_id timestamps
        time.sleep(0.01)

        # Record v2 (simulates promoted draft)
        v2_id = vm.record_version(
            module_id="test/rollback",
            bundle_sha256="bbb222",
            actor="dev1",
            source="draft_promoted",
        )

        # Active should be v1 (first recorded gets active pointer)
        active = vm.get_active_version("test/rollback")
        assert active is not None
        assert active.version_id == v1_id

        # Rollback to v2 (to test the other direction too)
        result = vm.rollback_to_version(
            "test/rollback", v2_id, actor="admin", reason="Testing v2",
        )
        assert result["status"] == "success"
        active = vm.get_active_version("test/rollback")
        assert active.bundle_sha256 == "bbb222"

        # Rollback back to v1
        result = vm.rollback_to_version(
            "test/rollback", v1_id, actor="admin", reason="Bug in v2",
        )
        assert result["status"] == "success"
        active = vm.get_active_version("test/rollback")
        assert active.bundle_sha256 == "aaa111"

        # Both versions still exist
        versions = vm.list_versions("test/rollback")
        assert len(versions) == 2

        # Verify rollback audit
        events = audit_log.get_events(action="version_rollback")
        assert len(events) >= 1

    def test_validation_failure_prevents_promotion(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Failed validation keeps draft in EDITING state, promotion rejected."""
        modules_dir = temp_workspace["modules_dir"]

        create_test_module(
            modules_dir, "test/failval", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
        )

        create_result = dm.create_draft("test/failval")
        draft_id = create_result["draft_id"]

        # Validate with failing mock
        validator_func = MagicMock(return_value={
            "status": "failed",
            "report": {"fix_hints": [{"category": "test_failure", "message": "test broke"}]},
        })
        val_result = dm.validate_draft(draft_id, validator_func=validator_func)
        assert val_result["status"] == "failed"

        # Draft should be back to EDITING
        draft = dm.get_draft(draft_id)
        assert draft.state == DraftState.EDITING

        # Promote should fail
        promo_result = dm.promote_draft(draft_id)
        assert promo_result["status"] == "error"
        assert "VALIDATED" in promo_result["error"]

    def test_bundle_sha256_consistency_across_draft_and_version(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """bundle_sha256 from validate_draft matches VersionManager record."""
        modules_dir = temp_workspace["modules_dir"]

        create_test_module(
            modules_dir, "test/hashconsist", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
        )
        vm = VersionManager(db_path=temp_workspace["db_path"])

        result = dm.create_draft("test/hashconsist")
        draft_id = result["draft_id"]

        # Edit
        edited = valid_adapter_code.replace("celsius", "kelvin")
        dm.edit_file(draft_id, "adapter.py", edited)

        # Validate
        validator_func = MagicMock(return_value={"status": "success", "report": {}})
        val_result = dm.validate_draft(draft_id, validator_func=validator_func)
        draft_hash = val_result["bundle_sha256"]

        # Record this hash in version manager
        v_id = vm.record_version(
            module_id="test/hashconsist",
            bundle_sha256=draft_hash,
            source="draft_promoted",
        )

        version = vm.get_version(v_id)
        assert version.bundle_sha256 == draft_hash

    def test_discarded_draft_cannot_be_promoted_or_validated(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Once discarded, draft operations fail gracefully."""
        modules_dir = temp_workspace["modules_dir"]
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"])

        create_test_module(
            modules_dir, "test/discard", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
            audit_log=audit_log,
        )

        result = dm.create_draft("test/discard")
        draft_id = result["draft_id"]

        dm.discard_draft(draft_id, actor="dev1")

        draft = dm.get_draft(draft_id)
        assert draft.state == DraftState.DISCARDED

        # Validate fails
        val_result = dm.validate_draft(draft_id)
        assert val_result["status"] == "error"
        assert "Cannot validate" in val_result["error"]

        # Promote fails
        promo_result = dm.promote_draft(draft_id)
        assert promo_result["status"] == "error"

        # Audit has discard event
        events = audit_log.get_events(action="draft_discarded")
        assert len(events) >= 1
