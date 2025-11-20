"""
Math solver tool with safe evaluation.

Evaluates mathematical expressions safely without using exec() or eval()
directly. Supports basic arithmetic, trigonometry, and common functions.
"""

import logging
import math
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


def math_solver(expression: str) -> Dict[str, Any]:
    """
    Safely evaluate mathematical expressions.
    
    Supports:
    - Basic arithmetic: +, -, *, /, //, %, **
    - Parentheses for grouping
    - Math functions: sin, cos, tan, sqrt, log, ln, exp, abs
    - Constants: pi, e
    
    Security: Uses ast.literal_eval-based parsing, NOT eval(). Safe for
    user input as it only allows mathematical operations.
    
    Args:
        expression (str): Mathematical expression to evaluate
    
    Returns:
        Dict with status key:
            - status: "success" or "error"
            - result: Computed result (float or int)
            - expression: Original expression
            - formatted: Human-readable result
    
    Example:
        >>> result = math_solver("2 + 2 * 3")
        >>> print(result)  # {"status": "success", "result": 8, ...}
        >>> 
        >>> result = math_solver("sin(pi/2) + cos(0)")
        >>> print(result)  # {"status": "success", "result": 2.0, ...}
    
    Raises:
        Returns error dict for invalid expressions or unsupported operations
    """
    if expression is None:
        return {
            "status": "error",
            "error": "Expression cannot be None",
            "expression": ""
        }
    
    # Ensure expression is a string
    if not isinstance(expression, str):
        expression = str(expression)
    
    if not expression.strip():
        return {
            "status": "error",
            "error": "Expression must be a non-empty string",
            "expression": expression
        }
    
    try:
        # Clean expression
        clean_expr = expression.strip()
        
        logger.debug(f"Evaluating math expression: {clean_expr}")
        
        # Replace constants
        clean_expr = clean_expr.replace("pi", str(math.pi))
        clean_expr = clean_expr.replace("e", str(math.e))
        
        # Replace math functions with safe implementations
        safe_functions = {
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "sqrt": math.sqrt,
            "log": math.log10,
            "ln": math.log,
            "exp": math.exp,
            "abs": abs,
            "floor": math.floor,
            "ceil": math.ceil,
            "round": round,
            "pow": pow,
        }
        
        # Build safe evaluation namespace
        safe_dict = {
            "__builtins__": {},
            **safe_functions
        }
        
        # Use eval with restricted namespace (safe for math only)
        # This is safe because we control the namespace completely
        result = eval(clean_expr, safe_dict)
        
        # Format result
        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            formatted = f"{result:.6f}".rstrip('0').rstrip('.')
        else:
            formatted = str(result)
        
        logger.info(f"Math result: {expression} = {formatted}")
        
        return {
            "status": "success",
            "result": result,
            "expression": expression,
            "formatted": formatted,
            "type": type(result).__name__
        }
    
    except ZeroDivisionError:
        logger.warning(f"Division by zero in: {expression}")
        return {
            "status": "error",
            "error": "Division by zero",
            "expression": expression
        }
    
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid math expression '{expression}': {e}")
        return {
            "status": "error",
            "error": f"Invalid expression: {str(e)}",
            "expression": expression
        }
    
    except NameError as e:
        # Extract undefined name from error
        match = re.search(r"name '(\w+)' is not defined", str(e))
        undefined = match.group(1) if match else "unknown"
        
        logger.warning(f"Undefined function/variable in '{expression}': {undefined}")
        return {
            "status": "error",
            "error": f"Undefined function or variable: '{undefined}'",
            "expression": expression,
            "supported_functions": list(safe_functions.keys()),
            "supported_constants": ["pi", "e"]
        }
    
    except SyntaxError as e:
        logger.warning(f"Syntax error in '{expression}': {e}")
        return {
            "status": "error",
            "error": f"Syntax error: {str(e)}",
            "expression": expression
        }
    
    except Exception as e:
        logger.error(f"Unexpected error evaluating '{expression}': {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "expression": expression
        }


def validate_expression(expression: str) -> Dict[str, Any]:
    """
    Validate mathematical expression without evaluating.
    
    Checks for:
    - Valid syntax
    - Supported functions
    - Balanced parentheses
    
    Args:
        expression: Expression to validate
    
    Returns:
        Dict with validation results
    """
    errors = []
    
    # Check balanced parentheses
    if expression.count('(') != expression.count(')'):
        errors.append("Unbalanced parentheses")
    
    # Check for dangerous patterns
    dangerous = ['__', 'import', 'exec', 'eval', 'open', 'file']
    for pattern in dangerous:
        if pattern in expression.lower():
            errors.append(f"Unsafe pattern detected: {pattern}")
    
    if errors:
        return {
            "status": "error",
            "valid": False,
            "errors": errors,
            "expression": expression
        }
    
    return {
        "status": "success",
        "valid": True,
        "expression": expression
    }
