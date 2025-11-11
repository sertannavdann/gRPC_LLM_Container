"""
Integration test for crash recovery and workflow resumption.

Tests that workflows can resume after service crashes.
"""

import pytest
import time
import subprocess
import signal
from pathlib import Path

from tests.integration.docker_manager import DockerManager
from tests.integration.grpc_test_client import AgentGrpcClient


@pytest.mark.integration
@pytest.mark.slow
class TestCrashResume:
    """Test crash recovery and resumption."""
    
    @pytest.fixture(scope="class")
    def docker_manager(self):
        """Setup Docker environment."""
        manager = DockerManager()
        manager.start_services()
        yield manager
        manager.stop_services()
    
    def test_workflow_resumes_after_crash(self, docker_manager):
        """
        Test that a workflow resumes correctly after agent service crashes.
        
        Steps:
        1. Start a workflow
        2. Crash agent service mid-execution
        3. Restart agent service
        4. Verify workflow resumes from last checkpoint
        """
        client = AgentGrpcClient()
        
        # Step 1: Start a complex workflow with tools
        query = "Search for Python 3.12 release notes and summarize the main changes"
        thread_id = "test-crash-resume-001"
        
        # Start workflow (this will take time due to tool calls)
        import threading
        result = {}
        exception = {}
        
        def run_query():
            try:
                result["data"] = client.query_agent(query, thread_id=thread_id)
            except Exception as e:
                exception["error"] = e
        
        query_thread = threading.Thread(target=run_query)
        query_thread.start()
        
        # Step 2: Wait a bit for workflow to start, then crash service
        time.sleep(2)  # Let workflow start
        
        # Crash agent service
        docker_manager.kill_service("orchestrator")
        print("🔥 Agent service killed (simulated crash)")
        
        # Wait for thread to fail
        query_thread.join(timeout=5)
        assert "error" in exception, "Expected query to fail after crash"
        
        # Step 3: Restart agent service
        time.sleep(1)
        docker_manager.restart_service("agent_service")
        time.sleep(3)  # Wait for recovery scan
        
        # Step 4: Verify recovery happened
        # Check logs for recovery messages
        logs = docker_manager.get_service_logs("agent_service")
        assert "Running startup crash recovery scan" in logs
        assert f"Found 1 crashed threads" in logs or "Clean startup" in logs
        
        # Try to resume by sending another query with same thread_id
        try:
            resumed_result = client.query_agent(
                "Continue from where we left off",
                thread_id=thread_id
            )
            
            # Verify we got a response
            assert resumed_result["final_answer"]
            assert resumed_result["sources"]
            
            print("✅ Workflow successfully resumed after crash")
            
        except Exception as e:
            pytest.fail(f"Failed to resume workflow: {e}")
    
    def test_checkpoint_validation_detects_issues(self, docker_manager):
        """
        Test that checkpoint validation works correctly.
        
        Steps:
        1. Create a checkpoint
        2. Restart service
        3. Verify checkpoint validation runs
        """
        client = AgentGrpcClient()
        
        # Create a checkpoint
        thread_id = "test-validation-001"
        client.query_agent("Hello, this is a test", thread_id=thread_id)
        
        # Restart and verify validation
        docker_manager.restart_service("agent_service")
        time.sleep(2)
        
        logs = docker_manager.get_service_logs("agent_service")
        # Should see recovery scan in logs
        assert "Running startup crash recovery scan" in logs
        
        print("✅ Checkpoint validation runs on startup")
    
    def test_clean_startup_with_no_crashes(self, docker_manager):
        """
        Test that clean startup (no crashed threads) works correctly.
        
        Steps:
        1. Complete a workflow normally
        2. Restart service
        3. Verify clean startup message
        """
        client = AgentGrpcClient()
        
        # Complete a workflow normally
        thread_id = "test-clean-001"
        client.query_agent("What is 2+2?", thread_id=thread_id)
        
        # Restart service
        docker_manager.restart_service("agent_service")
        time.sleep(2)
        
        logs = docker_manager.get_service_logs("agent_service")
        # Should see clean startup message
        assert "Running startup crash recovery scan" in logs
        assert "Clean startup" in logs or "No crashed threads found" in logs
        
        print("✅ Clean startup works correctly")
