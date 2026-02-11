"""
Sandbox Client - Interface for code execution in sandboxed environment.
"""

import grpc
import logging
from typing import Dict, List, Optional, Any
from .base_client import BaseClient

# Try imports for both local dev and container modes
try:
    from shared.generated import sandbox_pb2, sandbox_pb2_grpc
except ModuleNotFoundError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'generated'))
    import sandbox_pb2
    import sandbox_pb2_grpc

logger = logging.getLogger(__name__)


class SandboxClient(BaseClient):
    """Client for the Sandbox Service."""
    
    def __init__(self, host: str = "sandbox_service", port: int = 50057):
        super().__init__(host, port)
        self.stub = sandbox_pb2_grpc.SandboxServiceStub(self.channel)
    
    def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 30,
        memory_limit_mb: int = 256,
        allowed_imports: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Execute code in a sandboxed environment.
        
        Args:
            code: Code to execute
            language: Programming language (currently only 'python' supported)
            timeout_seconds: Maximum execution time
            memory_limit_mb: Maximum memory usage
            allowed_imports: Additional allowed import modules
            environment: Environment variables to set
        
        Returns:
            Dict with keys:
                - stdout: Standard output
                - stderr: Standard error
                - exit_code: Process exit code
                - execution_time_ms: Time taken to execute
                - timed_out: True if execution exceeded timeout
                - memory_exceeded: True if memory limit exceeded
                - error_message: Error description if failed
                - success: True if exit_code == 0
        """
        try:
            response = self.stub.ExecuteCode(
                sandbox_pb2.ExecuteCodeRequest(
                    code=code,
                    language=language,
                    timeout_seconds=timeout_seconds,
                    memory_limit_mb=memory_limit_mb,
                    allowed_imports=allowed_imports or [],
                    environment=environment or {}
                ),
                timeout=timeout_seconds + 10  # Extra buffer for RPC overhead
            )
            
            return {
                "stdout": response.stdout,
                "stderr": response.stderr,
                "exit_code": response.exit_code,
                "execution_time_ms": response.execution_time_ms,
                "timed_out": response.timed_out,
                "memory_exceeded": response.memory_exceeded,
                "error_message": response.error_message,
                "success": response.exit_code == 0 and not response.timed_out
            }
            
        except grpc.RpcError as e:
            logger.error(f"Sandbox execution failed: {e.code().name}")
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "execution_time_ms": 0,
                "timed_out": False,
                "memory_exceeded": False,
                "error_message": f"Sandbox Service Error: {e.details()}",
                "success": False
            }
    
    def health_check(self) -> bool:
        """Check if sandbox service is healthy."""
        try:
            response = self.stub.HealthCheck(
                sandbox_pb2.HealthCheckRequest(),
                timeout=5
            )
            return response.healthy
        except grpc.RpcError:
            return False
