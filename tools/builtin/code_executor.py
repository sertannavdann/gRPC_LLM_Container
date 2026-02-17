"""
CodeExecutorTool - Execute code in a sandboxed environment.

Wraps the SandboxClient for secure code execution.
Refactored from function-based to BaseTool class.
"""
import logging
from typing import Dict, Any, Optional, List

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class CodeExecutorTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """Execute code in a sandboxed environment."""

    name = "execute_code"
    description = (
        "Execute Python code in a sandboxed environment with timeout and memory limits."
    )
    version = "2.0.0"

    def __init__(self, sandbox_client=None):
        self._sandbox_client = sandbox_client

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        code = kwargs.get("code")
        if not code or not str(code).strip():
            raise ValueError("No code provided")

        language = kwargs.get("language", "python").lower()
        if language != "python":
            raise ValueError(f"Unsupported language: {language}. Only 'python' is supported.")

        timeout = max(1, min(kwargs.get("timeout_seconds", 30), 60))

        return {
            "code": code,
            "language": language,
            "timeout_seconds": timeout,
            "allowed_imports": kwargs.get("allowed_imports") or [],
        }

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if self._sandbox_client is None:
            return {
                "status": "error",
                "error": "Sandbox service not available. Code execution is disabled.",
                "data": None,
            }

        try:
            logger.info(f"Executing code ({len(request['code'])} chars, timeout={request['timeout_seconds']}s)")

            result = self._sandbox_client.execute_code(
                code=request["code"],
                language=request["language"],
                timeout_seconds=request["timeout_seconds"],
                memory_limit_mb=256,
                allowed_imports=request["allowed_imports"],
            )

            if result.get("success"):
                return {
                    "status": "success",
                    "data": {
                        "stdout": result.get("stdout", ""),
                        "stderr": result.get("stderr", ""),
                        "execution_time_ms": result.get("execution_time_ms", 0),
                    },
                    "error": None,
                }
            else:
                error_msg = result.get("error_message", "Unknown error")
                if result.get("timed_out"):
                    error_msg = f"Execution timed out after {request['timeout_seconds']} seconds"
                elif result.get("memory_exceeded"):
                    error_msg = "Memory limit exceeded"

                return {
                    "status": "error",
                    "error": error_msg,
                    "data": {
                        "stdout": result.get("stdout", ""),
                        "stderr": result.get("stderr", ""),
                        "exit_code": result.get("exit_code", -1),
                    },
                }

        except Exception as e:
            logger.error(f"Code execution failed: {e}", exc_info=True)
            return {"status": "error", "error": f"Execution failed: {str(e)}", "data": None}

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response


# ── Backward-compat module-level function ────────────────────────────

_default_tool: Optional[CodeExecutorTool] = None


def execute_code(
    code: str,
    language: str = "python",
    timeout_seconds: int = 30,
    allowed_imports: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Legacy wrapper."""
    global _default_tool
    if _default_tool is None:
        _default_tool = CodeExecutorTool()
    return _default_tool(
        code=code, language=language,
        timeout_seconds=timeout_seconds,
        allowed_imports=allowed_imports,
    )


def set_sandbox_client(client):
    """Legacy wrapper to set sandbox client."""
    global _default_tool
    if _default_tool is None:
        _default_tool = CodeExecutorTool(sandbox_client=client)
    else:
        _default_tool._sandbox_client = client
