"""
Math solver tool — generates Python code and executes it on the sandbox.

Instead of a fragile eval()-based approach this tool:
    1. Translates a symbolic math expression into a short Python script.
    2. Delegates execution to the sandbox_service (via execute_code).
    3. Returns the numeric result along with the generated code so the
       UI can display the working.

If the sandbox is unavailable a restricted local evaluator is used as
fallback.
"""

import logging
import math
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Module-level reference to sandbox executor — set by orchestrator init.
_execute_code_fn = None


def set_sandbox_executor(fn):
    """Inject the execute_code callable (called by orchestrator at startup)."""
    global _execute_code_fn
    _execute_code_fn = fn
    logger.info("math_solver: sandbox executor wired")


# ── Safe local-eval namespace (fallback when sandbox unavailable) ─────
_SAFE_NAMESPACE: Dict[str, Any] = {
    "__builtins__": {},
    "abs": abs,
    "round": round,
    "pow": pow,
    "min": min,
    "max": max,
    "int": int,
    "float": float,
    # math module functions
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sqrt": math.sqrt,
    "log": math.log10,
    "log10": math.log10,
    "log2": math.log2,
    "ln": math.log,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}


def math_solver(expression: str) -> Dict[str, Any]:
    """
    Safely evaluate mathematical expressions.

    Supports:
    - Basic arithmetic: +, -, *, /, //, %, **
    - Parentheses for grouping
    - Math functions: sin, cos, tan, sqrt, log, ln, exp, abs, floor, ceil
    - Constants: pi, e, tau

    The expression is compiled to a Python script and executed on the
    sandbox service when available, falling back to a restricted local
    evaluation otherwise.

    Args:
        expression (str): Mathematical expression to evaluate

    Returns:
        Dict with status key:
            - status: "success" or "error"
            - result: Computed result (float or int)
            - expression: Original expression
            - formatted: Human-readable result
            - code: Generated Python code (when sandbox used)

    Example:
        >>> result = math_solver("2 + 2 * 3")
        >>> print(result)  # {"status": "success", "result": 8, ...}
    """
    if expression is None:
        return {"status": "error", "error": "Expression cannot be None", "expression": ""}

    if not isinstance(expression, str):
        expression = str(expression)

    expression = expression.strip()
    if not expression:
        return {"status": "error", "error": "Expression must be a non-empty string", "expression": expression}

    # Reject dangerous patterns early
    _dangerous = {"__", "import", "exec", "eval", "open", "file", "os.", "sys."}
    expr_lower = expression.lower()
    for pattern in _dangerous:
        if pattern in expr_lower:
            return {"status": "error", "error": f"Unsafe pattern detected: {pattern}", "expression": expression}

    logger.debug(f"Evaluating math expression: {expression}")

    # Normalise common aliases
    clean = _normalise_expression(expression)

    # Build a tiny Python script
    code = _build_script(clean)

    # ── Try sandbox first ─────────────────────────────────────────────
    if _execute_code_fn is not None:
        result = _run_on_sandbox(code, expression)
        if result is not None:
            return result
        logger.warning("Sandbox execution failed — falling back to local eval")

    # ── Local fallback ────────────────────────────────────────────────
    return _run_local(clean, expression, code)


# ── Internal helpers ──────────────────────────────────────────────────

def _normalise_expression(expr: str) -> str:
    """
    Turn human-friendly notation into valid Python.

    Handles ``^`` → ``**``, ``×`` → ``*``, ``÷`` → ``/``.
    Keeps bare ``pi`` / ``e`` as names (NOT replaced with floats so
    that ``exp``, ``ceil``, etc. are not broken).
    """
    expr = expr.replace("^", "**")
    expr = expr.replace("\u00d7", "*").replace("\u00f7", "/")
    expr = expr.replace("\u2018", "").replace("\u2019", "")
    return expr


def _build_script(clean_expr: str) -> str:
    """Build a self-contained Python script that prints the result."""
    return (
        "import math\n"
        "pi = math.pi\n"
        "e = math.e\n"
        "tau = math.tau\n"
        "sin = math.sin\n"
        "cos = math.cos\n"
        "tan = math.tan\n"
        "asin = math.asin\n"
        "acos = math.acos\n"
        "atan = math.atan\n"
        "sqrt = math.sqrt\n"
        "log = math.log10\n"
        "log10 = math.log10\n"
        "log2 = math.log2\n"
        "ln = math.log\n"
        "exp = math.exp\n"
        "floor = math.floor\n"
        "ceil = math.ceil\n"
        "factorial = math.factorial\n"
        "gcd = math.gcd\n"
        f"result = {clean_expr}\n"
        "print(result)\n"
    )


def _run_on_sandbox(code: str, original_expr: str) -> Optional[Dict[str, Any]]:
    """Execute *code* on the sandbox and parse the printed result."""
    try:
        sandbox_result = _execute_code_fn(code=code, language="python", timeout_seconds=15)
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


def _run_local(clean_expr: str, original_expr: str, code: str) -> Dict[str, Any]:
    """Evaluate *clean_expr* in a restricted local namespace."""
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
            "status": "error",
            "error": f"Undefined function or variable: '{name}'",
            "expression": original_expr,
            "supported_functions": sorted(k for k in _SAFE_NAMESPACE if k != "__builtins__"),
        }
    except SyntaxError as exc:
        return {"status": "error", "error": f"Syntax error: {exc}", "expression": original_expr}
    except Exception as exc:
        logger.error(f"Unexpected math error: {exc}", exc_info=True)
        return {"status": "error", "error": f"Unexpected error: {exc}", "expression": original_expr}


# ── Formatting ────────────────────────────────────────────────────────

def _parse_number(text: str):
    """Parse a string into int or float."""
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
        "status": "success",
        "result": value,
        "expression": original_expr,
        "formatted": formatted,
        "code": code,
        "type": type(value).__name__,
    }


def validate_expression(expression: str) -> Dict[str, Any]:
    """
    Validate a mathematical expression without evaluating.

    Checks for valid syntax, supported functions, balanced parentheses.
    """
    errors = []

    if expression.count("(") != expression.count(")"):
        errors.append("Unbalanced parentheses")

    dangerous = ["__", "import", "exec", "eval", "open", "file"]
    for pat in dangerous:
        if pat in expression.lower():
            errors.append(f"Unsafe pattern detected: {pat}")

    if errors:
        return {"status": "error", "valid": False, "errors": errors, "expression": expression}

    return {"status": "success", "valid": True, "expression": expression}
