"""
Feature Test Harness - Capability-driven test suite selector.

Selects and runs test suites based on module manifest capabilities:
- auth_type="api_key" → run auth_api_key suite
- auth_type="oauth2" → run oauth_refresh suite
- capability="pagination" → run pagination_cursor suite
- capability="rate_limited" → run rate_limit_429 suite
- Always → run schema_drift_detection suite

Usage:
    from tools.builtin.feature_test_harness import select_suites, run_feature_tests

    manifest = ModuleManifest.load(manifest_path)
    suites = select_suites(manifest)
    results = run_feature_tests(module_id, suites)
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TestSuite:
    """Definition of a feature test suite."""
    name: str
    description: str
    test_module: str  # pytest module path
    required_capability: Optional[str] = None
    required_auth_type: Optional[str] = None


# Feature test suite registry
FEATURE_SUITES = [
    TestSuite(
        name="auth_api_key",
        description="API key authentication tests",
        test_module="tests.feature.test_auth_api_key",
        required_auth_type="api_key",
    ),
    TestSuite(
        name="oauth_refresh",
        description="OAuth2 token refresh tests",
        test_module="tests.feature.test_oauth_refresh",
        required_auth_type="oauth2",
    ),
    TestSuite(
        name="pagination_cursor",
        description="Cursor-based pagination tests",
        test_module="tests.feature.test_pagination_cursor",
        required_capability="pagination",
    ),
    TestSuite(
        name="rate_limit_429",
        description="Rate limit handling tests",
        test_module="tests.feature.test_rate_limit_429",
        required_capability="rate_limited",
    ),
    TestSuite(
        name="schema_drift",
        description="Schema drift detection tests",
        test_module="tests.feature.test_schema_drift_detection",
        # Always runs
    ),
]


def select_suites(manifest: Dict[str, Any]) -> List[TestSuite]:
    """
    Select test suites based on manifest capabilities.

    Args:
        manifest: Module manifest dict or ModuleManifest object

    Returns:
        List of TestSuite objects to run
    """
    # Handle both dict and ModuleManifest object
    if hasattr(manifest, 'to_dict'):
        manifest_dict = manifest.to_dict()
    else:
        manifest_dict = manifest

    auth_type = manifest_dict.get("auth_type", "none")
    capabilities = manifest_dict.get("capabilities", {})

    # Extract capability flags
    has_pagination = capabilities.get("pagination", False)
    has_rate_limiting = capabilities.get("rate_limited", False)

    selected = []

    for suite in FEATURE_SUITES:
        # Always include suites with no requirements
        if suite.required_auth_type is None and suite.required_capability is None:
            selected.append(suite)
            continue

        # Check auth type match
        if suite.required_auth_type and suite.required_auth_type == auth_type:
            selected.append(suite)
            continue

        # Check capability match
        if suite.required_capability:
            if suite.required_capability == "pagination" and has_pagination:
                selected.append(suite)
            elif suite.required_capability == "rate_limited" and has_rate_limiting:
                selected.append(suite)

    logger.info(
        f"Selected {len(selected)} feature test suites for manifest: "
        f"{[s.name for s in selected]}"
    )

    return selected


@dataclass
class FeatureTestResult:
    """Result from running feature test suites."""
    module_id: str
    suites_run: int = 0
    suites_passed: int = 0
    suites_failed: int = 0
    total_tests: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    suite_results: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0


def run_feature_tests(
    module_id: str,
    suites: List[TestSuite],
    module_path: Optional[Path] = None,
) -> FeatureTestResult:
    """
    Run selected feature test suites for a module.

    Args:
        module_id: Module identifier (category/platform)
        suites: List of test suites to run
        module_path: Optional path to module directory

    Returns:
        FeatureTestResult with aggregated results
    """
    import subprocess
    import time

    result = FeatureTestResult(module_id=module_id)
    start_time = time.time()

    for suite in suites:
        suite_start = time.time()

        # Run pytest for this suite
        cmd = [
            "python",
            "-m",
            "pytest",
            suite.test_module.replace(".", "/") + ".py",
            "-v",
            "--tb=short",
            "--json-report",
            f"--json-report-file=/tmp/pytest_report_{suite.name}.json",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            suite_duration = (time.time() - suite_start) * 1000

            # Parse pytest output
            suite_result = {
                "name": suite.name,
                "passed": proc.returncode == 0,
                "duration_ms": suite_duration,
                "exit_code": proc.returncode,
            }

            # Try to parse JSON report if available
            report_path = Path(f"/tmp/pytest_report_{suite.name}.json")
            if report_path.exists():
                try:
                    report_data = json.loads(report_path.read_text())
                    suite_result["tests_run"] = report_data.get("summary", {}).get("total", 0)
                    suite_result["tests_passed"] = report_data.get("summary", {}).get("passed", 0)
                    suite_result["tests_failed"] = report_data.get("summary", {}).get("failed", 0)
                except Exception as e:
                    logger.warning(f"Failed to parse pytest JSON report: {e}")

            result.suite_results.append(suite_result)
            result.suites_run += 1

            if suite_result["passed"]:
                result.suites_passed += 1
            else:
                result.suites_failed += 1

            result.total_tests += suite_result.get("tests_run", 0)
            result.tests_passed += suite_result.get("tests_passed", 0)
            result.tests_failed += suite_result.get("tests_failed", 0)

        except subprocess.TimeoutExpired:
            logger.error(f"Suite {suite.name} timed out after 30s")
            result.suite_results.append({
                "name": suite.name,
                "passed": False,
                "error": "timeout",
            })
            result.suites_failed += 1

        except Exception as e:
            logger.error(f"Failed to run suite {suite.name}: {e}")
            result.suite_results.append({
                "name": suite.name,
                "passed": False,
                "error": str(e),
            })
            result.suites_failed += 1

    result.execution_time_ms = (time.time() - start_time) * 1000

    logger.info(
        f"Feature tests complete: {result.suites_passed}/{result.suites_run} suites passed, "
        f"{result.tests_passed}/{result.total_tests} tests passed"
    )

    return result


def get_suite_by_name(name: str) -> Optional[TestSuite]:
    """Get a test suite by name."""
    for suite in FEATURE_SUITES:
        if suite.name == name:
            return suite
    return None


def list_available_suites() -> List[str]:
    """List all available feature test suites."""
    return [suite.name for suite in FEATURE_SUITES]
