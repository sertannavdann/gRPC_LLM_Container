"""
Unit tests for tools.registry.LocalToolRegistry.

Tests tool registration, schema extraction, circuit breaker integration,
and OpenAI function calling schema export.
"""

import pytest
from typing import Dict, Any
from unittest.mock import Mock, patch
import logging

from tools.registry import LocalToolRegistry
from tools.base import ToolError
from tools.circuit_breaker import CircuitBreaker


class TestLocalToolRegistry:
    """Test suite for LocalToolRegistry."""
    
    def test_registry_initialization(self, empty_tool_registry):
        """Test registry initializes with empty state."""
        registry = empty_tool_registry
        
        assert len(registry.tools) == 0
        assert len(registry.schemas) == 0
        assert len(registry.circuit_breakers) == 0
    
    def test_register_simple_function(self, empty_tool_registry):
        """Test registering a simple function with docstring."""
        registry = empty_tool_registry
        
        @registry.register
        def simple_tool(query: str) -> Dict[str, Any]:
            """
            Simple test tool.
            
            Args:
                query (str): Test query parameter
            
            Returns:
                Success result dictionary
            """
            return {"status": "success", "query": query}
        
        # Verify registration
        assert "simple_tool" in registry.tools
        assert "simple_tool" in registry.schemas
        assert "simple_tool" in registry.circuit_breakers
        # Circuit breaker starts in closed state
        assert registry.circuit_breakers["simple_tool"].is_available() is True
    
    def test_register_decorator_syntax(self, empty_tool_registry):
        """Test @registry.register decorator syntax."""
        registry = empty_tool_registry
        
        @registry.register
        def decorated_tool(param: str) -> Dict[str, Any]:
            """
            Tool registered via decorator.
            
            Args:
                param (str): Parameter
            
            Returns:
                Result dict
            """
            return {"status": "success"}
        
        assert "decorated_tool" in registry.tools
        
        # Should be callable after registration
        result = registry.call_tool("decorated_tool", param="test")
        assert result["status"] == "success"
    
    def test_schema_extraction_basic(self, empty_tool_registry):
        """Test basic schema extraction from function."""
        registry = empty_tool_registry
        
        @registry.register
        def schema_test(required_param: str, optional_param: int = 10) -> Dict[str, Any]:
            """
            Test schema extraction.
            
            Args:
                required_param (str): A required parameter
                optional_param (int): An optional parameter with default
            
            Returns:
                Result dictionary
            """
            return {"status": "success"}
        
        schema = registry.schemas["schema_test"]
        
        # Check basic structure
        assert schema["name"] == "schema_test"
        assert "description" in schema
        assert "parameters" in schema
        
        # Check parameters
        params = schema["parameters"]
        assert "required_param" in params["properties"]
        assert "optional_param" in params["properties"]
        
        # Check required vs optional
        assert "required_param" in params["required"]
        assert "optional_param" not in params["required"]
    
    def test_schema_extraction_type_hints(self, empty_tool_registry):
        """Test schema extraction respects type hints."""
        registry = empty_tool_registry
        
        @registry.register
        def typed_tool(
            string_param: str,
            int_param: int,
            float_param: float,
            bool_param: bool
        ) -> Dict[str, Any]:
            """
            Tool with multiple types.
            
            Args:
                string_param (str): String parameter
                int_param (int): Integer parameter
                float_param (float): Float parameter
                bool_param (bool): Boolean parameter
            
            Returns:
                Result dict
            """
            return {"status": "success"}
        
        schema = registry.schemas["typed_tool"]
        props = schema["parameters"]["properties"]
        
        assert props["string_param"]["type"] == "string"
        assert props["int_param"]["type"] == "integer"
        assert props["float_param"]["type"] == "number"
        assert props["bool_param"]["type"] == "boolean"
    
    def test_call_tool_success(self, empty_tool_registry):
        """Test successful tool execution."""
        registry = empty_tool_registry
        
        @registry.register
        def success_tool(value: str) -> Dict[str, Any]:
            """
            Always succeeds.
            
            Args:
                value (str): Input value
            
            Returns:
                Success result
            """
            return {"status": "success", "data": f"processed_{value}"}
        
        result = registry.call_tool("success_tool", value="test")
        
        assert result["status"] == "success"
        assert result["data"] == "processed_test"
        
        # Circuit breaker should still be available
        assert registry.circuit_breakers["success_tool"].is_available() is True
    
    def test_call_tool_not_found(self, empty_tool_registry):
        """Test calling non-existent tool."""
        registry = empty_tool_registry
        
        result = registry.call_tool("nonexistent_tool", param="value")
        
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()
    
    def test_call_tool_with_exception(self, empty_tool_registry):
        """Test tool that raises exception."""
        registry = empty_tool_registry
        
        @registry.register
        def failing_tool(param: str) -> Dict[str, Any]:
            """
            Tool that fails.
            
            Args:
                param (str): Parameter
            
            Returns:
                Never returns, always raises
            """
            raise ValueError("Simulated failure")
        
        result = registry.call_tool("failing_tool", param="test")
        
        assert result["status"] == "error"
        assert "Simulated failure" in result["error"]
        assert result["tool"] == "failing_tool"
        # Check circuit breaker metrics instead of failures field
        assert "circuit_breaker_metrics" in result
        
        # Circuit breaker should have recorded failure but still be available (1 < max 3)
        assert registry.circuit_breakers["failing_tool"].is_available() is True
    
    def test_circuit_breaker_opens_after_failures(self, empty_tool_registry):
        """Test circuit breaker opens after max failures."""
        registry = empty_tool_registry
        
        @registry.register
        def unreliable_tool(param: str) -> Dict[str, Any]:
            """
            Unreliable tool.
            
            Args:
                param (str): Parameter
            
            Returns:
                Never succeeds
            """
            raise RuntimeError("Always fails")
        
        # Call tool 3 times (default max_failures)
        for i in range(3):
            result = registry.call_tool("unreliable_tool", param=f"test{i}")
            assert result["status"] == "error"
        
        # 4th call should be blocked by circuit breaker
        result = registry.call_tool("unreliable_tool", param="test4")
        assert result["status"] == "error"
        assert "circuit breaker" in result["error"].lower() or "open" in result["error"].lower()
    
    def test_circuit_breaker_resets_on_success(self, empty_tool_registry):
        """Test circuit breaker resets failure count on success."""
        registry = empty_tool_registry
        
        call_count = [0]
        
        @registry.register
        def flaky_tool(param: str) -> Dict[str, Any]:
            """
            Flaky tool.
            
            Args:
                param (str): Parameter
            
            Returns:
                Success or error based on call count
            """
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Temporary failure")
            return {"status": "success", "data": "recovered"}
        
        # First 2 calls fail
        registry.call_tool("flaky_tool", param="test1")
        registry.call_tool("flaky_tool", param="test2")
        # Circuit breaker should have failures recorded
        assert registry.circuit_breakers["flaky_tool"].is_available() is True  # Not open yet
        
        # 3rd call succeeds
        result = registry.call_tool("flaky_tool", param="test3")
        assert result["status"] == "success"
        
        # Circuit breaker should reset after success
        assert registry.circuit_breakers["flaky_tool"].is_available() is True
    
    def test_get_available_tools(self, empty_tool_registry):
        """Test get_available_tools filters circuit-broken tools."""
        registry = empty_tool_registry
        
        @registry.register
        def good_tool(param: str) -> Dict[str, Any]:
            """Good tool. Args: param (str): Parameter. Returns: Success."""
            return {"status": "success"}
        
        @registry.register
        def bad_tool(param: str) -> Dict[str, Any]:
            """Bad tool. Args: param (str): Parameter. Returns: Fails."""
            raise ValueError("Always fails")
        
        # Initially both available
        available = registry.get_available_tools()
        assert "good_tool" in available
        assert "bad_tool" in available
        
        # Break bad_tool circuit
        for _ in range(3):
            registry.call_tool("bad_tool", param="test")
        
        # Only good_tool should be available
        available = registry.get_available_tools()
        assert "good_tool" in available
        assert "bad_tool" not in available
    
    def test_reset_circuit_breaker(self, empty_tool_registry):
        """Test manual circuit breaker reset."""
        registry = empty_tool_registry
        
        @registry.register
        def tool_to_reset(param: str) -> Dict[str, Any]:
            """Tool. Args: param (str): Parameter. Returns: Fails."""
            raise ValueError("Failure")
        
        # Trip circuit breaker
        for _ in range(3):
            registry.call_tool("tool_to_reset", param="test")
        
        assert "tool_to_reset" not in registry.get_available_tools()
        
        # Reset manually
        success = registry.reset_circuit_breaker("tool_to_reset")
        assert success is True
        assert "tool_to_reset" in registry.get_available_tools()
    
    def test_to_openai_tools(self, empty_tool_registry):
        """Test exporting tools as OpenAI function calling schema."""
        registry = empty_tool_registry
        
        @registry.register
        def example_tool(query: str, limit: int = 10) -> Dict[str, Any]:
            """
            Example tool for export.
            
            Args:
                query (str): Search query
                limit (int): Result limit
            
            Returns:
                Search results
            """
            return {"status": "success"}
        
        openai_schema = registry.to_openai_tools()
        
        assert len(openai_schema) == 1
        tool_spec = openai_schema[0]
        
        assert tool_spec["type"] == "function"
        assert tool_spec["function"]["name"] == "example_tool"
        assert "Example tool for export" in tool_spec["function"]["description"]
        assert "query" in tool_spec["function"]["parameters"]["properties"]
        assert "limit" in tool_spec["function"]["parameters"]["properties"]
        assert "query" in tool_spec["function"]["parameters"]["required"]
    
    def test_register_gRPC_tool(self, empty_tool_registry):
        """Test backward compatibility with gRPC tool registration."""
        registry = empty_tool_registry
        
        # Mock gRPC client method
        mock_method = Mock(return_value={"status": "success", "data": "grpc result"})
        
        # Register gRPC tool with the correct signature
        registry.register_gRPC_tool(
            name="grpc_search",
            client_method=mock_method,
            description="gRPC web search tool"
        )
        
        assert "grpc_search" in registry.tools
        
        # Call tool
        result = registry.call_tool("grpc_search", query="test")
        
        # Should delegate to gRPC client method
        mock_method.assert_called_once_with(query="test")
        assert result["status"] == "success"
    
    def test_tool_with_complex_return(self, empty_tool_registry):
        """Test tool that returns non-standard format gets wrapped."""
        registry = empty_tool_registry
        
        @registry.register
        def legacy_tool(param: str) -> list:
            """
            Legacy tool with non-dict return.
            
            Args:
                param (str): Parameter
            
            Returns:
                List of results (non-standard)
            """
            return ["result1", "result2"]
        
        result = registry.call_tool("legacy_tool", param="test")
        
        # Should be wrapped in standard format
        assert result["status"] == "success"
        assert "data" in result
        assert result["data"] == ["result1", "result2"]
    
    def test_tool_missing_docstring(self, empty_tool_registry):
        """Test registering tool without docstring still works (creates empty description)."""
        registry = empty_tool_registry
        
        # The registry allows registration without docstring (uses empty description)
        @registry.register
        def no_docstring(param: str) -> Dict[str, Any]:
            return {"status": "success"}
        
        # Should register successfully
        assert "no_docstring" in registry.tools
        assert "no_docstring" in registry.schemas
        # Description will be empty or "No description"
        assert isinstance(registry.schemas["no_docstring"]["description"], str)
    
    def test_concurrent_tool_calls(self, empty_tool_registry):
        """Test registry handles concurrent tool execution."""
        import threading
        
        registry = empty_tool_registry
        results = []
        
        @registry.register
        def concurrent_tool(thread_id: int) -> Dict[str, Any]:
            """
            Thread-safe tool.
            
            Args:
                thread_id (int): Thread identifier
            
            Returns:
                Result with thread ID
            """
            import time
            time.sleep(0.01)  # Simulate work
            return {"status": "success", "thread_id": thread_id}
        
        def call_tool(tid):
            result = registry.call_tool("concurrent_tool", thread_id=tid)
            results.append(result)
        
        # Launch 5 concurrent calls
        threads = [threading.Thread(target=call_tool, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should succeed
        assert len(results) == 5
        assert all(r["status"] == "success" for r in results)
        
        # Each should have unique thread_id
        thread_ids = [r["thread_id"] for r in results]
        assert len(set(thread_ids)) == 5


class TestRegistryLogging:
    """Test registry logging behavior."""
    
    def test_registration_logs(self, empty_tool_registry, caplog):
        """Test tool registration creates log entries."""
        caplog.set_level(logging.INFO)
        registry = empty_tool_registry
        
        @registry.register
        def logged_tool(param: str) -> Dict[str, Any]:
            """Logged tool. Args: param (str): P. Returns: R."""
            return {"status": "success"}
        
        # Check for actual log message format
        assert "Registered function tool 'logged_tool'" in caplog.text or "logged_tool" in caplog.text
    
    def test_tool_execution_logs(self, empty_tool_registry, caplog):
        """Test tool execution creates debug logs."""
        caplog.set_level(logging.DEBUG)
        registry = empty_tool_registry
        
        @registry.register
        def exec_logged_tool(param: str) -> Dict[str, Any]:
            """Tool. Args: param (str): P. Returns: R."""
            return {"status": "success"}
        
        registry.call_tool("exec_logged_tool", param="test_value")
        
        assert "Executing tool 'exec_logged_tool'" in caplog.text
        assert "test_value" in caplog.text
    
    def test_failure_logs(self, empty_tool_registry, caplog):
        """Test tool failures create error logs."""
        caplog.set_level(logging.ERROR)
        registry = empty_tool_registry
        
        @registry.register
        def failing_logged_tool(param: str) -> Dict[str, Any]:
            """Tool. Args: param (str): P. Returns: R."""
            raise ValueError("Test error")
        
        registry.call_tool("failing_logged_tool", param="test")
        
        # Check for actual error log format
        assert "Unexpected error in 'failing_logged_tool'" in caplog.text or "failing_logged_tool" in caplog.text
        assert "Test error" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
