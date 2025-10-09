"""
Unit tests for LocalToolRegistry - Stage 1
"""

import pytest
from agent_service.tools.registry import LocalToolRegistry
from agent_service.tools.base import ToolResult, ToolError
from typing import Dict, Any


# Sample tools for testing
def simple_tool(name: str) -> Dict[str, Any]:
    """
    A simple test tool.
    
    Args:
        name (str): A person's name
    
    Returns:
        Dict with greeting: {"status": "success", "greeting": "Hello, name!"}
    """
    return {
        "status": "success",
        "greeting": f"Hello, {name}!"
    }


def math_tool(a: int, b: int) -> Dict[str, Any]:
    """
    Add two numbers.
    
    Args:
        a (int): First number
        b (int): Second number
    
    Returns:
        Dict with result: {"status": "success", "result": sum}
    """
    return {
        "status": "success",
        "result": a + b
    }


def failing_tool(message: str) -> Dict[str, Any]:
    """
    A tool that always fails.
    
    Args:
        message (str): Error message
    
    Returns:
        Never returns, always raises exception
    """
    raise ValueError(f"Intentional failure: {message}")


def optional_param_tool(required: str, optional: str = "default") -> Dict[str, Any]:
    """
    Tool with optional parameter.
    
    Args:
        required (str): Required parameter
        optional (str): Optional parameter with default
    
    Returns:
        Dict with values
    """
    return {
        "status": "success",
        "required": required,
        "optional": optional
    }


class TestLocalToolRegistry:
    """Test suite for LocalToolRegistry"""
    
    def test_initialization(self):
        """Test registry initializes correctly"""
        registry = LocalToolRegistry()
        
        assert isinstance(registry.tools, dict)
        assert isinstance(registry.schemas, dict)
        assert isinstance(registry.circuit_breakers, dict)
        assert registry.max_failures == 3
    
    def test_register_function(self):
        """Test function registration"""
        registry = LocalToolRegistry()
        registry.register_function(simple_tool)
        
        assert "simple_tool" in registry.tools
        assert "simple_tool" in registry.schemas
        assert "simple_tool" in registry.circuit_breakers
        assert registry.circuit_breakers["simple_tool"] == 0
    
    def test_schema_extraction(self):
        """Test schema extraction from docstring"""
        registry = LocalToolRegistry()
        registry.register_function(simple_tool)
        
        schema = registry.schemas["simple_tool"]
        
        assert schema["name"] == "simple_tool"
        assert "simple test tool" in schema["description"].lower()
        assert "name" in schema["parameters"]
        assert schema["parameters"]["name"]["type"] == "string"
        assert "name" in schema["required"]
    
    def test_schema_extraction_multiple_params(self):
        """Test schema extraction with multiple parameters"""
        registry = LocalToolRegistry()
        registry.register_function(math_tool)
        
        schema = registry.schemas["math_tool"]
        
        assert len(schema["parameters"]) == 2
        assert "a" in schema["parameters"]
        assert "b" in schema["parameters"]
        assert schema["parameters"]["a"]["type"] == "integer"
        assert schema["parameters"]["b"]["type"] == "integer"
        assert len(schema["required"]) == 2
    
    def test_schema_extraction_optional_params(self):
        """Test schema extraction with optional parameters"""
        registry = LocalToolRegistry()
        registry.register_function(optional_param_tool)
        
        schema = registry.schemas["optional_param_tool"]
        
        assert len(schema["parameters"]) == 2
        assert "required" in schema["required"]
        assert "optional" not in schema["required"]  # Has default value
    
    def test_call_tool_success(self):
        """Test successful tool execution"""
        registry = LocalToolRegistry()
        registry.register_function(simple_tool)
        
        result = registry.call_tool("simple_tool", name="Alice")
        
        assert result["status"] == "success"
        assert result["greeting"] == "Hello, Alice!"
    
    def test_call_tool_with_math(self):
        """Test tool execution with multiple parameters"""
        registry = LocalToolRegistry()
        registry.register_function(math_tool)
        
        result = registry.call_tool("math_tool", a=5, b=3)
        
        assert result["status"] == "success"
        assert result["result"] == 8
    
    def test_call_nonexistent_tool(self):
        """Test calling a tool that doesn't exist"""
        registry = LocalToolRegistry()
        
        result = registry.call_tool("nonexistent_tool")
        
        assert result["status"] == "error"
        assert "not found" in result["message"]
    
    def test_call_tool_failure(self):
        """Test tool execution failure"""
        registry = LocalToolRegistry()
        registry.register_function(failing_tool)
        
        result = registry.call_tool("failing_tool", message="test")
        
        assert result["status"] == "error"
        assert "Intentional failure" in result["message"]
        assert result["tool"] == "failing_tool"
        assert result["failures"] == 1
    
    def test_circuit_breaker_trips(self):
        """Test circuit breaker trips after max failures"""
        registry = LocalToolRegistry(max_failures=3)
        registry.register_function(failing_tool)
        
        # Fail 3 times
        for i in range(3):
            result = registry.call_tool("failing_tool", message="test")
            assert result["status"] == "error"
        
        # 4th call should be blocked by circuit breaker
        result = registry.call_tool("failing_tool", message="test")
        assert result["status"] == "error"
        assert "circuit breaker" in result["message"].lower()
    
    def test_circuit_breaker_resets_on_success(self):
        """Test circuit breaker resets after successful call"""
        registry = LocalToolRegistry()
        registry.register_function(simple_tool)
        
        # Manually set failure count
        registry.circuit_breakers["simple_tool"] = 2
        
        # Successful call should reset
        result = registry.call_tool("simple_tool", name="Bob")
        assert result["status"] == "success"
        assert registry.circuit_breakers["simple_tool"] == 0
    
    def test_reset_circuit_breaker(self):
        """Test manual circuit breaker reset"""
        registry = LocalToolRegistry()
        registry.register_function(failing_tool)
        
        # Trip the circuit breaker
        for _ in range(3):
            registry.call_tool("failing_tool", message="test")
        
        assert registry.circuit_breakers["failing_tool"] >= 3
        
        # Reset it
        success = registry.reset_circuit_breaker("failing_tool")
        assert success is True
        assert registry.circuit_breakers["failing_tool"] == 0
    
    def test_get_available_tools(self):
        """Test getting available (non-circuit-broken) tools"""
        registry = LocalToolRegistry(max_failures=2)
        registry.register_function(simple_tool)
        registry.register_function(failing_tool)
        
        # Initially both available
        available = registry.get_available_tools()
        assert len(available) == 2
        
        # Trip circuit breaker for failing_tool
        for _ in range(2):
            registry.call_tool("failing_tool", message="test")
        
        # Now only simple_tool available
        available = registry.get_available_tools()
        assert len(available) == 1
        assert "simple_tool" in available
        assert "failing_tool" not in available
    
    def test_get_tool_schema(self):
        """Test retrieving tool schema"""
        registry = LocalToolRegistry()
        registry.register_function(simple_tool)
        
        schema = registry.get_tool_schema("simple_tool")
        assert schema is not None
        assert schema["name"] == "simple_tool"
        
        schema = registry.get_tool_schema("nonexistent")
        assert schema is None


class TestToolResult:
    """Test suite for ToolResult dataclass"""
    
    def test_tool_result_creation(self):
        """Test creating ToolResult"""
        result = ToolResult(status="success", data={"key": "value"}, message="Done")
        
        assert result.status == "success"
        assert result.data == {"key": "value"}
        assert result.message == "Done"
    
    def test_tool_result_to_dict(self):
        """Test converting ToolResult to dict"""
        result = ToolResult(status="success", data=42, message="Calculated")
        dict_result = result.to_dict()
        
        assert dict_result["status"] == "success"
        assert dict_result["data"] == 42
        assert dict_result["message"] == "Calculated"
    
    def test_tool_result_minimal(self):
        """Test ToolResult with minimal fields"""
        result = ToolResult(status="error")
        dict_result = result.to_dict()
        
        assert dict_result["status"] == "error"
        assert "data" not in dict_result
        assert "message" not in dict_result


class TestToolError:
    """Test suite for ToolError exception"""
    
    def test_tool_error_creation(self):
        """Test creating ToolError"""
        error = ToolError("Something went wrong", tool_name="test_tool")
        
        assert error.message == "Something went wrong"
        assert error.tool_name == "test_tool"
    
    def test_tool_error_to_dict(self):
        """Test converting ToolError to dict"""
        error = ToolError("Failed", tool_name="my_tool")
        dict_error = error.to_dict()
        
        assert dict_error["status"] == "error"
        assert dict_error["message"] == "Failed"
        assert dict_error["tool"] == "my_tool"
    
    def test_tool_error_raise(self):
        """Test raising ToolError"""
        with pytest.raises(ToolError) as exc_info:
            raise ToolError("Test error", tool_name="failing_tool")
        
        assert "Test error" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
