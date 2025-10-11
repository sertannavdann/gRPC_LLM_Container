"""
Modern tool system following Google ADK patterns.

Provides decorator-based tool registration, automatic schema extraction,
circuit breakers, and support for multiple tool frameworks (ADK, LangChain,
CrewAI, MCP).
"""

from .base import BaseTool, ToolResult, ToolError
from .registry import LocalToolRegistry, tool
from .circuit_breaker import CircuitBreaker
from .decorators import mcp_tool, langchain_tool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolError",
    "LocalToolRegistry",
    "tool",
    "CircuitBreaker",
    "mcp_tool",
    "langchain_tool",
]
