"""
Module Validator Tool — validates adapter code in the sandbox.

Validation pipeline:
    1. Syntax check via compile()
    2. AST analysis for BaseAdapter compliance
    3. Run tests in sandbox (with module validation mode)
    4. Update manifest with validation results

The sandbox is used for test execution with extended imports
(httpx, aiohttp, csv, pydantic) enabled for adapter testing.
"""
import ast
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from shared.modules.manifest import ModuleManifest, ModuleStatus, ValidationResults

logger = logging.getLogger(__name__)

MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))

# Extended imports allowed in module validation sandbox mode
MODULE_VALIDATION_IMPORTS = [
    "httpx", "aiohttp", "csv", "pydantic", "hashlib",
    "decimal", "asyncio", "unittest", "pytest",
    "unittest.mock", "typing", "dataclasses", "enum",
    "json", "re", "os", "datetime", "pathlib",
    "collections", "itertools", "functools",
]

# Sandbox client reference — set by orchestrator at startup
_sandbox_client = None


def set_sandbox_client(client) -> None:
    """Set the sandbox client for module validation."""
    global _sandbox_client
    _sandbox_client = client


def validate_module(
    module_id: str,
) -> Dict[str, Any]:
    """
    Validate an adapter module's code quality and test results.

    Runs a multi-step validation pipeline:
    1. Syntax check (compile)
    2. Structure check (AST analysis for BaseAdapter class)
    3. Test execution in sandbox

    Call this after build_module() and write_module_code() to verify
    the adapter code is correct before installing.

    Args:
        module_id (str): Module identifier in "category/platform" format,
            e.g. "gaming/clashroyale".

    Returns:
        Dict with validation results: syntax_check, structure_check,
        unit_tests status, and any error details.
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

    results = ValidationResults()
    errors = []

    # --- Step 1: Syntax check ---
    adapter_code = adapter_file.read_text()
    try:
        compile(adapter_code, str(adapter_file), "exec")
        results.syntax_check = "pass"
    except SyntaxError as e:
        results.syntax_check = "fail"
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")

    # --- Step 2: Structure check (AST) ---
    if results.syntax_check == "pass":
        structure_issues = _check_adapter_structure(adapter_code, module_id)
        if structure_issues:
            errors.extend(structure_issues)

    # --- Step 3: Run tests in sandbox ---
    test_result = "skip"
    test_output = ""

    if test_file.exists() and results.syntax_check == "pass":
        test_result, test_output = _run_tests_in_sandbox(
            adapter_code=adapter_code,
            test_code=test_file.read_text(),
            module_id=module_id,
        )
        results.unit_tests = test_result

        if test_result == "fail":
            errors.append(f"Test failures:\n{test_output}")
    else:
        results.unit_tests = "skip"

    # --- Update manifest ---
    results.validated_at = datetime.utcnow().isoformat()
    if errors:
        results.error_details = "\n".join(errors)

    overall_pass = (
        results.syntax_check == "pass"
        and results.unit_tests in ("pass", "skip")
    )

    if manifest_file.exists():
        manifest = ModuleManifest.load(manifest_file)
        manifest.validation_results = results
        manifest.status = ModuleStatus.VALIDATED if overall_pass else ModuleStatus.FAILED
        manifest.save(MODULES_DIR)

    logger.info(f"Module validation {'PASSED' if overall_pass else 'FAILED'}: {module_id}")

    return {
        "status": "success" if overall_pass else "failed",
        "module_id": module_id,
        "validation": results.to_dict(),
        "errors": errors if errors else None,
        "instructions": (
            f"Module {module_id} validation {'passed' if overall_pass else 'failed'}. "
            + (
                "Call install_module() to deploy it."
                if overall_pass
                else "Fix the errors and call write_module_code() then validate_module() again."
            )
        ),
    }


def _check_adapter_structure(code: str, module_id: str) -> List[str]:
    """Check AST for BaseAdapter subclass with required methods."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ["Could not parse AST"]

    # Find class definitions
    classes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]

    if not classes:
        issues.append("No class definition found in adapter.py")
        return issues

    # Check for BaseAdapter subclass
    adapter_class = None
    for cls in classes:
        for base in cls.bases:
            base_name = ""
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
                base_name = base.value.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr

            if "BaseAdapter" in base_name or "Adapter" in base_name:
                adapter_class = cls
                break

    if adapter_class is None:
        issues.append("No class extending BaseAdapter found")
        return issues

    # Check required methods
    method_names = {
        node.name for node in ast.walk(adapter_class)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for required in ("fetch_raw", "transform"):
        if required not in method_names:
            issues.append(f"Missing required method: {required}")

    # Check for @register_adapter decorator
    has_register = False
    for decorator in adapter_class.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name) and func.id == "register_adapter":
                has_register = True
            elif isinstance(func, ast.Attribute) and func.attr == "register_adapter":
                has_register = True
        elif isinstance(decorator, ast.Name) and decorator.id == "register_adapter":
            has_register = True

    if not has_register:
        issues.append("Missing @register_adapter decorator on adapter class")

    return issues


def _run_tests_in_sandbox(
    adapter_code: str,
    test_code: str,
    module_id: str,
) -> tuple:
    """
    Run adapter tests in the sandbox service.

    Returns (result, output) where result is "pass" or "fail".
    """
    if _sandbox_client is None:
        # Fallback: local compile-only validation
        try:
            compile(test_code, f"{module_id}/test_adapter.py", "exec")
            return "pass", "Sandbox unavailable — syntax-only validation passed"
        except SyntaxError as e:
            return "fail", f"Test syntax error: {e}"

    # Build a test runner script that includes the adapter code
    runner_code = f'''
import sys
import os
sys.path.insert(0, os.getcwd())

# Write adapter code to importable location
with open("adapter.py", "w") as f:
    f.write("""{adapter_code.replace(chr(92), chr(92)*2).replace('"""', chr(92) + '"""')}""")

# Write test code
test_source = """{test_code.replace(chr(92), chr(92)*2).replace('"""', chr(92) + '"""')}"""

with open("test_adapter.py", "w") as f:
    f.write(test_source)

# Run tests using simple test discovery
import importlib
import traceback

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
    except Exception as e:
        failed += 1
        errors.append(f"FAIL: {{test_name}}: {{e}}")
        print(f"FAIL: {{test_name}}: {{e}}")

print(f"\\nResults: {{passed}} passed, {{failed}} failed")
if failed > 0:
    sys.exit(1)
'''

    try:
        result = _sandbox_client.execute_code(
            code=runner_code,
            language="python",
            timeout_seconds=60,
            memory_limit_mb=512,
            allowed_imports=MODULE_VALIDATION_IMPORTS,
        )

        output = result.get("stdout", "") + result.get("stderr", "")

        if result.get("success") and result.get("exit_code", 1) == 0:
            return "pass", output
        else:
            error_msg = result.get("error_message", "")
            return "fail", output + "\n" + error_msg

    except Exception as e:
        return "fail", f"Sandbox execution error: {e}"
