"""
Cross-feature integration test: Audit completeness.

Verifies that every pipeline stage produces audit records with correct
hashes and that the full audit trail is consistent across subsystems.

Components integrated:
- shared/modules/audit.py (BuildAuditLog, DevModeAuditLog, AttemptRecord)
- shared/modules/artifacts.py (ArtifactBundleBuilder)
- shared/modules/drafts.py (DraftManager)
- shared/modules/versioning.py (VersionManager)
"""
import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from shared.audit import AuditStore
from shared.modules.audit import (
    BuildAuditLog,
    AttemptRecord,
    AttemptStatus,
    FailureType,
    FailureFingerprint,
    DevModeAuditLog,
)
from shared.modules.artifacts import ArtifactBundleBuilder
from shared.modules.drafts import DraftManager
from shared.modules.versioning import VersionManager
from shared.modules.manifest import ModuleStatus

from conftest import create_test_module


class TestAuditCompleteness:

    def test_build_audit_log_captures_all_stages(self, tmp_path):
        """BuildAuditLog records for scaffold/implement/tests/repair — all preserved."""
        audit_log = BuildAuditLog(job_id="full-build", module_id="weather/openweather")

        stages = [
            ("scaffold", AttemptStatus.SUCCESS),
            ("implement", AttemptStatus.SUCCESS),
            ("tests", AttemptStatus.FAILED),
            ("repair", AttemptStatus.SUCCESS),
        ]

        for i, (stage, status) in enumerate(stages):
            record = AttemptRecord(
                attempt_number=i + 1,
                bundle_sha256=f"hash_{stage}_{i}",
                stage=stage,
                status=status,
            )
            audit_log.add_attempt(record)

        # Serialize and deserialize
        serialized = audit_log.to_dict()
        restored = BuildAuditLog.from_dict(serialized)

        assert len(restored.attempts) == 4
        for i, (stage, status) in enumerate(stages):
            assert restored.attempts[i].stage == stage
            assert restored.attempts[i].status == status
            assert restored.attempts[i].bundle_sha256 == f"hash_{stage}_{i}"

    def test_draft_lifecycle_audit_trail_complete(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Every DraftManager action produces a DevModeAuditLog event."""
        modules_dir = temp_workspace["modules_dir"]
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"])

        create_test_module(
            modules_dir, "test/auditlife", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
            audit_log=audit_log,
        )

        # Create
        result = dm.create_draft("test/auditlife", actor="dev1")
        draft_id = result["draft_id"]

        # Edit
        dm.edit_file(draft_id, "adapter.py", "class A: pass", actor="dev1")

        # Get diff
        dm.get_diff(draft_id, actor="dev1")

        # Validate (mock)
        validator_func = MagicMock(return_value={"status": "success", "report": {}})
        dm.validate_draft(draft_id, actor="dev1", validator_func=validator_func)

        # Create a second draft and discard it
        result2 = dm.create_draft("test/auditlife", actor="dev1")
        dm.discard_draft(result2["draft_id"], actor="dev1")

        # Check all events
        all_events = audit_log.get_events()
        actions = [e.action for e in all_events]

        assert "draft_created" in actions
        assert "draft_edited" in actions
        assert "draft_diff_viewed" in actions
        assert "draft_validated" in actions
        assert "draft_discarded" in actions
        assert len(all_events) >= 6  # 2 creates + edit + diff + validate + discard

    def test_version_rollback_audit_includes_from_and_to(self, temp_workspace):
        """Rollback events record from_version, to_version, reason."""
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"])
        vm = VersionManager(
            db_path=temp_workspace["db_path"],
            audit_log=audit_log,
        )

        v1_id = vm.record_version(
            module_id="test/rollaudit",
            bundle_sha256="hash_v1",
            actor="system",
        )
        time.sleep(0.01)

        v2_id = vm.record_version(
            module_id="test/rollaudit",
            bundle_sha256="hash_v2",
            actor="dev1",
        )

        # Rollback to v2 first (v1 is active by default)
        vm.rollback_to_version(
            "test/rollaudit", v2_id, actor="admin", reason="Testing v2",
        )
        # Then back to v1
        vm.rollback_to_version(
            "test/rollaudit", v1_id, actor="admin", reason="Bug in v2",
        )

        events = audit_log.get_events(action="version_rollback")
        assert len(events) >= 2

        last_event = events[-1]
        assert last_event.details["to_version"] == v1_id
        assert last_event.details["reason"] == "Bug in v2"
        assert "bundle_sha256" in last_event.details

    def test_install_success_and_rejection_produce_audit_entries(
        self, setup_installer, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Both successful and rejected installs produce JSONL audit entries."""
        modules_dir = temp_workspace["modules_dir"]
        audit_dir = temp_workspace["audit_dir"]

        # Successful install
        _, bundle_hash = create_test_module(
            modules_dir, "test/auditsuccess", valid_adapter_code, valid_test_code,
            ModuleStatus.APPROVED.value,
        )
        attestation = {"bundle_sha256": bundle_hash, "status": "APPROVED"}
        result = setup_installer.install_module("test/auditsuccess", attestation)
        assert result["status"] == "success"

        success_file = audit_dir / "install_success.jsonl"
        assert success_file.exists()
        entries = [json.loads(line) for line in success_file.read_text().splitlines()]
        assert any(e["module_id"] == "test/auditsuccess" for e in entries)

        # Rejected install (non-validated)
        create_test_module(
            modules_dir, "test/auditreject", valid_adapter_code, valid_test_code,
            ModuleStatus.PENDING.value,
        )
        result = setup_installer.install_module("test/auditreject")
        assert result["status"] == "error"

        reject_file = audit_dir / "install_rejections.jsonl"
        assert reject_file.exists()
        entries = [json.loads(line) for line in reject_file.read_text().splitlines()]
        assert any(e["module_id"] == "test/auditreject" for e in entries)

    def test_audit_events_have_monotonic_timestamps(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """All events within a lifecycle have non-decreasing timestamps."""
        modules_dir = temp_workspace["modules_dir"]
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"])

        create_test_module(
            modules_dir, "test/timestamps", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
            audit_log=audit_log,
        )

        result = dm.create_draft("test/timestamps", actor="dev1")
        draft_id = result["draft_id"]
        dm.edit_file(draft_id, "adapter.py", "# edited", actor="dev1")
        dm.get_diff(draft_id, actor="dev1")
        dm.discard_draft(draft_id, actor="dev1")

        events = audit_log.get_events()
        timestamps = [e.timestamp for e in events]

        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Non-monotonic: {timestamps[i-1]} > {timestamps[i]}"
            )

    def test_failure_fingerprint_in_audit_matches_recomputed(self):
        """Fingerprint hash stored in AttemptRecord matches recomputed from report."""
        report = {
            "fix_hints": [
                {"category": "test_failure", "message": "test_fetch failed"},
                {"category": "missing_method", "message": "Missing get_schema"},
            ],
            "static_results": [{"name": "syntax", "passed": False}],
            "runtime_results": {"stderr": "FAIL: test_fetch", "stdout": ""},
        }

        fp = FailureFingerprint.from_validation_report(report)

        record = AttemptRecord(
            attempt_number=1,
            bundle_sha256="test_hash",
            stage="repair",
            status=AttemptStatus.FAILED,
            validation_report=report,
            failure_fingerprint=fp.hash,
        )

        audit_log = BuildAuditLog(job_id="fp-test", module_id="t/m")
        audit_log.add_attempt(record)

        # Round-trip
        serialized = audit_log.to_dict()
        restored = BuildAuditLog.from_dict(serialized)

        stored_fp = restored.attempts[0].failure_fingerprint
        stored_report = restored.attempts[0].validation_report
        recomputed_fp = FailureFingerprint.from_validation_report(stored_report)

        assert stored_fp == recomputed_fp.hash

    def test_audit_log_save_and_load_round_trip(self, tmp_path):
        """BuildAuditLog survives save -> load with all data intact."""
        audit_log = BuildAuditLog(
            job_id="roundtrip-test",
            module_id="weather/test",
        )

        for i in range(3):
            record = AttemptRecord(
                attempt_number=i + 1,
                bundle_sha256=f"hash_{i}",
                stage=["scaffold", "implement", "repair"][i],
                status=[AttemptStatus.SUCCESS, AttemptStatus.SUCCESS, AttemptStatus.FAILED][i],
                failure_fingerprint="fp_abc" if i == 2 else None,
                failure_type=FailureType.TEST_FAILURE if i == 2 else None,
                metadata={"model": "gpt-4o", "tokens": 1000 + i},
            )
            audit_log.add_attempt(record)

        audit_log.final_status = "FAILED"

        # Save
        saved_path = audit_log.save(tmp_path)
        assert saved_path.exists()

        # Load
        loaded = BuildAuditLog.load(saved_path)

        assert loaded.job_id == "roundtrip-test"
        assert loaded.module_id == "weather/test"
        assert loaded.final_status == "FAILED"
        assert len(loaded.attempts) == 3

        assert loaded.attempts[0].stage == "scaffold"
        assert loaded.attempts[0].status == AttemptStatus.SUCCESS
        assert loaded.attempts[2].failure_fingerprint == "fp_abc"
        assert loaded.attempts[2].failure_type == FailureType.TEST_FAILURE
        assert loaded.attempts[2].metadata["model"] == "gpt-4o"


class TestAuditSQLiteParity:
    """
    D-01 dual-write parity (Phase 07-02 Task 3): every DevModeAuditLog
    JSONL event produced during the draft/version lifecycle must have a
    matching row in the SQLite audit_events store, cross-referenced by
    jsonl_event_id — not just present in the JSONL file.
    """

    @staticmethod
    def _assert_parity(jsonl_events, sqlite_store, action: str) -> None:
        """Every JSONL event with `action` has exactly one SQLite row whose
        details.jsonl_event_id matches, and core fields agree."""
        matching_jsonl = [e for e in jsonl_events if e.action == action]
        assert matching_jsonl, f"No JSONL events found for action={action!r}"

        sqlite_rows = sqlite_store.query(action=action, limit=1000)
        sqlite_by_event_id = {
            row["details"]["jsonl_event_id"]: row
            for row in sqlite_rows
            if row.get("details") and "jsonl_event_id" in row["details"]
        }

        for jsonl_event in matching_jsonl:
            assert jsonl_event.event_id in sqlite_by_event_id, (
                f"JSONL event {jsonl_event.event_id} (action={action!r}) has no "
                f"SQLite parity row"
            )
            sqlite_row = sqlite_by_event_id[jsonl_event.event_id]
            assert sqlite_row["actor_id"] == jsonl_event.actor
            assert sqlite_row["details"]["module_id"] == jsonl_event.module_id
            assert sqlite_row["details"]["draft_id"] == jsonl_event.draft_id

    def test_draft_lifecycle_sqlite_parity(
        self, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Every DraftManager action's JSONL event has a matching SQLite row."""
        modules_dir = temp_workspace["modules_dir"]
        sqlite_store = AuditStore(db_path=str(Path(temp_workspace["audit_dir"]) / "audit_events.db"))
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"], sink=sqlite_store)

        create_test_module(
            modules_dir, "test/sqliteparity", valid_adapter_code, valid_test_code,
            ModuleStatus.VALIDATED.value,
        )

        dm = DraftManager(
            drafts_dir=temp_workspace["drafts_dir"],
            modules_dir=modules_dir,
            audit_log=audit_log,
        )

        result = dm.create_draft("test/sqliteparity", actor="dev1")
        draft_id = result["draft_id"]
        dm.edit_file(draft_id, "adapter.py", "class A: pass", actor="dev1")
        dm.get_diff(draft_id, actor="dev1")
        validator_func = MagicMock(return_value={"status": "success", "report": {}})
        dm.validate_draft(draft_id, actor="dev1", validator_func=validator_func)

        result2 = dm.create_draft("test/sqliteparity", actor="dev1")
        dm.discard_draft(result2["draft_id"], actor="dev1")

        all_events = audit_log.get_events()

        for action in (
            "draft_created",
            "draft_edited",
            "draft_diff_viewed",
            "draft_validated",
            "draft_discarded",
        ):
            self._assert_parity(all_events, sqlite_store, action)

        # Row count parity: same number of rows on both sides for this module.
        sqlite_total = sqlite_store.count()
        assert sqlite_total == len(all_events)

    def test_version_rollback_sqlite_parity(self, temp_workspace):
        """Rollback JSONL events have matching SQLite rows with from/to/reason in details."""
        sqlite_store = AuditStore(db_path=str(Path(temp_workspace["audit_dir"]) / "audit_events.db"))
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"], sink=sqlite_store)
        vm = VersionManager(
            db_path=temp_workspace["db_path"],
            audit_log=audit_log,
        )

        v1_id = vm.record_version(
            module_id="test/rollparity", bundle_sha256="hash_v1", actor="system",
        )
        time.sleep(0.01)
        v2_id = vm.record_version(
            module_id="test/rollparity", bundle_sha256="hash_v2", actor="dev1",
        )

        vm.rollback_to_version("test/rollparity", v2_id, actor="admin", reason="Testing v2")
        vm.rollback_to_version("test/rollparity", v1_id, actor="admin", reason="Bug in v2")

        all_events = audit_log.get_events()
        self._assert_parity(all_events, sqlite_store, "version_rollback")

        rollback_sqlite_rows = sqlite_store.query(action="version_rollback")
        assert any(
            row["details"].get("reason") == "Bug in v2" for row in rollback_sqlite_rows
        )

    def test_sink_failure_propagates_and_stops_lifecycle_action(self, temp_workspace, monkeypatch):
        """A broken SQLite sink raises out of log_action() (D-03 fail-closed) —
        the JSONL side still recorded the event, but the caller sees the failure."""
        from shared.audit import AuditWriteError

        sqlite_store = AuditStore(db_path=str(Path(temp_workspace["audit_dir"]) / "audit_events.db"))
        audit_log = DevModeAuditLog(temp_workspace["audit_dir"], sink=sqlite_store)

        def _boom(*args, **kwargs):
            raise AuditWriteError("sink unavailable")

        monkeypatch.setattr(sqlite_store, "record", _boom)

        with pytest.raises(AuditWriteError):
            audit_log.log_action(action="draft_created", actor="dev1", module_id="test/sinkfail")

        # JSONL append happens before the sink call, so the event is still there.
        assert len(audit_log.get_events()) == 1
