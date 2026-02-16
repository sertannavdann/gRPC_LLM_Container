"""
Cross-feature integration test: Repair loop feedback pipeline.

Verifies validator FixHints flow into the builder repair prompt, failure
fingerprinting catches thrashing, and terminal failures halt immediately.

Components integrated:
- tools/builtin/module_validator.py (FixHint, ValidationReport)
- tools/builtin/module_builder.py (repair_module, MAX_REPAIR_ATTEMPTS)
- shared/modules/audit.py (BuildAuditLog, FailureFingerprint, FailureType)
"""
import importlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from shared.modules.contracts import GeneratorResponseContract, FileChange

from shared.modules.audit import (
    BuildAuditLog,
    AttemptRecord,
    AttemptStatus,
    FailureFingerprint,
    FailureType,
)


class TestRepairLoopFeedback:

    def test_fix_hints_flow_from_validator_to_repair(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Validator FixHints appear in repair_module output and audit log."""
        modules_dir = temp_workspace["modules_dir"]

        category, platform = "test", "repairmod"
        module_dir = modules_dir / category / platform
        module_dir.mkdir(parents=True)
        (module_dir / "adapter.py").write_text(valid_adapter_code)
        (module_dir / "test_adapter.py").write_text(valid_test_code)

        validation_report = {
            "status": "FAILED",
            "fix_hints": [
                {"category": "test_failure", "message": "test_fetch_raw failed"},
                {"category": "missing_method", "message": "Missing transform_v2"},
            ],
            "static_results": [],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        audit_log = BuildAuditLog(job_id="repair-test", module_id="test/repairmod")
        result = setup_builder.repair_module(
            "test/repairmod", validation_report, audit_log
        )

        assert result["fix_hints"] == validation_report["fix_hints"]
        assert len(audit_log.attempts) == 1
        assert audit_log.attempts[0].failure_fingerprint is not None

    def test_failure_fingerprint_stable_for_identical_failures(self):
        """Same FixHints produce same FailureFingerprint hash."""
        report = {
            "fix_hints": [
                {"category": "test_failure", "message": "test_fetch failed"},
            ],
            "static_results": [{"name": "syntax", "passed": True}],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        fp1 = FailureFingerprint.from_validation_report(report)
        fp2 = FailureFingerprint.from_validation_report(report)

        assert fp1.hash == fp2.hash

    def test_thrash_detection_stops_repair_loop(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Two consecutive identical fingerprints trigger thrash detection."""
        modules_dir = temp_workspace["modules_dir"]
        module_dir = modules_dir / "test" / "thrash"
        module_dir.mkdir(parents=True)
        (module_dir / "adapter.py").write_text(valid_adapter_code)
        (module_dir / "test_adapter.py").write_text(valid_test_code)

        # Pre-load audit log with two identical failures
        audit_log = BuildAuditLog(job_id="thrash-test", module_id="test/thrash")

        fp_hash = FailureFingerprint(
            error_types=["syntax"],
            failing_tests=["test_one"],
            fix_hint_categories=["test_failure"],
        ).hash

        for i in range(2):
            audit_log.add_attempt(AttemptRecord(
                attempt_number=i + 1,
                bundle_sha256=f"hash_{i}",
                stage="repair",
                status=AttemptStatus.FAILED,
                failure_fingerprint=fp_hash,
                failure_type=FailureType.TEST_FAILURE,
            ))

        report = {
            "fix_hints": [{"category": "test_failure", "message": "same failure"}],
            "static_results": [],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        result = setup_builder.repair_module("test/thrash", report, audit_log)

        assert result["status"] == "failed"
        assert "Thrashing detected" in result["error"]

    def test_terminal_failure_stops_immediately(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Policy violation classified as terminal — repair stops."""
        modules_dir = temp_workspace["modules_dir"]
        module_dir = modules_dir / "test" / "terminal"
        module_dir.mkdir(parents=True)
        (module_dir / "adapter.py").write_text(valid_adapter_code)
        (module_dir / "test_adapter.py").write_text(valid_test_code)

        report = {
            "fix_hints": [
                {"category": "policy_violation", "message": "Forbidden import subprocess"},
            ],
            "static_results": [],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        audit_log = BuildAuditLog(job_id="terminal-test", module_id="test/terminal")
        result = setup_builder.repair_module("test/terminal", report, audit_log)

        assert result["status"] == "failed"
        assert "Terminal failure" in result["error"]
        assert result["failure_type"] == "policy_violation"

    def test_max_attempts_boundary(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Repair stops at exactly MAX_REPAIR_ATTEMPTS=10."""
        modules_dir = temp_workspace["modules_dir"]
        module_dir = modules_dir / "test" / "maxattempt"
        module_dir.mkdir(parents=True)
        (module_dir / "adapter.py").write_text(valid_adapter_code)
        (module_dir / "test_adapter.py").write_text(valid_test_code)

        audit_log = BuildAuditLog(job_id="max-test", module_id="test/maxattempt")
        for i in range(10):
            audit_log.add_attempt(AttemptRecord(
                attempt_number=i + 1,
                bundle_sha256=f"hash_{i}",
                stage="repair",
                status=AttemptStatus.FAILED,
                failure_fingerprint=f"fp_{i}",  # unique fingerprints
                failure_type=FailureType.TEST_FAILURE,
            ))

        report = {
            "fix_hints": [{"category": "test_failure", "message": "still failing"}],
            "static_results": [],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        result = setup_builder.repair_module("test/maxattempt", report, audit_log)

        assert result["status"] == "failed"
        assert "Max repair attempts" in result["error"]

    def test_repair_module_calls_gateway_generate_for_repair(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """repair_module invokes gateway.generate with purpose=REPAIR and applies patch."""
        modules_dir = temp_workspace["modules_dir"]
        module_dir = modules_dir / "test" / "gapcheck"
        module_dir.mkdir(parents=True)
        (module_dir / "adapter.py").write_text(valid_adapter_code)
        (module_dir / "test_adapter.py").write_text(valid_test_code)

        generated_contract = GeneratorResponseContract(
            stage="repair",
            module="test/gapcheck",
            changed_files=[
                FileChange(
                    path="test/gapcheck/adapter.py",
                    content=valid_adapter_code.replace("return {\"temperature\": 22, \"unit\": \"celsius\"}", "return {\"temperature\": 23, \"unit\": \"celsius\"}"),
                )
            ],
            assumptions=["repair"],
            rationale="apply fix",
            policy="adapter_contract_v1",
            validation_report={"self_check": "passed"},
        )

        mock_gateway = MagicMock()
        mock_gateway.generate = AsyncMock(return_value=(generated_contract, {"provider": "mock", "model": "mock-model"}))
        setup_builder._llm_gateway = mock_gateway

        report = {
            "fix_hints": [{"category": "test_failure", "message": "test failed"}],
            "static_results": [],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        audit_log = BuildAuditLog(job_id="gap-test", module_id="test/gapcheck")
        result = setup_builder.repair_module("test/gapcheck", report, audit_log)

        mock_gateway.generate.assert_called_once()
        purpose = mock_gateway.generate.call_args.kwargs["purpose"]
        purpose_value = getattr(purpose, "value", str(purpose)).lower()
        assert "repair" in purpose_value
        assert result["status"] == "success"

    def test_fix_hint_categories_align_with_failure_classification(self):
        """FixHint categories map to correct FailureType enum values."""
        audit_log = BuildAuditLog(job_id="classify", module_id="t/m")

        test_cases = [
            ("test_failure", FailureType.TEST_FAILURE),
            ("schema_error", FailureType.SCHEMA_MISMATCH),
            ("missing_method", FailureType.MISSING_METHOD),
            ("import_violation", FailureType.IMPORT_VIOLATION),
            ("syntax_error", FailureType.SYNTAX_ERROR),
            ("policy_violation", FailureType.POLICY_VIOLATION),
            ("security_block", FailureType.POLICY_VIOLATION),
        ]

        for category, expected_type in test_cases:
            report = {"fix_hints": [{"category": category, "message": "test"}]}
            classified = audit_log.classify_failure_type(report)
            assert classified == expected_type, (
                f"category={category}: expected {expected_type}, got {classified}"
            )
