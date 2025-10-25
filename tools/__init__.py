"""
Modern tool system following Google ADK patterns.

Provides decorator-based tool registration, automatic schema extraction,
circuit breakers, and support for multiple tool frameworks (ADK, LangChain,
CrewAI, MCP).

Example:
    >>> from tools import LocalToolRegistry, tool
    >>> 
    >>> registry = LocalToolRegistry()
    >>> 
    >>> @registry.register
    >>> def my_tool(param: str) -> dict:
    ...     '''My tool description.
    ...     
    ...     Args:
    ...         param (str): Parameter description
    ...     
    ...     Returns:
    ...         Dict with status key
    ...     '''
    ...     return {"status": "success", "data": param.upper()}
    >>> 
    >>> result = registry.call_tool("my_tool", param="hello")
    >>> print(result)  # {"status": "success", "data": "HELLO"}
"""

from .base import BaseTool, ToolResult, ToolError, ToolCallable
from .registry import LocalToolRegistry
from .circuit_breaker import CircuitBreaker
from .decorators import (
    tool,
    mcp_tool,
    langchain_tool,
    requires_api_key,
    with_timeout
)

__all__ = [
    # Base classes
    "BaseTool",
    "ToolResult",
    "ToolError",
    "ToolCallable",
    
    # Registry
    "LocalToolRegistry",
    
    # Circuit breaker
    "CircuitBreaker",
    
    # Decorators
    "tool",
    "mcp_tool",
    "langchain_tool",
    "requires_api_key",
    "with_timeout",
]

__version__ = "1.0.0"
