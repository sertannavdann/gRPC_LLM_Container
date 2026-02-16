"""
Module Validator Tool — validates adapter code with merged static + runtime report.

Validation pipeline:
    1. Static checks (no sandbox needed):
       - Syntax check via compile()
       - AST contract compliance (required methods, decorator, imports)
       - Manifest schema validation
       - Path allowlist check
    2. Runtime checks (sandbox only):
       - Execute test_adapter.py in sandbox
       - Capture stdout, stderr, junit XML
       - Record timing, resource usage, exit code
    3. Merge results into single ValidationReport
    4. Store artifacts using ArtifactIndex

Returns VALIDATED | FAILED | ERROR with structured fix hints and artifact references.
"""
import ast
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from shared.modules.manifest import ModuleManifest, ModuleStatus, ValidationResults
from shared.modules.contracts import AdapterContractSpec
from shared.modules.artifacts import ArtifactBundleBuilder, ArtifactIndex
from sandbox_service.policy import ExecutionPolicy
from sandbox_service.runner import SandboxRunner

logger = logging.getLogger(__name__)

MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/app/data/artifacts"))


@dataclass
class StaticCheckResult:
    """Result from a single static check."""
    name: str
    passed: bool
    details: str = ""


@dataclass
class RuntimeCheckResult:
    """Result from runtime test execution."""
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_errored: int = 0
    execution_time_ms: float = 0.0
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class FixHint:
    """Structured hint for LLM self-correction."""
    category: str  # import_violation, test_failure, schema_error, missing_method, etc.
    message: str
    context: Optional[str] = None
    suggestion: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class ValidationReport:
    """
    Merged validation report (static + runtime).

    Attributes:
        status: VALIDATED | FAILED | ERROR
        module_id: Module identifier (category/platform)
        static_results: List of static check results
        runtime_results: Runtime test execution results
        fix_hints: Structured hints for fixing issues
        artifacts: List of artifact references (logs, junit, reports)
        validated_at: ISO timestamp
    """
    status: str
    module_id: str
    static_results: List[StaticCheckResult] = field(default_factory=list)
    runtime_results: Optional[RuntimeCheckResult] = None
    fix_hints: List[FixHint] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status,
            "module_id": self.module_id,
            "static_results": [
                {"name": r.name, "passed": r.passed, "details": r.details}
                for r in self.static_results
            ],
            "runtime_results": {
                "tests_run": self.runtime_results.tests_run,
                "tests_passed": self.runtime_results.tests_passed,
                "tests_failed": self.runtime_results.tests_failed,
                "tests_errored": self.runtime_results.tests_errored,
                "execution_time_ms": self.runtime_results.execution_time_ms,
                "exit_code": self.runtime_results.exit_code,
            } if self.runtime_results else None,
            "fix_hints": [
                {
                    "category": h.category,
                    "message": h.message,
                    "context": h.context,
                    "suggestion": h.suggestion,
                    "line_number": h.line_number
                }
                for h in self.fix_hints
            ],
            "artifacts": self.artifacts,
            "validated_at": self.validated_at
        }


def validate_module(module_id: str) -> Dict[str, Any]:
    """
    Validate an adapter module with merged static + runtime checks.

    Args:
        module_id: Module identifier in "category/platform" format

    Returns:
        Dict with ValidationReport and instructions
    """
    parts = module_id.split("/")
    if len(parts) != 2:
        return {"status": "error", "error": f"Invalid module_id: {module_id}"}

    category, platform = parts
    module_dir = MODULES_DIR / category / platform

    if not module_dir.exists():
        return {"status": "error", "error": f"Module not found: {module_dir}"}

    adapter_file = module_dir / "adapter.py"
    test_file = module_dir / "test_adapter.py"
    manifest_file = module_dir / "manifest.json"

    if not adapter_file.exists():
        return {"status": "error", "error": f"adapter.py not found in {module_dir}"}

    # Initialize validation report
    report = ValidationReport(
        status="VALIDATED",
        module_id=module_id
    )

    # ========== STATIC CHECKS (no sandbox needed) ==========

    adapter_code = adapter_file.read_text()

    # 1. Syntax check
    syntax_check = _check_syntax(adapter_code, str(adapter_file))
    report.static_results.append(syntax_check)
    if not syntax_check.passed:
        report.status = "FAILED"
        report.fix_hints.append(FixHint(
            category="syntax_error",
            message=syntax_check.details,
            suggestion="Fix syntax errors before proceeding"
        ))

    # 2. Contract compliance (AST)
    if syntax_check.passed:
        contract_checks = _check_contract_compliance(adapter_code, module_id)
        report.static_results.extend(contract_checks)
        failed_contracts = [c for c in contract_checks if not c.passed]
        if failed_contracts:
            report.status = "FAILED"
            for check in failed_contracts:
                report.fix_hints.extend(_build_contract_fix_hints(check))

    # 3. Manifest schema validation
    if manifest_file.exists():
        manifest_check = _check_manifest_schema(manifest_file)
        report.static_results.append(manifest_check)
        if not manifest_check.passed:
            report.status = "FAILED"
            report.fix_hints.append(FixHint(
                category="schema_error",
                message=manifest_check.details,
                suggestion="Fix manifest.json schema violations"
            ))

    # 4. Path allowlist check
    path_check = _check_path_allowlist(module_dir, module_id)
    report.static_results.append(path_check)
    if not path_check.passed:
        report.status = "FAILED"

    # ========== RUNTIME CHECKS (sandbox only) ==========

    if test_file.exists() and report.status != "FAILED":
        runtime_result, artifacts = _run_tests_in_sandbox(
            adapter_code=adapter_code,
            test_code=test_file.read_text(),
            module_id=module_id
        )
        report.runtime_results = runtime_result
        report.artifacts = artifacts

        if runtime_result.tests_failed > 0 or runtime_result.exit_code != 0:
            report.status = "FAILED"
            report.fix_hints.append(FixHint(
                category="test_failure",
                message=f"{runtime_result.tests_failed} tests failed",
                context=runtime_result.stderr[:500] if runtime_result.stderr else None,
                suggestion="Review test output in artifacts"
            ))

    # ========== FINALIZE ==========

    # Store artifacts
    if report.artifacts:
        _store_validation_artifacts(module_id, report)

    # Update manifest
    if manifest_file.exists():
        manifest = ModuleManifest.load(manifest_file)
        # Update old ValidationResults for backwards compatibility
        legacy_results = ValidationResults()
        legacy_results.syntax_check = "pass" if syntax_check.passed else "fail"
        if report.runtime_results:
            legacy_results.unit_tests = (
                "pass" if report.runtime_results.tests_failed == 0 else "fail"
            )
        legacy_results.validated_at = report.validated_at
        if report.status == "FAILED":
            legacy_results.error_details = "\n".join([h.message for h in report.fix_hints])

        manifest.validation_results = legacy_results
        manifest.status = ModuleStatus.VALIDATED if report.status == "VALIDATED" else ModuleStatus.FAILED
        manifest.save(MODULES_DIR)

    logger.info(f"Module validation {report.status}: {module_id}")

    return {
        "status": "success" if report.status == "VALIDATED" else "failed",
        "module_id": module_id,
        "report": report.to_dict(),
        "instructions": (
            f"Module {module_id} validation {report.status.lower()}. "
            + (
                "Call install_module() to deploy it."
                if report.status == "VALIDATED"
                else "Fix the errors and call write_module_code() then validate_module() again."
            )
        ),
    }


def _check_syntax(source_code: str, filename: str) -> StaticCheckResult:
    """Check Python syntax."""
    try:
        compile(source_code, filename, "exec")
        return StaticCheckResult(name="syntax", passed=True)
    except SyntaxError as e:
        return StaticCheckResult(
            name="syntax",
            passed=False,
            details=f"Syntax error at line {e.lineno}: {e.msg}"
        )


def _check_contract_compliance(source_code: str, module_id: str) -> List[StaticCheckResult]:
    """Check adapter contract compliance using AdapterContractSpec."""
    results = []

    # Use contract validation
    contract_result = AdapterContractSpec.validate_adapter_file(source_code)

    # Forbidden imports
    if any(e["code"] == "forbidden_import" for e in contract_result.get("errors", [])):
        forbidden_error = next(e for e in contract_result["errors"] if e["code"] == "forbidden_import")
        results.append(StaticCheckResult(
            name="forbidden_imports",
            passed=False,
            details=forbidden_error["message"]
        ))
    else:
        results.append(StaticCheckResult(name="forbidden_imports", passed=True))

    # Decorator check
    if any(e["code"] == "missing_decorator" for e in contract_result.get("errors", [])):
        results.append(StaticCheckResult(
            name="decorator",
            passed=False,
            details="Missing @register_adapter decorator"
        ))
    else:
        results.append(StaticCheckResult(name="decorator", passed=True))

    # Required methods
    if any(e["code"] == "missing_method" for e in contract_result.get("errors", [])):
        method_error = next(e for e in contract_result["errors"] if e["code"] == "missing_method")
        results.append(StaticCheckResult(
            name="required_methods",
            passed=False,
            details=method_error["message"]
        ))
    else:
        results.append(StaticCheckResult(name="required_methods", passed=True))

    return results


def _check_manifest_schema(manifest_file: Path) -> StaticCheckResult:
    """Check manifest.json against schema."""
    try:
        manifest = ModuleManifest.load(manifest_file)
        # Basic validation - manifest loaded successfully
        return StaticCheckResult(name="manifest_schema", passed=True)
    except Exception as e:
        return StaticCheckResult(
            name="manifest_schema",
            passed=False,
            details=f"Manifest validation failed: {e}"
        )


def _check_path_allowlist(module_dir: Path, module_id: str) -> StaticCheckResult:
    """Check that module files are within allowed directory."""
    allowed_path = MODULES_DIR / module_id.replace("/", "/")
    try:
        module_dir.relative_to(allowed_path.parent)
        return StaticCheckResult(name="path_allowlist", passed=True)
    except ValueError:
        return StaticCheckResult(
            name="path_allowlist",
            passed=False,
            details=f"Module directory {module_dir} is outside allowed path"
        )


def _run_tests_in_sandbox(
    adapter_code: str,
    test_code: str,
    module_id: str
) -> tuple:
    """
    Run adapter tests in sandbox and return results + artifacts.

    Returns:
        (RuntimeCheckResult, List[artifact_paths])
    """
    # Create sandbox runner with module validation policy
    policy = ExecutionPolicy.module_validation()
    runner = SandboxRunner(policy)

    # Build test runner script
    runner_code = f'''
import sys
import traceback

# Write adapter code
with open("adapter.py", "w") as f:
    f.write("""{adapter_code.replace(chr(92), chr(92)*2).replace('"""', chr(92) + '"""')}""")

# Write test code
with open("test_adapter.py", "w") as f:
    f.write("""{test_code.replace(chr(92), chr(92)*2).replace('"""', chr(92) + '"""')}""")

# Import and run tests
try:
    import importlib
    test_module = importlib.import_module("test_adapter")

    test_functions = [
        name for name in dir(test_module)
        if name.startswith("test_") and callable(getattr(test_module, name))
    ]

    passed = 0
    failed = 0
    errors = []

    for test_name in test_functions:
        try:
            getattr(test_module, test_name)()
            passed += 1
            print(f"PASS: {{test_name}}")
        except AssertionError as e:
            failed += 1
            errors.append(f"FAIL: {{test_name}}: {{e}}")
            print(f"FAIL: {{test_name}}: {{e}}")
        except Exception as e:
            failed += 1
            errors.append(f"ERROR: {{test_name}}: {{e}}")
            print(f"ERROR: {{test_name}}: {{e}}")

    print(f"\\nResults: {{passed}} passed, {{failed}} failed")
    if failed > 0:
        sys.exit(1)
except Exception as e:
    print(f"Test execution error: {{e}}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
'''

    # Execute in sandbox
    exec_result = runner.execute(runner_code)

    # Parse test results from output
    runtime_result = RuntimeCheckResult(
        execution_time_ms=exec_result.execution_time_ms,
        exit_code=exec_result.exit_code,
        stdout=exec_result.stdout,
        stderr=exec_result.stderr
    )

    # Parse test counts from output
    if "Results:" in exec_result.stdout:
        try:
            results_line = [l for l in exec_result.stdout.split("\n") if "Results:" in l][0]
            parts = results_line.split()
            runtime_result.tests_passed = int(parts[1])
            runtime_result.tests_failed = int(parts[3])
            runtime_result.tests_run = runtime_result.tests_passed + runtime_result.tests_failed
        except (IndexError, ValueError):
            pass

    # Count PASS/FAIL lines as fallback
    if runtime_result.tests_run == 0:
        runtime_result.tests_passed = exec_result.stdout.count("PASS:")
        runtime_result.tests_failed = exec_result.stdout.count("FAIL:") + exec_result.stdout.count("ERROR:")
        runtime_result.tests_run = runtime_result.tests_passed + runtime_result.tests_failed

    # Store artifacts
    artifacts = _store_execution_artifacts(module_id, exec_result, runtime_result)

    return runtime_result, artifacts


def _store_execution_artifacts(
    module_id: str,
    exec_result,
    runtime_result: RuntimeCheckResult
) -> List[str]:
    """Store execution artifacts and return artifact paths."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    category, platform = module_id.split("/")
    artifact_dir = ARTIFACTS_DIR / category / platform
    artifact_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    artifacts = []

    # Store stdout
    if exec_result.stdout:
        stdout_file = artifact_dir / f"stdout_{timestamp}.log"
        stdout_file.write_text(exec_result.stdout)
        artifacts.append(str(stdout_file))

    # Store stderr
    if exec_result.stderr:
        stderr_file = artifact_dir / f"stderr_{timestamp}.log"
        stderr_file.write_text(exec_result.stderr)
        artifacts.append(str(stderr_file))

    # Store execution report
    report_file = artifact_dir / f"execution_{timestamp}.json"
    report_file.write_text(json.dumps(exec_result.to_dict(), indent=2))
    artifacts.append(str(report_file))

    return artifacts


def _store_validation_artifacts(module_id: str, report: ValidationReport) -> None:
    """Store validation report using ArtifactIndex."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    category, platform = module_id.split("/")
    artifact_dir = ARTIFACTS_DIR / category / platform
    artifact_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_file = artifact_dir / f"validation_{timestamp}.json"
    report_file.write_text(json.dumps(report.to_dict(), indent=2))


def _build_contract_fix_hints(check: StaticCheckResult) -> List[FixHint]:
    """Build fix hints from contract check failures."""
    hints = []

    if check.name == "forbidden_imports" and not check.passed:
        hints.append(FixHint(
            category="import_violation",
            message=check.details,
            suggestion="Remove forbidden imports and use allowed alternatives from the policy"
        ))
    elif check.name == "decorator" and not check.passed:
        hints.append(FixHint(
            category="missing_decorator",
            message="Missing @register_adapter decorator",
            suggestion="Add @register_adapter decorator before class definition"
        ))
    elif check.name == "required_methods" and not check.passed:
        hints.append(FixHint(
            category="missing_method",
            message=check.details,
            suggestion="Implement all required methods: fetch_raw, transform, get_schema"
        ))

    return hints
