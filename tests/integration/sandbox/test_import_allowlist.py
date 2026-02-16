"""
Integration tests for import allowlist enforcement.

Tests both static (AST) and runtime import enforcement.
These tests are standalone and don't require Docker services.
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sandbox_service.policy import ExecutionPolicy, ImportPolicy, ImportCategory
from sandbox_service.runner import SandboxRunner, StaticImportChecker


class TestStaticImportChecking:
    """Test AST-based static import checking."""

    def test_allowed_import_passes(self):
        """Allowed imports pass static check."""
        policy = ImportPolicy.module_validation()
        code = """
import json
import httpx
import pytest
"""
        violations = StaticImportChecker.check_imports(code, policy)
        assert len(violations) == 0

    def test_forbidden_import_subprocess_blocked(self):
        """Forbidden import (subprocess) is blocked statically."""
        policy = ImportPolicy.module_validation()
        code = """
import subprocess
subprocess.run(['ls'])
"""
        violations = StaticImportChecker.check_imports(code, policy)
        assert len(violations) == 1
        assert violations[0].module_name == "subprocess"
        assert violations[0].location == "static"
        assert violations[0].line_number == 2

    def test_forbidden_from_import_blocked(self):
        """Forbidden from import (from os import system) is blocked."""
        policy = ImportPolicy.module_validation()
        code = """
from os import system
system('echo bad')
"""
        violations = StaticImportChecker.check_imports(code, policy)
        # Should catch "os.system" as forbidden
        assert len(violations) >= 1
        # Check if any violation is for os.system
        forbidden_found = any(
            "system" in v.module_name or v.module_name == "os.system"
            for v in violations
        )
        assert forbidden_found

    def test_dynamic_import_detected(self):
        """Dynamic __import__ calls are detected statically."""
        policy = ImportPolicy.module_validation()
        code = """
module = __import__('os')
"""
        violations = StaticImportChecker.check_imports(code, policy)
        assert len(violations) == 1
        assert violations[0].module_name == "__import__"
        assert "Dynamic" in violations[0].policy_rule


class TestRuntimeImportEnforcement:
    """Test runtime import hook enforcement."""

    def test_allowed_import_succeeds(self):
        """Allowed imports succeed at runtime."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        code = """
import json
data = json.dumps({"test": True})
print(data)
"""
        result = runner.execute(code)
        assert result.success
        assert result.exit_code == 0
        assert '{"test": true}' in result.stdout.lower()

    def test_forbidden_import_blocked_at_runtime(self):
        """Forbidden import (subprocess) is blocked at runtime even if static check bypassed."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        # Try to bypass static check with getattr
        code = """
# This would bypass simple static checks
try:
    __import__('subprocess')
    print("SHOULD NOT REACH HERE")
except ImportError as e:
    print(f"Blocked: {e}")
"""
        result = runner.execute(code)
        # Should be blocked at runtime
        assert "subprocess" in result.stderr or "Blocked" in result.stdout

    def test_dynamic_import_blocked_at_runtime(self):
        """Dynamic __import__('os') is blocked at runtime."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        code = """
try:
    os = __import__('subprocess')
    print("BYPASS SUCCESSFUL")
except ImportError:
    print("Runtime block worked")
"""
        result = runner.execute(code)
        # Static check should catch __import__ call
        assert len(result.import_violations) > 0
        assert result.exit_code != 0

    def test_import_nonexistent_module_handled_gracefully(self):
        """Import of non-existent module is handled gracefully."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        code = """
try:
    import this_module_does_not_exist_12345
except ImportError as e:
    print(f"Module not found: {e}")
"""
        result = runner.execute(code)
        # Should execute but catch the import error
        assert "Module not found" in result.stdout or result.exit_code != 0


class TestDualLayerEnforcement:
    """Test that both static and runtime layers work together."""

    def test_static_layer_prevents_execution(self):
        """Static violations prevent code execution."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        code = """
import subprocess
subprocess.run(['echo', 'this should never run'])
print("EXECUTION STARTED")
"""
        result = runner.execute(code)
        # Should fail at static check
        assert not result.success
        assert len(result.import_violations) > 0
        assert result.import_violations[0].location == "static"
        # Code should not have executed
        assert "EXECUTION STARTED" not in result.stdout

    def test_runtime_layer_catches_bypasses(self):
        """Runtime layer catches attempts to bypass static check."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        # Use eval to bypass static analysis (though eval itself might be caught)
        code = """
import sys
try:
    # Try to import via hook
    mod_name = 'sub' + 'process'
    __import__(mod_name)
    print("BYPASS SUCCESSFUL")
except ImportError:
    print("Runtime hook blocked it")
"""
        result = runner.execute(code)
        # __import__ call should be caught statically
        assert len(result.import_violations) > 0
        # Even if it ran, runtime should block
        assert "BYPASS SUCCESSFUL" not in result.stdout

    def test_allowed_stdlib_works_end_to_end(self):
        """Allowed standard library imports work through both layers."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        code = """
import json
import datetime
import math

data = {
    "time": str(datetime.datetime.now()),
    "pi": math.pi,
    "nested": {"value": 42}
}
print(json.dumps(data, indent=2))
"""
        result = runner.execute(code)
        assert result.success
        assert result.exit_code == 0
        assert "pi" in result.stdout
        assert "3.14" in result.stdout

    def test_http_clients_allowed_in_validation_mode(self):
        """HTTP client imports are allowed in module validation mode."""
        policy = ExecutionPolicy.module_validation()
        runner = SandboxRunner(policy)
        code = """
# Test that httpx is importable (won't actually make requests)
try:
    import httpx
    print("httpx imported successfully")
except ImportError as e:
    print(f"Failed to import httpx: {e}")
"""
        result = runner.execute(code)
        assert result.success
        assert "httpx imported successfully" in result.stdout

    def test_minimal_policy_blocks_http_clients(self):
        """Minimal policy blocks HTTP clients."""
        policy = ExecutionPolicy(
            network=policy.ExecutionPolicy.default().network,
            imports=ImportPolicy.minimal(),
            resources=policy.ExecutionPolicy.default().resources,
            name="minimal"
        )
        runner = SandboxRunner(policy)
        code = """
import httpx
"""
        result = runner.execute(code)
        # Should be blocked at static check
        assert not result.success
        assert len(result.import_violations) > 0
        assert any("httpx" in v.module_name for v in result.import_violations)


class TestImportViolationReporting:
    """Test detailed violation reporting."""

    def test_violation_includes_line_number(self):
        """Import violations include source line numbers."""
        policy = ImportPolicy.minimal()
        code = """
# Line 1
import json  # Line 2 - allowed
import subprocess  # Line 3 - forbidden
"""
        violations = StaticImportChecker.check_imports(code, policy)
        subprocess_violation = next(
            (v for v in violations if "subprocess" in v.module_name),
            None
        )
        assert subprocess_violation is not None
        assert subprocess_violation.line_number == 3

    def test_violation_includes_policy_rule(self):
        """Import violations include which policy rule was violated."""
        policy = ImportPolicy.minimal()
        code = """
import subprocess
"""
        violations = StaticImportChecker.check_imports(code, policy)
        assert len(violations) > 0
        assert violations[0].policy_rule != ""
        assert "not in allowed list" in violations[0].policy_rule or "forbidden" in violations[0].policy_rule

    def test_multiple_violations_reported(self):
        """Multiple violations are all reported."""
        policy = ImportPolicy.minimal()
        code = """
import subprocess
import eval
from os import system
"""
        violations = StaticImportChecker.check_imports(code, policy)
        # Should have at least 2 violations (subprocess and os.system)
        # eval might not be an import violation (it's a builtin)
        assert len(violations) >= 2
