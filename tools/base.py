"""
Base classes and protocols for tool system.

Defines the interface for all tools following Google ADK best practices:
- Tools are callables that return Dict[str, Any]
- All results have a "status" key ("success" or "error")
- Type hints for all parameters
- Structured docstrings with Args and Returns sections
"""

from typing import Dict, Any, Protocol, runtime_checkable, Optional
from dataclasses import dataclass


@runtime_checkable
class ToolCallable(Protocol):
    """
    Protocol for tool functions following ADK patterns.
    
    All tools must:
    - Accept kwargs with type hints
    - Return Dict[str, Any] with "status" key
    - Have docstring with Args/Returns sections
    """
    
    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute tool with provided arguments."""
        ...


@dataclass
class ToolResult:
    """
    Standardized tool result format following ADK patterns.
    
    All tools should return dictionaries, but this class provides
    a convenient way to construct standardized results.
    
    Attributes:
        status: "success" or "error"
        data: Tool-specific return data (optional)
        message: Human-readable message (optional)
    
    Example:
        >>> result = ToolResult(status="success", data={"count": 5})
        >>> return result.to_dict()
    """
    
    status: str  # "success" | "error"
    data: Any = None
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format expected by LLMs.
        
        Returns:
            dict: Standardized result with status key
        """
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        return result


class ToolError(Exception):
    """
    Tool execution error with standardized formatting.
    
    Provides automatic conversion to error dictionary format
    for consistent error handling across the agent system.
    
    Attributes:
        message: Error description
        tool_name: Name of tool that failed (optional)
    
    Example:
        >>> raise ToolError("API request failed", tool_name="web_search")
    """
    
    def __init__(self, message: str, tool_name: Optional[str] = None):
        self.message = message
        self.tool_name = tool_name
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to error dictionary.
        
        Returns:
            dict: Error result with status="error"
        """
        result = {
            "status": "error",
            "error": self.message
        }
        if self.tool_name:
            result["tool"] = self.tool_name
        return result


class BaseTool:
    """
    Base class for tools requiring stateful initialization.
    
    Most tools should be simple functions decorated with @tool.
    Use this class only when you need:
    - API clients with authentication
    - Connection pooling
    - Shared configuration across calls
    
    Example:
        >>> class WebSearchTool(BaseTool):
        ...     def __init__(self, api_key: str):
        ...         self.api_key = api_key
        ...     
        ...     def execute(self, query: str) -> Dict[str, Any]:
        ...         # Use self.api_key for API calls
        ...         return {"status": "success", "results": [...]}
    """
    
    name: str = ""
    description: str = ""
    
    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute tool with provided arguments.
        
        Must be overridden by subclasses.
        
        Args:
            **kwargs: Tool-specific arguments
        
        Returns:
            dict: Result with "status" key
        
        Raises:
            NotImplementedError: If not overridden by subclass
        """
        raise NotImplementedError(f"{self.__class__.__name__}.execute() not implemented")
    
    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        """Make tool instances callable."""
        return self.execute(**kwargs)
