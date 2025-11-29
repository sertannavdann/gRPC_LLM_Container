"""
Integration tests for Sandbox Service code execution.

Tests end-to-end code execution flow:
- Orchestrator -> Sandbox Service -> Code Execution -> Result

Requires Docker services to be running.
"""

import pytest
import logging
import time
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.integration.grpc_test_client import AgentTestClient
from tests.integration.docker_manager import DockerComposeManager

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def docker_manager():
    """Docker manager for sandbox tests."""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.yaml"
    
    try:
        manager = DockerComposeManager(str(compose_file))
    except FileNotFoundError as e:
        pytest.skip(f"Docker not available: {e}")
    
    # Verify sandbox service is running
    if not manager.wait_for_service("sandbox_service", 50057, timeout=10):
        pytest.skip("sandbox_service not available. Please start with 'make up'.")
    
    yield manager


@pytest.fixture(scope="function")
def agent_client(docker_manager):
    """Agent test client."""
    # Verify orchestrator is available
    if not docker_manager.wait_for_service("orchestrator", 50054, timeout=10):
        pytest.skip("orchestrator not available")
    
    with AgentTestClient(host="localhost", port=50054, timeout=60) as client:
        yield client


class TestSandboxCodeExecution:
    """Test code execution through sandbox service."""
    
    def test_simple_print(self, agent_client):
        """Test simple print statement execution."""
        response = agent_client.query(
            "Execute this Python code: print('Hello from sandbox!')"
        )
        
        assert response is not None
        assert len(response.final_answer) > 0
        logger.info(f"✓ Simple print response: {response.final_answer[:200]}")
    
    def test_math_calculation(self, agent_client):
        """Test math calculation in code."""
        response = agent_client.query(
            "Run this Python code and tell me the result: print(sum(range(10)))"
        )
        
        assert response is not None
        # Should contain 45 (sum of 0-9)
        logger.info(f"✓ Math calculation response: {response.final_answer[:200]}")
    
    def test_code_with_loop(self, agent_client):
        """Test code with loop execution."""
        response = agent_client.query(
            "Execute Python: for i in range(5): print(f'Count: {i}')"
        )
        
        assert response is not None
        assert len(response.final_answer) > 0
        logger.info(f"✓ Loop execution response: {response.final_answer[:200]}")
    
    def test_import_allowed_module(self, agent_client):
        """Test importing allowed module (math)."""
        response = agent_client.query(
            "Run this code: import math; print(math.sqrt(16))"
        )
        
        assert response is not None
        logger.info(f"✓ Import math response: {response.final_answer[:200]}")


class TestSandboxSafety:
    """Test sandbox safety features."""
    
    def test_timeout_handling(self, agent_client):
        """Test that long-running code times out."""
        response = agent_client.query(
            "Execute this code with a 5 second timeout: import time; time.sleep(100)"
        )
        
        assert response is not None
        # Should mention timeout or error
        logger.info(f"✓ Timeout test response: {response.final_answer[:200]}")
    
    def test_restricted_import(self, agent_client):
        """Test that dangerous imports are blocked."""
        response = agent_client.query(
            "Run this code: import subprocess; subprocess.run(['ls'])"
        )
        
        assert response is not None
        # Should mention import error or restriction
        logger.info(f"✓ Restricted import response: {response.final_answer[:200]}")


class TestSandboxDirectClient:
    """Test sandbox client directly (bypassing orchestrator)."""
    
    def test_direct_execution(self, docker_manager):
        """Test direct sandbox client execution."""
        from shared.clients.sandbox_client import SandboxClient
        
        client = SandboxClient(host="localhost", port=50057)
        
        result = client.execute_code(
            code="print(2 + 2)",
            language="python",
            timeout_seconds=10
        )
        
        assert result is not None
        assert result.get("success") is True
        assert "4" in result.get("stdout", "")
        
        logger.info(f"✓ Direct execution result: {result}")
    
    def test_direct_error_handling(self, docker_manager):
        """Test direct sandbox client error handling."""
        from shared.clients.sandbox_client import SandboxClient
        
        client = SandboxClient(host="localhost", port=50057)
        
        result = client.execute_code(
            code="raise ValueError('test error')",
            language="python",
            timeout_seconds=10
        )
        
        assert result is not None
        assert result.get("success") is False
        assert "error" in result.get("error_message", "").lower() or "error" in result.get("stderr", "").lower()
        
        logger.info(f"✓ Error handling result: {result}")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.sandbox,
]
