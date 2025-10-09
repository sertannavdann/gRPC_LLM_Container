"""
Modern tool system for ADK-style function tools.

This package provides:
- LocalToolRegistry: Auto-schema extraction from docstrings
- ToolResult/ToolError: Standardized result types
- Function tool implementations
"""

from .registry import LocalToolRegistry
from .base import ToolResult, ToolError

__all__ = ['LocalToolRegistry', 'ToolResult', 'ToolError']
