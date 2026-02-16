"""
Cross-feature integration test: Policy propagation.

Verifies that sandbox policy violations propagate correctly through the
validator into fix hints, and then into terminal failure classification.

Components integrated:
- sandbox_service/policy.py (ExecutionPolicy, ImportPolicy)
- sandbox_service/runner.py (StaticImportChecker)
- shared/modules/contracts.py (AdapterContractSpec)
- shared/modules/audit.py (BuildAuditLog, FailureType)
- tools/builtin/module_builder.py (repair_module)
"""
import pytest

from sandbox_service.policy import (
    ExecutionPolicy,
    ImportPolicy,
    ImportCategory,
    FORBIDDEN_IMPORTS,
)
from sandbox_service.runner import StaticImportChecker
from shared.modules.contracts import AdapterContractSpec
from shared.modules.audit import BuildAuditLog, AttemptRecord, AttemptStatus, FailureType


class TestPolicyPropagation:

    def test_sandbox_import_violation_becomes_validator_fix_hint(
        self, forbidden_import_adapter_code
    ):
        """Sandbox import violation aligns with AdapterContractSpec error."""
        # StaticImportChecker catches it
        policy = ImportPolicy.module_validation()
        violations = StaticImportChecker.check_imports(
            forbidden_import_adapter_code, policy
        )
        subprocess_violations = [
            v for v in violations if "subprocess" in v.module_name
        ]
        assert len(subprocess_violations) > 0

        # AdapterContractSpec also catches it
        result = AdapterContractSpec.validate_adapter_file(
            forbidden_import_adapter_code
        )
        assert result["valid"] is False

        has_forbidden_error = any(
            "Forbidden imports" in e.get("message", "")
            for e in result["errors"]
        )
        assert has_forbidden_error

    def test_policy_violation_classified_as_terminal(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Policy violation fix_hint -> terminal stop in repair loop."""
        modules_dir = temp_workspace["modules_dir"]
        module_dir = modules_dir / "test" / "polterm"
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

        audit_log = BuildAuditLog(job_id="pol-test", module_id="test/polterm")

        # classify_failure_type returns POLICY_VIOLATION
        classified = audit_log.classify_failure_type(report)
        assert classified == FailureType.POLICY_VIOLATION

        # repair_module stops immediately
        result = setup_builder.repair_module("test/polterm", report, audit_log)
        assert result["status"] == "failed"
        assert "Terminal failure" in result["error"]

    def test_security_block_classified_as_terminal(self):
        """security_block fix_hint -> POLICY_VIOLATION (same terminal handling)."""
        audit_log = BuildAuditLog(job_id="sec", module_id="t/m")
        report = {
            "fix_hints": [
                {"category": "security_block", "message": "Dangerous operation"},
            ],
        }
        classified = audit_log.classify_failure_type(report)
        assert classified == FailureType.POLICY_VIOLATION

    def test_retryable_failure_allows_repair_attempt(
        self, setup_builder, temp_workspace, valid_adapter_code, valid_test_code
    ):
        """Non-terminal failures allow repair attempts."""
        modules_dir = temp_workspace["modules_dir"]
        module_dir = modules_dir / "test" / "retryable"
        module_dir.mkdir(parents=True)
        (module_dir / "adapter.py").write_text(valid_adapter_code)
        (module_dir / "test_adapter.py").write_text(valid_test_code)

        report = {
            "fix_hints": [
                {"category": "test_failure", "message": "test_fetch_raw failed"},
            ],
            "static_results": [],
            "runtime_results": {"stderr": "", "stdout": ""},
        }

        audit_log = BuildAuditLog(job_id="retry-test", module_id="test/retryable")

        classified = audit_log.classify_failure_type(report)
        assert classified == FailureType.TEST_FAILURE

        result = setup_builder.repair_module("test/retryable", report, audit_log)
        assert result["status"] == "repair_pending"
        assert len(audit_log.attempts) == 1

    def test_sandbox_policy_merge_preserves_forbidden_enforcement(self):
        """Merging two policies preserves forbidden import enforcement."""
        default = ExecutionPolicy.default()
        extended = ExecutionPolicy.module_validation()

        merged = default.merge(extended)

        assert merged.imports.enforce_forbidden is True
        assert not merged.imports.is_import_allowed("subprocess")

    def test_different_policy_profiles_all_block_subprocess(self):
        """default, module_validation, integration_test all block subprocess."""
        code = "import subprocess\nsubprocess.run(['ls'])"

        profiles = [
            ("default", ExecutionPolicy.default()),
            ("module_validation", ExecutionPolicy.module_validation()),
            ("integration_test", ExecutionPolicy.integration_test(["example.com"])),
        ]

        for name, policy in profiles:
            violations = StaticImportChecker.check_imports(code, policy.imports)
            subprocess_found = any("subprocess" in v.module_name for v in violations)
            assert subprocess_found, f"{name} policy did not block subprocess"
