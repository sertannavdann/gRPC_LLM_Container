"""
MathSolverTool - Safely evaluate mathematical expressions.

Generates Python code and executes on sandbox or restricted local fallback.
Refactored from function-based to BaseTool class.
"""
import logging
import math
import re
from typing import Dict, Any, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


# Safe local-eval namespace (fallback when sandbox unavailable)
_SAFE_NAMESPACE: Dict[str, Any] = {
    "__builtins__": {},
    "abs": abs, "round": round, "pow": pow, "min": min, "max": max,
    "int": int, "float": float,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sqrt": math.sqrt, "log": math.log10, "log10": math.log10,
    "log2": math.log2, "ln": math.log, "exp": math.exp,
    "floor": math.floor, "ceil": math.ceil,
    "factorial": math.factorial, "gcd": math.gcd,
    "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf,
}


class MathSolverTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """Safely evaluate mathematical expressions."""

    name = "math_solver"
    description = (
        "Evaluate mathematical expressions safely. Supports arithmetic, "
        "trig, logarithms, constants (pi, e, tau)."
    )
    version = "2.0.0"

    def __init__(self, sandbox_executor=None):
        self._execute_code_fn = sandbox_executor

    def set_sandbox_executor(self, fn):
        """Wire sandbox executor (called by orchestrator)."""
        self._execute_code_fn = fn

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        expression = kwargs.get("expression")
        if expression is None:
            raise ValueError("Expression cannot be None")
        if not isinstance(expression, str):
            expression = str(expression)
        expression = expression.strip()
        if not expression:
            raise ValueError("Expression must be a non-empty string")

        # Reject dangerous patterns
        expr_lower = expression.lower()
        for pattern in ("__", "import", "exec", "eval", "open", "file", "os.", "sys."):
            if pattern in expr_lower:
                raise ValueError(f"Unsafe pattern detected: {pattern}")

        return {"expression": expression}

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        expression = request["expression"]
        clean = _normalise_expression(expression)
        code = _build_script(clean)

        # Try sandbox first
        if self._execute_code_fn is not None:
            result = self._run_on_sandbox(code, expression)
            if result is not None:
                return result
            logger.warning("Sandbox execution failed -- falling back to local eval")

        # Local fallback
        return _run_local(clean, expression, code)

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response

    def _run_on_sandbox(self, code: str, original_expr: str) -> Optional[Dict[str, Any]]:
        """Execute code on sandbox and parse the printed result."""
        try:
            sandbox_result = self._execute_code_fn(code=code, language="python", timeout_seconds=15)
            if sandbox_result.get("status") != "success":
                return None
            stdout = sandbox_result.get("data", {}).get("stdout", "").strip()
            if not stdout:
                return None
            last_line = stdout.strip().splitlines()[-1]
            value = _parse_number(last_line)
            return _success_response(value, original_expr, code)
        except Exception as exc:
            logger.warning(f"Sandbox math failed: {exc}")
            return None


# ── Internal helpers ──────────────────────────────────────────────────

def _normalise_expression(expr: str) -> str:
    expr = expr.replace("^", "**")
    expr = expr.replace("\u00d7", "*").replace("\u00f7", "/")
    expr = expr.replace("\u2018", "").replace("\u2019", "")
    return expr


def _build_script(clean_expr: str) -> str:
    return (
        "import math\n"
        "pi = math.pi\ne = math.e\ntau = math.tau\n"
        "sin = math.sin\ncos = math.cos\ntan = math.tan\n"
        "asin = math.asin\nacos = math.acos\natan = math.atan\n"
        "sqrt = math.sqrt\nlog = math.log10\nlog10 = math.log10\n"
        "log2 = math.log2\nln = math.log\nexp = math.exp\n"
        "floor = math.floor\nceil = math.ceil\n"
        "factorial = math.factorial\ngcd = math.gcd\n"
        f"result = {clean_expr}\nprint(result)\n"
    )


def _run_local(clean_expr: str, original_expr: str, code: str) -> Dict[str, Any]:
    try:
        result = eval(clean_expr, _SAFE_NAMESPACE)  # noqa: S307
        return _success_response(result, original_expr, code)
    except ZeroDivisionError:
        return {"status": "error", "error": "Division by zero", "expression": original_expr}
    except (ValueError, TypeError) as exc:
        return {"status": "error", "error": f"Invalid expression: {exc}", "expression": original_expr}
    except NameError as exc:
        match = re.search(r"name '(\w+)' is not defined", str(exc))
        name = match.group(1) if match else "unknown"
        return {
            "status": "error", "error": f"Undefined function or variable: '{name}'",
            "expression": original_expr,
            "supported_functions": sorted(k for k in _SAFE_NAMESPACE if k != "__builtins__"),
        }
    except SyntaxError as exc:
        return {"status": "error", "error": f"Syntax error: {exc}", "expression": original_expr}
    except Exception as exc:
        return {"status": "error", "error": f"Unexpected error: {exc}", "expression": original_expr}


def _parse_number(text: str):
    text = text.strip()
    try:
        val = float(text)
        return int(val) if val == int(val) else val
    except ValueError:
        return text


def _success_response(value, original_expr: str, code: str) -> Dict[str, Any]:
    if isinstance(value, float) and value == int(value):
        value = int(value)
    formatted = f"{value:.6f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    return {
        "status": "success", "result": value, "expression": original_expr,
        "formatted": formatted, "code": code, "type": type(value).__name__,
    }


# ── Backward-compat module-level function ────────────────────────────

_default_tool: Optional[MathSolverTool] = None


def math_solver(expression: str) -> Dict[str, Any]:
    """Legacy wrapper."""
    global _default_tool
    if _default_tool is None:
        _default_tool = MathSolverTool()
    return _default_tool(expression=expression)


def set_sandbox_executor(fn):
    """Legacy wrapper to wire sandbox executor."""
    global _default_tool
    if _default_tool is None:
        _default_tool = MathSolverTool(sandbox_executor=fn)
    else:
        _default_tool.set_sandbox_executor(fn)
    logger.info("math_solver: sandbox executor wired")


def validate_expression(expression: str) -> Dict[str, Any]:
    """Validate a math expression without evaluating."""
    errors = []
    if expression.count("(") != expression.count(")"):
        errors.append("Unbalanced parentheses")
    for pat in ("__", "import", "exec", "eval", "open", "file"):
        if pat in expression.lower():
            errors.append(f"Unsafe pattern detected: {pat}")
    if errors:
        return {"status": "error", "valid": False, "errors": errors, "expression": expression}
    return {"status": "success", "valid": True, "expression": expression}
