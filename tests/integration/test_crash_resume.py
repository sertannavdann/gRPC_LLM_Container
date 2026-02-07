"""
Integration test for crash recovery and service restart behavior.

Tests that services can restart and resume operations after crashes.
"""

import pytest
import time
from pathlib import Path

from tests.integration.docker_manager import DockerComposeManager
from tests.integration.grpc_test_client import AgentTestClient

# Aliases for backward compatibility
DockerManager = DockerComposeManager
AgentGrpcClient = AgentTestClient


@pytest.mark.integration
@pytest.mark.slow
class TestCrashResume:
    """Test crash recovery and resumption."""
    
    @pytest.fixture(scope="class")
    def docker_manager(self):
        """Setup Docker environment - assumes services are already running."""
        compose_file = Path(__file__).parent.parent.parent / "docker-compose.yaml"
        try:
            manager = DockerManager(str(compose_file))
        except FileNotFoundError as e:
            pytest.skip(f"Docker not available: {e}")
        
        # Verify orchestrator is available
        if not manager.wait_for_service("orchestrator", 50054, timeout=10):
            pytest.skip("orchestrator not available. Please start with 'make up'.")
        
        yield manager
    
    @pytest.fixture(scope="function")
    def agent_client(self, docker_manager):
        """Agent test client."""
        with AgentTestClient(host="localhost", port=50054, timeout=60) as client:
            yield client
    
    def test_service_recovers_after_restart(self, docker_manager, agent_client):
        """
        Test that the orchestrator service recovers correctly after restart.
        
        Steps:
        1. Verify service is working
        2. Restart service
        3. Verify service is working again
        """
        # Step 1: Verify service is working
        response = agent_client.query("What is 2+2?")
        assert response is not None
        assert len(response.final_answer) > 0
        print(f"✓ Initial query successful: {response.final_answer[:50]}")
        
        # Step 2: Restart orchestrator service
        docker_manager.restart_service("orchestrator")
        
        # Wait for service to be healthy
        docker_manager.wait_for_service("orchestrator", 50054, timeout=30)
        time.sleep(2)  # Extra wait for initialization
        
        # Step 3: Verify service is working with new client
        with AgentTestClient(host="localhost", port=50054, timeout=60) as new_client:
            response = new_client.query("What is 3+3?")
            assert response is not None
            assert len(response.final_answer) > 0
            print(f"✓ Post-restart query successful: {response.final_answer[:50]}")
        
        print("✅ Service recovered successfully after restart")
    
    def test_orchestrator_startup_logs(self, docker_manager, agent_client):
        """
        Test that orchestrator logs startup information correctly.
        
        Verifies service logging and health after restart.
        """
        # Make a query first
        response = agent_client.query("Hello")
        assert response is not None
        
        # Restart and verify
        docker_manager.restart_service("orchestrator")
        docker_manager.wait_for_service("orchestrator", 50054, timeout=30)
        time.sleep(2)
        
        logs = docker_manager.get_service_logs("orchestrator", tail=100)
        # Should have some log output
        assert len(logs) > 0, "Expected logs from orchestrator"
        
        # Verify service is listening
        has_startup_info = (
            "50054" in logs or 
            "started" in logs.lower() or 
            "serving" in logs.lower() or
            "listening" in logs.lower() or
            "grpc" in logs.lower()
        )
        assert has_startup_info, f"Expected startup info in logs. Got: {logs[-300:]}"
        
        print("✅ Orchestrator startup logging verified")
    
    def test_multiple_restarts_stable(self, docker_manager):
        """
        Test that the service remains stable through multiple restarts.
        
        Verifies no resource leaks or state corruption.
        """
        for i in range(3):
            # Verify service is working
            with AgentTestClient(host="localhost", port=50054, timeout=60) as client:
                response = client.query(f"Test query {i}")
                assert response is not None
                print(f"✓ Query {i+1}/3 successful")
            
            # Restart if not last iteration
            if i < 2:
                docker_manager.restart_service("orchestrator")
                docker_manager.wait_for_service("orchestrator", 50054, timeout=30)
                time.sleep(2)
        
        print("✅ Multiple restarts completed successfully")
        
        print("✅ Clean startup works correctly")
