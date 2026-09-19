"""
Tool registration for the orchestrator's LLM-facing tool registry.

Kept free of gRPC/LLM/DB imports so a unit test can run it end to end
(tests/unit/test_tool_registration.py). Every name the model can call is
registered through a function with a real typed signature: the legacy
module-level wrappers, or a small closure that injects a composite tool's
`action`. The registry builds parameter schemas from Python signatures, and a
tool *instance* only exposes __call__(**kwargs) — registering instances
directly exported every tool as a single "kwargs" parameter (USAGE-LOG S2).
"""
from __future__ import annotations

import functools
import importlib
from typing import Any, Dict

from tools.registry import LocalToolRegistry

# Alias names the graph prompt (core/graph.py) and intent patterns rely on.
ALIAS_NAMES = (
    "get_user_context", "get_daily_briefing", "get_commute_time", "query_finance",
    "web_search", "load_web_page",
    "build_module", "write_module_code", "validate_module", "install_module",
    "list_modules", "enable_module", "disable_module", "store_module_credentials", "uninstall_module",
)
PRIMARY_NAMES = (
    "user_context", "web", "search_knowledge", "store_knowledge",
    "math_solver", "execute_code", "module_pipeline", "module_admin",
)


def register_agent_tools(
    registry: LocalToolRegistry,
    *,
    user_context_tool,
    web_tool,
    knowledge_search_tool,
    knowledge_store_tool,
    math_tool,
    code_executor_tool,
    module_pipeline_tool,
    module_admin_tool,
) -> None:
    """Register the 8 primary tools and their named aliases on `registry`."""
    # ── Tool registration ────────────────────────────────────────
    # The registry builds parameter schemas from Python signatures, and a
    # tool *instance* only exposes __call__(**kwargs). So every name the
    # model can call is registered through a function with a real typed
    # signature (the legacy module-level wrappers, or a small closure that
    # injects the composite tool's `action`), while execution still goes
    # through the configured instances above. The graph prompt
    # (core/graph.py) and intent patterns speak in these names.
    from typing import List as _List, Optional as _Optional
    _uc_mod = importlib.import_module("tools.builtin.user_context")
    _web_mod = importlib.import_module("tools.builtin.web_tools")
    _math_mod = importlib.import_module("tools.builtin.math_solver")
    _code_mod = importlib.import_module("tools.builtin.code_executor")
    from tools.builtin.knowledge_search import search_knowledge as _search_knowledge_sig
    from tools.builtin.knowledge_store import store_knowledge as _store_knowledge_sig
    from tools.builtin.module_builder import (
        build_module as _build_sig,
        write_module_code as _write_sig,
    )
    from tools.builtin.module_validator import validate_module as _validate_sig
    from tools.builtin.module_installer import (
        install_module as _install_sig,
        uninstall_module as _uninstall_sig,
    )
    from tools.builtin.module_manager import (
        list_modules as _list_sig,
        enable_module as _enable_sig,
        disable_module as _disable_sig,
        store_module_credentials as _creds_sig,
    )

    def _as(tool, sig_func, **fixed):
        """Call `tool` with `fixed` kwargs injected, under `sig_func`'s signature."""
        @functools.wraps(sig_func)  # inspect.signature() follows __wrapped__
        def _call(**kwargs):
            return tool(**fixed, **kwargs)
        return _call

    # Legacy module-level wrappers must execute through the instances built here.
    _uc_mod._default_tool = user_context_tool
    _web_mod._default_tool = web_tool
    _math_mod._default_tool = math_tool
    _code_mod._default_tool = code_executor_tool

    def user_context(
        category: str = "all",
        action: str = "summary",
        categories: _Optional[_List[str]] = None,
        destination: _Optional[str] = None,
        include_alerts: bool = True,
    ) -> Dict[str, Any]:
        """
        Unified access to the user's personal context.

        Args:
            category: all | calendar | finance | weather | gaming | navigation
            action: summary (default) | query (finance only) | commute (navigation)
            categories: Subset of categories to summarise, e.g. ["finance", "weather"]
            destination: Destination for commute time (navigation)
            include_alerts: Include alerts in the summary
        """
        return user_context_tool(
            category=category, action=action, categories=categories,
            destination=destination, include_alerts=include_alerts,
        )

    def query_finance(
        action: str = "transactions",
        search: _Optional[str] = None,
        sort: str = "timestamp",
        sort_dir: str = "desc",
        page: int = 1,
        per_page: int = 10,
        group_by: str = "category",
        date_from: _Optional[str] = None,
        date_to: _Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query the user's bank transactions (real data from the dashboard).

        Args:
            action: transactions | summary | categories | search
            search: Free text over merchant/description (required for action=search)
            sort: timestamp | amount | merchant | category
            sort_dir: asc | desc
            page: 1-based page number
            per_page: Results per page (1-50)
            group_by: category | company | month | year (summary only)
            date_from: Start date YYYY-MM-DD
            date_to: End date YYYY-MM-DD
        """
        return user_context_tool(
            category="finance", action="query", finance_action=action, search=search,
            sort=sort, sort_dir=sort_dir, page=page, per_page=per_page,
            group_by=group_by, date_from=date_from, date_to=date_to,
        )

    def web(
        action: str = "search",
        query: _Optional[str] = None,
        url: _Optional[str] = None,
        num_results: int = 10,
        max_length: int = 5000,
    ) -> Dict[str, Any]:
        """
        Web access.

        Args:
            action: search (needs query) | load (needs url)
            query: Search query for action=search
            url: Page URL for action=load
            num_results: Number of search results
            max_length: Maximum characters of page content to return
        """
        return web_tool(
            action=action, query=query, url=url,
            num_results=num_results, max_length=max_length,
        )

    reg = registry.register

    # ── Primary tools ────────────────────────────────────────────
    reg(user_context, name="user_context", description=user_context_tool.description)
    reg(web, name="web", description=web_tool.description)
    reg(_as(knowledge_search_tool, _search_knowledge_sig), name="search_knowledge", description=knowledge_search_tool.description)
    reg(_as(knowledge_store_tool, _store_knowledge_sig), name="store_knowledge", description=knowledge_store_tool.description)
    reg(_as(math_tool, _math_mod.math_solver), name="math_solver", description=math_tool.description)
    reg(_as(code_executor_tool, _code_mod.execute_code), name="execute_code", description=code_executor_tool.description)
    reg(module_pipeline_tool, name="module_pipeline", description=module_pipeline_tool.description)
    reg(module_admin_tool, name="module_admin", description=module_admin_tool.description)

    # ── Named aliases used by the graph prompt and intent patterns ──
    reg(_uc_mod.get_user_context, name="get_user_context", description="Summarise the user's context (finance, weather, calendar, gaming)")
    reg(_uc_mod.get_daily_briefing, name="get_daily_briefing", description="Today's briefing across all context categories")
    reg(_uc_mod.get_commute_time, name="get_commute_time", description="Commute time to a destination")
    reg(query_finance, name="query_finance", description="Query the user's bank transactions")
    reg(_web_mod.web_search, name="web_search", description="Search the web")
    reg(_web_mod.load_web_page, name="load_web_page", description="Load web page content")
    reg(_as(module_pipeline_tool, _build_sig, action="build"), name="build_module", description="Create a new adapter module scaffold (manifest, adapter skeleton, tests)")
    reg(_as(module_pipeline_tool, _write_sig, action="write_code"), name="write_module_code", description="Write or update the adapter code of an existing module")
    reg(_as(module_pipeline_tool, _validate_sig, action="validate"), name="validate_module", description="Validate a module: syntax, structure and sandbox tests")
    reg(_as(module_pipeline_tool, _install_sig, action="install"), name="install_module", description="Install an approved, validated module into the live system")
    reg(_as(module_admin_tool, _list_sig, action="list"), name="list_modules", description="List installed modules")
    reg(_as(module_admin_tool, _enable_sig, action="enable"), name="enable_module", description="Enable a module")
    reg(_as(module_admin_tool, _disable_sig, action="disable"), name="disable_module", description="Disable a module")
    reg(_as(module_admin_tool, _creds_sig, action="credentials"), name="store_module_credentials", description="Store API credentials for a module")
    reg(_as(module_admin_tool, _uninstall_sig, action="uninstall"), name="uninstall_module", description="Uninstall a module")
