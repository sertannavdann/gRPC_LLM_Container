"""
Built-in tools — consolidated class-based tools with backward-compat functions.

Primary tools (class-based, constructor DI):
- UserContextTool — context, briefing, commute, finance queries
- WebTool — web search + page loading
- KnowledgeSearchTool — ChromaDB vector search
- KnowledgeStoreTool — ChromaDB vector storage
- MathSolverTool — safe math evaluation
- CodeExecutorTool — sandboxed code execution
- ModulePipelineTool — build/write/repair/validate/install
- ModuleAdminTool — list/enable/disable/credentials/draft/version

All tools follow the standardized return format:
    {"status": "success|error", "data": ..., "error": ...}
"""

# ── New class-based tools ─────────────────────────────────────────────
from .user_context import UserContextTool
from .web_tools import WebTool
from .knowledge_search import KnowledgeSearchTool
from .knowledge_store import KnowledgeStoreTool
from .math_solver import MathSolverTool
from .code_executor import CodeExecutorTool
from .module_pipeline import ModulePipelineTool
from .module_admin import ModuleAdminTool

# ── Backward-compat function imports ──────────────────────────────────
from .web_tools import web_search, load_web_page
from .math_solver import math_solver
from .code_executor import execute_code, set_sandbox_client
from .user_context import get_user_context, get_daily_briefing, get_commute_time

__all__ = [
    # Classes
    "UserContextTool",
    "WebTool",
    "KnowledgeSearchTool",
    "KnowledgeStoreTool",
    "MathSolverTool",
    "CodeExecutorTool",
    "ModulePipelineTool",
    "ModuleAdminTool",
    # Backward-compat functions
    "web_search",
    "load_web_page",
    "math_solver",
    "execute_code",
    "set_sandbox_client",
    "get_user_context",
    "get_daily_briefing",
    "get_commute_time",
]
