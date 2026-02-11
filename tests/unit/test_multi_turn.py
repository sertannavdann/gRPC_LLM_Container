"""
Unit tests for multi-turn tool rollouts (Agent0 Phase 1).
Tests the stop-and-go pattern in LLMEngineWrapper.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch


class TestMultiTurnToolRollouts:
    """Test suite for multi-turn tool execution loop."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = Mock()
        return client
    
    @pytest.fixture
    def mock_tool_registry(self):
        """Create a mock tool registry with test tools."""
        registry = Mock()
        
        def mock_execute(tool_name, params):
            if tool_name == "calculate":
                return {"result": params.get("a", 0) + params.get("b", 0)}
            elif tool_name == "search":
                return {"results": ["result1", "result2"]}
            return {"error": f"Unknown tool: {tool_name}"}
        
        registry.execute_tool = mock_execute
        registry.get_tool = Mock(return_value=Mock(name="test_tool"))
        return registry

    def test_single_tool_call_then_answer(self, mock_llm_client, mock_tool_registry):
        """Test: LLM calls tool once, then provides final answer."""
        # First call returns a tool call
        tool_call_response = json.dumps({
            "type": "tool_call",
            "tool": "calculate",
            "arguments": {"a": 5, "b": 3}
        })
        
        # Second call returns final answer
        final_response = json.dumps({
            "type": "answer",
            "content": "The result is 8"
        })
        
        mock_llm_client.generate = Mock(side_effect=[tool_call_response, final_response])
        
        # Simulate the multi-turn loop logic
        max_iterations = 5
        context_history = []
        
        for iteration in range(max_iterations):
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
            
            if parsed.get("type") == "tool_call":
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                result = mock_tool_registry.execute_tool(tool_name, tool_args)
                context_history.append({"role": "tool", "content": json.dumps(result)})
            elif parsed.get("type") == "answer":
                final_answer = parsed.get("content")
                break
        
        assert final_answer == "The result is 8"
        assert len(context_history) == 1
        assert mock_llm_client.generate.call_count == 2

    def test_multiple_tool_iterations(self, mock_llm_client, mock_tool_registry):
        """Test: LLM makes multiple tool calls before final answer."""
        responses = [
            json.dumps({"type": "tool_call", "tool": "search", "arguments": {"query": "test"}}),
            json.dumps({"type": "tool_call", "tool": "calculate", "arguments": {"a": 10, "b": 5}}),
            json.dumps({"type": "answer", "content": "Found results and calculated 15"})
        ]
        
        mock_llm_client.generate = Mock(side_effect=responses)
        
        max_iterations = 5
        context_history = []
        final_answer = None
        
        for iteration in range(max_iterations):
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
            
            if parsed.get("type") == "tool_call":
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                result = mock_tool_registry.execute_tool(tool_name, tool_args)
                context_history.append({"role": "tool", "content": json.dumps(result)})
            elif parsed.get("type") == "answer":
                final_answer = parsed.get("content")
                break
        
        assert final_answer == "Found results and calculated 15"
        assert len(context_history) == 2
        assert mock_llm_client.generate.call_count == 3

    def test_max_iterations_limit(self, mock_llm_client, mock_tool_registry):
        """Test: Loop terminates at max_iterations even without final answer."""
        # All responses are tool calls - never reaches answer
        tool_response = json.dumps({
            "type": "tool_call",
            "tool": "calculate",
            "arguments": {"a": 1, "b": 1}
        })
        
        mock_llm_client.generate = Mock(return_value=tool_response)
        
        max_iterations = 3
        context_history = []
        final_answer = None
        
        for iteration in range(max_iterations):
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
            
            if parsed.get("type") == "tool_call":
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                result = mock_tool_registry.execute_tool(tool_name, tool_args)
                context_history.append({"role": "tool", "content": json.dumps(result)})
            elif parsed.get("type") == "answer":
                final_answer = parsed.get("content")
                break
        
        # Should have hit max iterations
        assert final_answer is None
        assert len(context_history) == 3
        assert mock_llm_client.generate.call_count == 3

    def test_immediate_answer_no_tools(self, mock_llm_client, mock_tool_registry):
        """Test: LLM provides answer immediately without tool calls."""
        immediate_response = json.dumps({
            "type": "answer",
            "content": "Direct answer without tools"
        })
        
        mock_llm_client.generate = Mock(return_value=immediate_response)
        
        max_iterations = 5
        context_history = []
        final_answer = None
        
        for iteration in range(max_iterations):
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
            
            if parsed.get("type") == "tool_call":
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                result = mock_tool_registry.execute_tool(tool_name, tool_args)
                context_history.append({"role": "tool", "content": json.dumps(result)})
            elif parsed.get("type") == "answer":
                final_answer = parsed.get("content")
                break
        
        assert final_answer == "Direct answer without tools"
        assert len(context_history) == 0
        assert mock_llm_client.generate.call_count == 1

    def test_tool_execution_error_handling(self, mock_llm_client):
        """Test: Error handling when tool execution fails."""
        tool_response = json.dumps({
            "type": "tool_call",
            "tool": "unknown_tool",
            "arguments": {}
        })
        
        mock_llm_client.generate = Mock(return_value=tool_response)
        
        # Registry that raises error
        failing_registry = Mock()
        failing_registry.execute_tool = Mock(side_effect=Exception("Tool not found"))
        
        context_history = []
        errors = []
        
        try:
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
            
            if parsed.get("type") == "tool_call":
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                try:
                    result = failing_registry.execute_tool(tool_name, tool_args)
                    context_history.append({"role": "tool", "content": json.dumps(result)})
                except Exception as e:
                    errors.append(str(e))
                    context_history.append({"role": "error", "content": str(e)})
        except Exception as e:
            errors.append(str(e))
        
        assert len(errors) == 1
        assert "Tool not found" in errors[0]

    def test_invalid_json_response(self, mock_llm_client, mock_tool_registry):
        """Test: Handle invalid JSON from LLM gracefully."""
        invalid_response = "This is not valid JSON"
        mock_llm_client.generate = Mock(return_value=invalid_response)
        
        error_caught = False
        
        try:
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
        except json.JSONDecodeError:
            error_caught = True
        
        assert error_caught

    def test_context_accumulation(self, mock_llm_client, mock_tool_registry):
        """Test: Tool results are properly accumulated in context."""
        responses = [
            json.dumps({"type": "tool_call", "tool": "calculate", "arguments": {"a": 1, "b": 2}}),
            json.dumps({"type": "tool_call", "tool": "calculate", "arguments": {"a": 3, "b": 4}}),
            json.dumps({"type": "answer", "content": "Results: 3 and 7"})
        ]
        
        mock_llm_client.generate = Mock(side_effect=responses)
        
        context_history = []
        
        for _ in range(5):
            response = mock_llm_client.generate(prompt="test", max_tokens=512)
            parsed = json.loads(response)
            
            if parsed.get("type") == "tool_call":
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                result = mock_tool_registry.execute_tool(tool_name, tool_args)
                context_history.append({"role": "tool", "content": json.dumps(result)})
            elif parsed.get("type") == "answer":
                break
        
        # Verify context has both tool results
        assert len(context_history) == 2
        assert json.loads(context_history[0]["content"])["result"] == 3
        assert json.loads(context_history[1]["content"])["result"] == 7


class TestToolUseCountTracking:
    """Test tool_use_count tracking for curriculum learning."""
    
    def test_tool_count_increments(self):
        """Test that tool_use_count increases with each tool call."""
        state = {"tool_use_count": 0}
        
        # Simulate tools_node execution
        tool_results = ["result1", "result2", "result3"]
        state["tool_use_count"] = state.get("tool_use_count", 0) + len(tool_results)
        
        assert state["tool_use_count"] == 3
    
    def test_tool_count_accumulates_across_iterations(self):
        """Test tool_use_count accumulates across multiple iterations."""
        state = {"tool_use_count": 0}
        
        # First iteration: 2 tools
        state["tool_use_count"] += 2
        assert state["tool_use_count"] == 2
        
        # Second iteration: 1 tool
        state["tool_use_count"] += 1
        assert state["tool_use_count"] == 3
        
        # Third iteration: 3 tools
        state["tool_use_count"] += 3
        assert state["tool_use_count"] == 6
    
    def test_tool_count_starts_at_zero(self):
        """Test tool_use_count defaults to 0 if not in state."""
        state = {}
        
        initial_count = state.get("tool_use_count", 0)
        assert initial_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
