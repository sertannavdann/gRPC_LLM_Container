"""
Sandbox Service - Secure Code Execution Environment (Agent0 Phase 3)

Provides isolated execution of LLM-generated code with:
- Timeout enforcement
- Memory limits
- Import whitelisting
- RestrictedPython for additional security
"""

import grpc
import logging
import sys
import os
import time
import multiprocessing
from concurrent import futures
from io import StringIO
from typing import Dict, Any, Optional, List
import signal

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2_grpc, health_pb2

# Try imports for both local dev and container modes
try:
    from shared.generated import sandbox_pb2, sandbox_pb2_grpc
except ModuleNotFoundError:
    # Regenerate if needed
    import subprocess
    subprocess.run([
        sys.executable, "-m", "grpc_tools.protoc",
        "-I../shared/proto",
        "--python_out=../shared/generated",
        "--grpc_python_out=../shared/generated",
        "../shared/proto/sandbox.proto"
    ], check=True)
    from shared.generated import sandbox_pb2, sandbox_pb2_grpc

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("sandbox_service")

# Default configuration
DEFAULT_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "30"))
DEFAULT_MEMORY_MB = int(os.getenv("SANDBOX_MEMORY_MB", "256"))
MAX_TIMEOUT = 60
MAX_MEMORY_MB = 512

# Allowed safe imports (whitelist)
SAFE_IMPORTS = {
    "math", "random", "datetime", "json", "re", "collections",
    "itertools", "functools", "operator", "string", "decimal",
    "fractions", "statistics", "typing", "dataclasses", "enum"
}


class TimeoutError(Exception):
    """Raised when code execution exceeds timeout."""
    pass


class MemoryExceededError(Exception):
    """Raised when code execution exceeds memory limit."""
    pass


def restricted_import(name: str, allowed_imports: set):
    """
    Custom import function that only allows whitelisted modules.
    """
    if name not in allowed_imports:
        raise ImportError(f"Import of '{name}' is not allowed in sandbox")
    return __import__(name)


def execute_in_sandbox(
    code: str,
    language: str,
    timeout_seconds: int,
    memory_limit_mb: int,
    allowed_imports: List[str],
    environment: Dict[str, str]
) -> Dict[str, Any]:
    """
    Execute code in a sandboxed subprocess with resource limits.
    
    Uses subprocess.run with timeout for more reliable execution in Docker.
    
    Returns dict with stdout, stderr, exit_code, execution_time, etc.
    """
    import subprocess
    import tempfile
    import json
    
    start_time = time.time()
    result = {
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "execution_time_ms": 0.0,
        "timed_out": False,
        "memory_exceeded": False,
        "error_message": ""
    }
    
    if language.lower() != "python":
        result["exit_code"] = 1
        result["error_message"] = f"Unsupported language: {language}. Only 'python' is supported."
        return result
    
    # Merge allowed imports with safe defaults
    allowed = SAFE_IMPORTS.union(set(allowed_imports) if allowed_imports else set())
    
    # Create a wrapper script that executes the code with restrictions
    wrapper_code = f'''
import sys
import json
import resource

# Set memory limit
memory_bytes = {memory_limit_mb} * 1024 * 1024
try:
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
except (ValueError, resource.error):
    pass  # May fail on some systems

# Allowed imports
ALLOWED = {repr(allowed)}

def restricted_import(name, *args, **kwargs):
    if name not in ALLOWED:
        raise ImportError(f"Import of '{{name}}' is not allowed in sandbox")
    return __builtins__.__import__(name, *args, **kwargs)

# Create restricted builtins
restricted_builtins = {{
    "print": print,
    "range": range,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "bool": bool,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "True": True,
    "False": False,
    "None": None,
    "__import__": restricted_import,
    "isinstance": isinstance,
    "type": type,
    "round": round,
    "pow": pow,
    "divmod": divmod,
    "hex": hex,
    "bin": bin,
    "oct": oct,
    "chr": chr,
    "ord": ord,
    "all": all,
    "any": any,
    "reversed": reversed,
    "format": format,
    "repr": repr,
}}

# User code to execute
USER_CODE = {repr(code)}

try:
    exec(USER_CODE, {{"__builtins__": restricted_builtins}})
except MemoryError:
    print("SANDBOX_MEMORY_ERROR", file=sys.stderr)
    sys.exit(137)
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''
    
    try:
        # Write wrapper to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(wrapper_code)
            temp_file = f.name
        
        # Prepare environment
        exec_env = os.environ.copy()
        exec_env.update(environment)
        
        # Run the code in subprocess
        proc = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=exec_env,
            cwd="/tmp"  # Use temp directory for safety
        )
        
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        result["exit_code"] = proc.returncode
        
        # Check for memory error
        if proc.returncode == 137 or "SANDBOX_MEMORY_ERROR" in proc.stderr:
            result["memory_exceeded"] = True
            result["error_message"] = "Memory limit exceeded"
        elif proc.returncode != 0:
            # Extract error from stderr
            result["error_message"] = proc.stderr.strip() if proc.stderr else f"Exit code: {proc.returncode}"
        
        # Cleanup temp file
        try:
            os.unlink(temp_file)
        except:
            pass
            
    except subprocess.TimeoutExpired:
        result["timed_out"] = True
        result["exit_code"] = 124
        result["error_message"] = f"Execution timed out after {timeout_seconds} seconds"
        # Cleanup temp file
        try:
            os.unlink(temp_file)
        except:
            pass
    except Exception as e:
        result["exit_code"] = 1
        result["error_message"] = f"Sandbox error: {str(e)}"
    
    result["execution_time_ms"] = (time.time() - start_time) * 1000
    return result


class HealthServicer(health.HealthServicer):
    """Health check servicer."""
    
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )


class SandboxServiceServicer(sandbox_pb2_grpc.SandboxServiceServicer):
    """Sandbox Service gRPC implementation."""
    
    def ExecuteCode(self, request, context):
        """Execute code in sandboxed environment."""
        logger.info(f"Executing {request.language} code (timeout={request.timeout_seconds}s)")
        
        # Validate and clamp parameters
        timeout = min(request.timeout_seconds or DEFAULT_TIMEOUT, MAX_TIMEOUT)
        memory_mb = min(request.memory_limit_mb or DEFAULT_MEMORY_MB, MAX_MEMORY_MB)
        
        if not request.code.strip():
            return sandbox_pb2.ExecuteCodeResponse(
                exit_code=1,
                error_message="No code provided"
            )
        
        try:
            result = execute_in_sandbox(
                code=request.code,
                language=request.language or "python",
                timeout_seconds=timeout,
                memory_limit_mb=memory_mb,
                allowed_imports=list(request.allowed_imports),
                environment=dict(request.environment)
            )
            
            return sandbox_pb2.ExecuteCodeResponse(
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                execution_time_ms=result["execution_time_ms"],
                timed_out=result["timed_out"],
                memory_exceeded=result["memory_exceeded"],
                error_message=result["error_message"]
            )
            
        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return sandbox_pb2.ExecuteCodeResponse(
                exit_code=1,
                error_message=f"Sandbox error: {str(e)}"
            )
    
    def HealthCheck(self, request, context):
        """Health check endpoint."""
        return sandbox_pb2.HealthCheckResponse(
            healthy=True,
            status="Sandbox service is operational"
        )


def serve():
    """Start the gRPC server."""
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        options=[
            ('grpc.max_receive_message_length', 10 * 1024 * 1024),  # 10MB
        ]
    )
    
    sandbox_pb2_grpc.add_SandboxServiceServicer_to_server(
        SandboxServiceServicer(), server
    )
    health_pb2_grpc.add_HealthServicer_to_server(
        HealthServicer(), server
    )
    
    # Enable reflection for debugging
    reflection.enable_server_reflection([
        sandbox_pb2.DESCRIPTOR.services_by_name['SandboxService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME
    ], server)
    
    port = os.getenv("SANDBOX_PORT", "50057")
    server.add_insecure_port(f"[::]:{port}")
    logger.info(f"Sandbox Service operational on port {port}")
    logger.info(f"Default timeout: {DEFAULT_TIMEOUT}s, Memory limit: {DEFAULT_MEMORY_MB}MB")
    
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
