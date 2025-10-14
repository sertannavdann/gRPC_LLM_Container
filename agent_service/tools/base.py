"""
Base classes and protocols for the tool system.

.. deprecated:: Phase 1B
   This module is DEPRECATED. Use the canonical implementation at the root level:
   ``tools/base.py`` instead. This duplicate will be removed in Phase 2.
   
   Migration:
       OLD: from agent_service.tools.base import BaseTool, ToolResult
       NEW: from tools.base import BaseTool, ToolResult

Defines the contract for tool implementations and standardized
result/error formats.
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
