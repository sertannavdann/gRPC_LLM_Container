"""
Unit tests for the refactored math_solver (sandbox pipeline + local fallback).

Tests the sandbox delegation path (mocked) and the local restricted-eval
fallback independently.
"""

import math
import pytest
from unittest.mock import Mock, patch

from tools.builtin.math_solver import (
    math_solver,
    set_sandbox_executor,
    validate_expression,
    _normalise_expression,
    _build_script,
)


class TestMathSolverLocal:
    """Tests using local eval fallback (no sandbox)."""

    def setup_method(self):
        # Ensure sandbox is NOT wired
        set_sandbox_executor(None)

    def test_basic_arithmetic(self):
        cases = [
            ("2 + 2", 4),
            ("10 - 3", 7),
            ("4 * 5", 20),
            ("20 / 4", 5),
            ("2 ** 3", 8),
            ("10 % 3", 1),
        ]
        for expr, expected in cases:
            result = math_solver(expr)
            assert result["status"] == "success", f"Failed for {expr}: {result}"
            assert result["result"] == expected, f"{expr} → {result['result']} != {expected}"

    def test_order_of_operations(self):
        assert math_solver("2 + 2 * 3")["result"] == 8
        assert math_solver("(2 + 2) * 3")["result"] == 12

    def test_constants_pi_e(self):
        r = math_solver("pi")
        assert r["status"] == "success"
        assert abs(r["result"] - math.pi) < 1e-6

        r = math_solver("e")
        assert r["status"] == "success"
        assert abs(r["result"] - math.e) < 1e-6

    def test_trig_functions(self):
        r = math_solver("sin(pi / 2)")
        assert abs(r["result"] - 1.0) < 1e-4

        r = math_solver("cos(0)")
        assert abs(r["result"] - 1.0) < 1e-4

    def test_exp_not_broken_by_e_replacement(self):
        """Regression: old code replaced 'e' in 'exp' with math.e float."""
        r = math_solver("exp(1)")
        assert r["status"] == "success"
        assert abs(r["result"] - math.e) < 1e-4

    def test_ceil_not_broken(self):
        """Regression: old code replaced 'e' in 'ceil'."""
        r = math_solver("ceil(2.3)")
        assert r["status"] == "success"
        assert r["result"] == 3

    def test_sqrt_log_ln(self):
        assert math_solver("sqrt(16)")["result"] == 4
        assert math_solver("log(100)")["result"] == 2  # log10
        assert abs(math_solver("ln(e)")["result"] - 1.0) < 1e-4

    def test_division_by_zero(self):
        r = math_solver("10 / 0")
        assert r["status"] == "error"
        assert "zero" in r["error"].lower()

    def test_empty_expression(self):
        assert math_solver("")["status"] == "error"
        assert math_solver("   ")["status"] == "error"

    def test_none_expression(self):
        assert math_solver(None)["status"] == "error"

    def test_unsafe_patterns_rejected(self):
        assert math_solver("__import__('os')")["status"] == "error"
        assert math_solver("import os")["status"] == "error"
        assert math_solver("eval('1+1')")["status"] == "error"

    def test_caret_as_power(self):
        r = math_solver("2^10")
        assert r["status"] == "success"
        assert r["result"] == 1024

    def test_response_has_code_field(self):
        r = math_solver("2 + 2")
        assert r["status"] == "success"
        assert "code" in r
        assert "import math" in r["code"]

    def test_formatted_field(self):
        r = math_solver("10 / 3")
        assert r["status"] == "success"
        assert "formatted" in r


class TestMathSolverSandbox:
    """Tests with mocked sandbox executor."""

    def test_sandbox_path_success(self):
        mock_exec = Mock(return_value={
            "status": "success",
            "data": {"stdout": "42\n", "stderr": ""},
        })
        set_sandbox_executor(mock_exec)

        r = math_solver("6 * 7")
        assert r["status"] == "success"
        assert r["result"] == 42
        mock_exec.assert_called_once()

        # Cleanup
        set_sandbox_executor(None)

    def test_sandbox_failure_falls_back(self):
        mock_exec = Mock(return_value={"status": "error", "error": "timeout"})
        set_sandbox_executor(mock_exec)

        r = math_solver("2 + 2")
        # Should fall back to local and still succeed
        assert r["status"] == "success"
        assert r["result"] == 4

        set_sandbox_executor(None)

    def test_sandbox_exception_falls_back(self):
        mock_exec = Mock(side_effect=RuntimeError("sandbox down"))
        set_sandbox_executor(mock_exec)

        r = math_solver("3 * 3")
        assert r["status"] == "success"
        assert r["result"] == 9

        set_sandbox_executor(None)


class TestNormaliseExpression:
    def test_caret_to_power(self):
        assert "**" in _normalise_expression("2^3")

    def test_unicode_operators(self):
        assert "*" in _normalise_expression("2×3")
        assert "/" in _normalise_expression("6÷2")


class TestBuildScript:
    def test_script_has_import_and_print(self):
        script = _build_script("2 + 2")
        assert "import math" in script
        assert "result = 2 + 2" in script
        assert "print(result)" in script


class TestValidateExpression:
    def test_valid(self):
        assert validate_expression("2 + 2")["valid"] is True

    def test_unbalanced_parens(self):
        r = validate_expression("(2 + 3")
        assert r["valid"] is False
        assert "parentheses" in r["errors"][0].lower()

    def test_unsafe_pattern(self):
        r = validate_expression("__import__('os')")
        assert r["valid"] is False
