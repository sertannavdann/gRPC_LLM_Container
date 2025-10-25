"""
End-to-end integration tests for agent_service.

Tests the complete gRPC stack with real Docker services:
- agent_service (orchestrator)
- llm_service (inference)
- chroma_service (embeddings)

Requires:
    - Docker Compose stack running
    - All services healthy and accessible
"""

import pytest
import logging
import time
from pathlib import Path

from tests.integration.grpc_test_client import AgentTestClient
from tests.integration.docker_manager import DockerComposeManager

logger = logging.getLogger(__name__)


# Fixtures
@pytest.fixture(scope="session")
def docker_manager():
    """
    Docker Compose manager for test session.
    
    Assumes services are already running (started via 'make up').
    Does NOT start or stop services - just provides management interface.
    """
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.yaml"
    
    try:
        manager = DockerComposeManager(str(compose_file))
    except FileNotFoundError as e:
        pytest.skip(f"Docker not available: {e}")
    
    logger.info("=" * 60)
    logger.info("Using existing Docker stack for integration tests...")
    logger.info("=" * 60)
    
    # Verify services are running
    if not manager.wait_for_service("agent_service", 50054, timeout=10):
        pytest.skip("agent_service not available on port 50054. Please start with 'make up'.")
    
    if not manager.wait_for_service("llm_service", 50051, timeout=10):
        pytest.skip("llm_service not available on port 50051. Please start with 'make up'.")
    
    if not manager.wait_for_service("chroma_service", 50052, timeout=10):
        pytest.skip("chroma_service not available on port 50052. Please start with 'make up'.")
    
    logger.info("✓ All services are reachable")
    
    yield manager
    
    logger.info("✓ Test session complete (services left running)")


@pytest.fixture(scope="function")
def agent_client(docker_manager):
    """
    Agent service test client for each test.
    
    Creates fresh client per test, closes after test.
    """
    with AgentTestClient(host="localhost", port=50054, timeout=30) as client:
        yield client


# Tests
class TestBasicFunctionality:
    """Test basic agent service operations."""
    
    def test_simple_greeting(self, agent_client):
        """Test simple greeting query."""
        response = agent_client.query("Hello, how are you?")
        
        assert response is not None
        assert len(response.final_answer) > 0
        assert response.final_answer.lower() not in ["", "null", "none"]
        
        logger.info(f"✓ Greeting response: {response.final_answer[:100]}...")
    
    def test_factual_question(self, agent_client):
        """Test factual knowledge query."""
        response = agent_client.query("What is 2 + 2?")
        
        assert response is not None
        assert len(response.final_answer) > 0
        
        # Check if "4" appears in response
        assert "4" in response.final_answer
        
        logger.info(f"✓ Math response: {response.final_answer[:100]}...")
    
    def test_debug_mode(self, agent_client):
        """Test debug mode with execution details."""
        response = agent_client.query("Tell me a fact", debug_mode=True)
        
        assert response is not None
        assert len(response.final_answer) > 0
        
        # Debug mode should populate additional fields
        # (Note: Depends on agent_service implementation)
        logger.info(f"✓ Debug response: {response.final_answer[:100]}...")
        logger.info(f"  Context: {response.context_used[:50]}...")
        logger.info(f"  Sources: {response.sources[:50]}...")


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_empty_query(self, agent_client):
        """Test handling of empty query."""
        try:
            response = agent_client.query("")
            
            # Service should handle gracefully
            assert response is not None
            logger.info(f"✓ Empty query handled: {response.final_answer[:50]}...")
        
        except Exception as e:
            # Or raise appropriate error
            logger.info(f"✓ Empty query rejected: {e}")
    
    def test_very_long_query(self, agent_client):
        """Test handling of very long query."""
        long_query = "Tell me about " + ("AI " * 500)  # ~1500 words
        
        try:
            response = agent_client.query(long_query)
            
            assert response is not None
            assert len(response.final_answer) > 0
            logger.info(f"✓ Long query handled: {response.final_answer[:50]}...")
        
        except Exception as e:
            # May hit context window limit
            logger.info(f"✓ Long query rejected appropriately: {e}")
    
    def test_special_characters(self, agent_client):
        """Test handling of special characters."""
        special_query = "What is 10% of $100? 🤔 <test> & 'quotes' \"double\""
        
        response = agent_client.query(special_query)
        
        assert response is not None
        assert len(response.final_answer) > 0
        logger.info(f"✓ Special chars handled: {response.final_answer[:50]}...")


class TestConcurrency:
    """Test concurrent request handling."""
    
    def test_sequential_queries(self, agent_client):
        """Test multiple sequential queries."""
        queries = [
            "What is 1+1?",
            "What is the capital of France?",
            "Tell me a fun fact",
        ]
        
        responses = []
        for query in queries:
            response = agent_client.query(query)
            assert response is not None
            assert len(response.final_answer) > 0
            responses.append(response)
            
            # Small delay between queries
            time.sleep(0.5)
        
        logger.info(f"✓ Sequential queries: {len(responses)} successful")
    
    @pytest.mark.xfail(reason="Known issue: concurrent requests fail due to thread safety issues in agent_service")
    def test_rapid_fire_queries(self, agent_client):
        """Test rapid concurrent queries (stress test)."""
        import concurrent.futures
        
        def send_query(i):
            try:
                response = agent_client.query(f"What is {i} + {i}?")
                return (i, response is not None, response.final_answer if response else None)
            except Exception as e:
                return (i, False, str(e))
        
        # Send 10 queries rapidly
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(send_query, range(10)))
        
        # Check results
        success_count = sum(1 for _, success, _ in results if success)
        
        logger.info(f"✓ Rapid fire: {success_count}/10 successful")
        
        # Allow some failures under heavy load
        assert success_count >= 7, f"Too many failures: {10 - success_count}/10"


class TestMetrics:
    """Test metrics endpoint."""
    
    @pytest.mark.xfail(reason="Known issue: metrics query fails with INTERNAL error after concurrent tests")
    def test_get_metrics(self, agent_client):
        """Test metrics retrieval."""
        # Send a query first
        agent_client.query("Test query for metrics")
        
        # Get metrics
        metrics = agent_client.get_metrics()
        
        assert metrics is not None
        assert metrics.llm_calls >= 0
        assert metrics.avg_response_time >= 0
        
        logger.info(f"✓ Metrics: llm_calls={metrics.llm_calls}, "
                   f"avg_time={metrics.avg_response_time:.2f}s")
        logger.info(f"  Tool usage: {metrics.tool_usage[:100]}...")


class TestServiceHealth:
    """Test service health and recovery."""
    
    @pytest.mark.xfail(reason="Known issue: health check query fails after service instability")
    def test_health_check(self, agent_client):
        """Test basic health check."""
        is_healthy = agent_client.health_check()
        
        assert is_healthy is True
        logger.info("✓ Health check passed")
    
    @pytest.mark.xfail(reason="Known issue: service recovery test unreliable due to Docker restart timing")
    def test_service_recovery(self, agent_client, docker_manager):
        """Test service recovery after restart."""
        # Send initial query
        response1 = agent_client.query("First query")
        assert response1 is not None
        
        # Restart agent service
        logger.info("Restarting agent_service...")
        docker_manager.restart_service("agent_service")
        
        # Wait for restart
        time.sleep(5)
        if not docker_manager.wait_for_service("agent_service", 50054, timeout=30):
            pytest.fail("agent_service failed to restart")
        
        # Send query after restart
        time.sleep(2)  # Additional settling time
        response2 = agent_client.query("Second query after restart")
        assert response2 is not None
        
        logger.info("✓ Service recovered after restart")


# Markers for selective test execution
pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
]
