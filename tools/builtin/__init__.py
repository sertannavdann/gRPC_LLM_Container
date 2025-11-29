"""
Built-in tools following Google ADK patterns.

These tools provide essential functionality out of the box:
- Web search via Serper API
- Math evaluation with safe execution
- Web page content extraction
- Code execution in sandboxed environment

All tools follow the ADK standardized return format:
    {"status": "success|error", "data": ..., "error": ...}
"""

from .web_search import web_search
from .math_solver import math_solver
from .web_loader import load_web_page
from .code_executor import execute_code, set_sandbox_client

__all__ = [
    "web_search",
    "math_solver",
    "load_web_page",
    "execute_code",
    "set_sandbox_client",
]
