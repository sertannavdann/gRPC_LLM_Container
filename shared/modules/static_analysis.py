"""
Static import analysis for NEXUS module system.

Provides AST-based import checking to detect forbidden imports before execution.
Single source of truth for static import validation.
"""
import ast
import logging
from typing import List, Set

from shared.modules.security_policy import FORBIDDEN_IMPORTS

logger = logging.getLogger(__name__)


class StaticImportChecker:
    """
    AST-based static import checker.

    Analyzes Python source code before execution to detect forbidden imports.
    """

    @staticmethod
    def check_imports(source_code: str, forbidden: Set[str]) -> List[str]:
        """
        Check source code for forbidden imports using AST analysis.

        Args:
            source_code: Python source code to check
            forbidden: Set of forbidden import names

        Returns:
            List of violation descriptions (empty if no violations)
        """
        violations = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            # Syntax errors will be caught during validation
            logger.debug(f"Syntax error during static import check: {e}")
            return violations

        # Walk the AST and check all imports
        for node in ast.walk(tree):
            # Check "import module"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden:
                        violations.append(
                            f"Line {node.lineno}: Import '{alias.name}' not in allowed list"
                        )

            # Check "from module import name"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Check base module
                    if node.module in forbidden:
                        violations.append(
                            f"Line {node.lineno}: Import '{node.module}' not in allowed list"
                        )

                    # Check specific imports like "from os import system"
                    for alias in node.names:
                        full_name = f"{node.module}.{alias.name}"
                        if full_name in forbidden:
                            violations.append(
                                f"Line {node.lineno}: Import '{full_name}' is forbidden"
                            )

            # Check for dynamic import calls and dangerous function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == "__import__":
                        violations.append(
                            f"Line {node.lineno}: Dynamic __import__ call detected"
                        )
                    elif node.func.id in {"eval", "exec", "compile"}:
                        # Check if these dangerous functions are in the forbidden set
                        if node.func.id in forbidden:
                            violations.append(
                                f"Line {node.lineno}: Import '{node.func.id}' is forbidden"
                            )

        return violations


def check_imports(source: str, forbidden: Set[str] = None) -> List[str]:
    """
    Convenience function for checking imports against forbidden set.

    Args:
        source: Python source code to check
        forbidden: Set of forbidden imports (defaults to FORBIDDEN_IMPORTS)

    Returns:
        List of violation descriptions
    """
    if forbidden is None:
        forbidden = FORBIDDEN_IMPORTS

    return StaticImportChecker.check_imports(source, forbidden)
