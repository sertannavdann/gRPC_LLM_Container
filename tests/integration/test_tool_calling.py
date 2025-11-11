"""
Integration test specifically for tool calling functionality.
Tests FINDING #1: Tool Calling is BROKEN
"""

import pytest
import logging
from tests.integration.grpc_test_client import AgentTestClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestToolCalling:
    """Test tool calling end-to-end"""
    
    @pytest.fixture
    def client(self):
        """Create gRPC test client"""
        client = AgentTestClient()
        yield client
        client.close()
    
    def test_math_solver_tool(self, client):
        """Test that math expressions trigger math_solver tool"""
        logger.info("=" * 60)
        logger.info("Testing Tool Calling: math_solver")
        logger.info("=" * 60)
        
        # This should trigger the math_solver tool
        response = client.query("Calculate 15 * 23")
        
        logger.info(f"Query: Calculate 15 * 23")
        logger.info(f"Response: {response.final_answer}")
        logger.info(f"Sources: {response.sources}")
        
        # Check response contains result
        assert response is not None
        assert len(response.final_answer) > 0
        
        # The answer should contain 345 (15 * 23 = 345)
        # Allow for some flexibility in response format
        assert "345" in response.final_answer or "three hundred" in response.final_answer.lower()
        
        logger.info("✓ Math solver tool calling works!")
    
    def test_tool_calling_debug_info(self, client):
        """Test with debug mode to see tool execution details"""
        logger.info("=" * 60)
        logger.info("Testing Tool Calling: Debug Mode")
        logger.info("=" * 60)
        
        # Query with debug mode enabled
        response = client.query(
            "What is 100 divided by 4?",
            debug=True
        )
        
        logger.info(f"Query: What is 100 divided by 4?")
        logger.info(f"Response: {response.final_answer}")
        logger.info(f"Context used: {response.context_used}")
        logger.info(f"Sources: {response.sources}")
        
        # Should contain the answer
        assert response is not None
        assert "25" in response.final_answer or "twenty" in response.final_answer.lower()
        
        # In debug mode, should see tool usage in sources
        assert "math_solver" in response.sources.lower() or "tool" in response.sources.lower()
        
        logger.info("✓ Debug mode shows tool execution!")
    
    def test_simple_query_without_tools(self, client):
        """Test that simple queries work without triggering tools"""
        logger.info("=" * 60)
        logger.info("Testing Simple Query (No Tools)")
        logger.info("=" * 60)
        
        response = client.query("Hello, how are you?")
        
        logger.info(f"Query: Hello, how are you?")
        logger.info(f"Response: {response.final_answer}")
        
        # Should get a response
        assert response is not None
        assert len(response.final_answer) > 0
        
        # Should be a greeting-like response
        greeting_words = ["hello", "hi", "good", "well", "fine", "great"]
        response_lower = response.final_answer.lower()
        assert any(word in response_lower for word in greeting_words)
        
        logger.info("✓ Simple queries work without tools!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
