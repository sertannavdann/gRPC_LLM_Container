"""
Base classes and types for the modern tool system.
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ToolResult:
    """
    Standard tool result format following ADK patterns.
    
    All tools should return dictionaries, but this class provides
    a convenient way to construct standardized results.
    """
    status: str  # "success" | "error"
    data: Any = None
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        return result


class ToolError(Exception):
    """Tool execution error"""
    
    def __init__(self, message: str, tool_name: str = None):
        self.message = message
        self.tool_name = tool_name
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to error dictionary"""
        result = {
            "status": "error",
            "message": self.message
        }
        if self.tool_name:
            result["tool"] = self.tool_name
        return result
