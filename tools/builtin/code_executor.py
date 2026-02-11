"""
Code Executor Tool - Execute code in a sandboxed environment.

Wraps the SandboxClient for secure code execution with:
- Timeout enforcement
- Memory limits
- Import whitelisting

This tool is registered with the LocalToolRegistry for LLM access.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Module-level client reference (set by orchestrator during init)
_sandbox_client = None


def set_sandbox_client(client):
    """Set the sandbox client instance (called by orchestrator)."""
    global _sandbox_client
    _sandbox_client = client


def execute_code(
    code: str,
    language: str = "python",
    timeout_seconds: int = 30,
    allowed_imports: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Execute code in a sandboxed environment.
    
    Use this tool to run Python code snippets safely. The code runs
    in an isolated environment with restricted imports and resource limits.
    
    Args:
        code: The Python code to execute
        language: Programming language (only 'python' supported currently)
        timeout_seconds: Maximum execution time (default 30, max 60)
        allowed_imports: Additional modules to allow importing (beyond safe defaults)
    
    Returns:
        Dict with status, stdout/stderr, execution time, and any errors
    
    Examples:
        - execute_code("print(2 + 2)")
        - execute_code("import math; print(math.sqrt(16))")
        - execute_code("for i in range(5): print(i)")
    """
    global _sandbox_client
    
    if _sandbox_client is None:
        logger.error("Sandbox client not initialized")
        return {
            "status": "error",
            "error": "Sandbox service not available. Code execution is disabled.",
            "data": None
        }
    
    if not code or not code.strip():
        return {
            "status": "error",
            "error": "No code provided",
            "data": None
        }
    
    # Validate language
    language = language.lower()
    if language != "python":
        return {
            "status": "error",
            "error": f"Unsupported language: {language}. Only 'python' is supported.",
            "data": None
        }
    
    # Clamp timeout
    timeout_seconds = max(1, min(timeout_seconds, 60))
    
    try:
        logger.info(f"Executing code ({len(code)} chars, timeout={timeout_seconds}s)")
        
        result = _sandbox_client.execute_code(
            code=code,
            language=language,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=256,
            allowed_imports=allowed_imports or []
        )
        
        # Format response
        if result.get("success"):
            return {
                "status": "success",
                "data": {
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "execution_time_ms": result.get("execution_time_ms", 0)
                },
                "error": None
            }
        else:
            error_msg = result.get("error_message", "Unknown error")
            
            if result.get("timed_out"):
                error_msg = f"Execution timed out after {timeout_seconds} seconds"
            elif result.get("memory_exceeded"):
                error_msg = "Memory limit exceeded"
            
            return {
                "status": "error",
                "error": error_msg,
                "data": {
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "exit_code": result.get("exit_code", -1)
                }
            }
    
    except Exception as e:
        logger.error(f"Code execution failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Execution failed: {str(e)}",
            "data": None
        }
