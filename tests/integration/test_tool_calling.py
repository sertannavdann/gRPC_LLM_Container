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
        """Test that math expressions trigger math_solver tool and return answer"""
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
        
        # The answer MUST contain 345 (15 * 23 = 345)
        # If tool was used but answer not in response, this is a FORMATTING BUG
        tool_used = "math_solver" in response.sources.lower()
        has_answer = "345" in response.final_answer or "three hundred" in response.final_answer.lower()
        
        assert has_answer, (
            f"FORMATTING BUG: Answer '345' not found in final_answer. "
            f"Tool was called: {tool_used}. "
            f"The orchestrator must format tool results into the final answer. "
            f"Got: '{response.final_answer}' | Sources: {response.sources}"
        )
        
        logger.info("✓ Math solver tool calling works!")
    
    def test_tool_calling_debug_info(self, client):
        """Test with debug mode - answer must appear in response"""
        logger.info("=" * 60)
        logger.info("Testing Tool Calling: Debug Mode")
        logger.info("=" * 60)
        
        # Query with debug mode enabled (note: debug_mode, not debug)
        response = client.query(
            "What is 100 divided by 4?",
            debug_mode=True
        )
        
        logger.info(f"Query: What is 100 divided by 4?")
        logger.info(f"Response: {response.final_answer}")
        logger.info(f"Context used: {response.context_used}")
        logger.info(f"Sources: {response.sources}")
        
        assert response is not None
        assert len(response.final_answer) > 0
        
        # The answer MUST contain 25 (100 / 4 = 25)
        # If tool was used but answer not in response, this is a FORMATTING BUG
        tool_used = "math_solver" in response.sources.lower() or "tool" in response.sources.lower()
        has_answer = "25" in response.final_answer or "twenty" in response.final_answer.lower()
        
        assert has_answer, (
            f"FORMATTING BUG: Answer '25' not found in final_answer. "
            f"Tool was called: {tool_used}. "
            f"The orchestrator must format tool results into the final answer. "
            f"Got: '{response.final_answer}' | Sources: {response.sources}"
        )
        
        logger.info("✓ Debug mode shows tool execution with correct answer!")
    
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
        
        # Response should not be an error message
        response_lower = response.final_answer.lower()
        assert "error" not in response_lower or "connection" not in response_lower
        
        logger.info("✓ Simple queries work!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
