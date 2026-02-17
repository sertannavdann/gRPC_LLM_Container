"""
UserContextTool - Consolidated user context, daily briefing, commute, and finance query.

Replaces 4 separate tool functions:
    - get_user_context
    - get_daily_briefing
    - get_commute_time
    - query_finance

All functionality unified behind a single BaseTool with category/action routing.
"""
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests

from tools.base import BaseTool
from .context_bridge import ContextBridge

logger = logging.getLogger(__name__)


class UserContextTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """
    Get user's personal context: calendar, finance, health, navigation,
    weather, gaming. For finance queries use action='query'.
    """

    name = "user_context"
    description = (
        "Get user's personal context: calendar, finance, health, navigation, "
        "weather, gaming. For finance queries use action='query'."
    )
    version = "2.0.0"

    def __init__(self, context_bridge: Optional[ContextBridge] = None):
        self._bridge = context_bridge or ContextBridge()

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        """Validate and normalize input parameters."""
        return {
            "category": kwargs.get("category", "all"),
            "action": kwargs.get("action", "summary"),
            "destination": kwargs.get("destination"),
            "include_alerts": kwargs.get("include_alerts", True),
            "categories": kwargs.get("categories"),
            # Finance query params
            "finance_action": kwargs.get("finance_action", "transactions"),
            "search": kwargs.get("search"),
            "sort": kwargs.get("sort", "timestamp"),
            "sort_dir": kwargs.get("sort_dir", "desc"),
            "page": kwargs.get("page", 1),
            "per_page": kwargs.get("per_page", 10),
            "group_by": kwargs.get("group_by", "category"),
            "date_from": kwargs.get("date_from"),
            "date_to": kwargs.get("date_to"),
        }

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Route to appropriate handler based on category/action."""
        category = request.get("category", "all")
        action = request.get("action", "summary")

        if category == "finance" and action == "query":
            return self._handle_finance_query(request)

        if category == "navigation" or request.get("destination"):
            return self._handle_commute(request)

        return self._handle_context_summary(request)

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Pass through — response already has status key."""
        return response

    # ── Context Summary (absorbs get_user_context + get_daily_briefing) ──

    def _handle_context_summary(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch and summarize context across categories."""
        try:
            categories = request.get("categories") or [request.get("category", "all")]
            destination = request.get("destination")

            # Try dashboard summary endpoint first
            if not self._bridge.is_mock_mode() and "all" in categories:
                result = self._fetch_summary_from_dashboard(destination=destination)
                if result and result.get("summary"):
                    return {
                        "status": "success",
                        "summary": result["summary"],
                        "categories_retrieved": result.get("categories_retrieved", []),
                        "alert_count": result.get("alert_count", 0),
                        "timestamp": result.get("timestamp", datetime.now().isoformat()),
                    }

            # Fallback: fetch raw context and build summaries locally
            context = None
            if not self._bridge.is_mock_mode():
                fetch_categories = None if "all" in categories else categories
                context = self._bridge.fetch(categories=fetch_categories)
                if context:
                    logger.debug("Using real context from dashboard")

            if not context:
                logger.debug("No context available — returning empty summary")
                return {
                    "status": "success",
                    "summary": "No context data available.",
                    "categories_retrieved": [],
                    "alert_count": 0,
                    "timestamp": datetime.now().isoformat(),
                }

            # Try dashboard formatters
            try:
                from dashboard_service.formatters import build_full_summary
                result = build_full_summary(context, destination=destination)
            except ImportError:
                result = self._build_fallback_summary(context, categories, destination)

            return {
                "status": "success",
                "summary": result.get("summary", ""),
                "categories_retrieved": result.get("categories_retrieved", []),
                "alert_count": result.get("alert_count", 0),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to retrieve user context: {e}", exc_info=True)
            return {"status": "error", "error": f"Failed to retrieve user context: {str(e)}"}

    def _fetch_summary_from_dashboard(
        self, destination: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch pre-built summary from dashboard formatters endpoint."""
        try:
            params: Dict[str, str] = {}
            if destination:
                params["destination"] = destination
            resp = requests.get(
                f"{self._bridge.dashboard_url}/context/summary/default",
                params=params,
                headers=self._bridge._headers,
                timeout=self._bridge.timeout,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Dashboard summary endpoint unreachable: {e}")
        return None

    @staticmethod
    def _build_fallback_summary(
        context: dict, categories: List[str], destination: Optional[str]
    ) -> Dict[str, Any]:
        """Minimal inline summary when dashboard_service.formatters unavailable."""
        parts = []
        cats = []
        for cat in ["calendar", "finance", "health", "navigation", "weather", "gaming"]:
            if "all" in categories or cat in categories:
                data = context.get(cat)
                if data:
                    cats.append(cat)
                    parts.append(f"{cat.upper()}: data available")
        return {
            "summary": "\n".join(parts) if parts else "No context data available.",
            "categories_retrieved": cats,
            "alert_count": 0,
        }

    # ── Commute / Navigation (absorbs get_commute_time) ──────────────

    def _handle_commute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle commute/navigation queries."""
        try:
            destination = request.get("destination")

            context = None
            if not self._bridge.is_mock_mode():
                context = self._bridge.fetch(categories=["navigation"])

            if not context:
                return {"status": "error", "error": "Navigation data not available"}

            nav_data = context.get("navigation", {})
            # For categories without real adapter, extract raw data
            if isinstance(nav_data, dict) and "raw" in nav_data:
                nav_data = nav_data["raw"]

            if destination:
                dest_clean = destination.lower().strip()
                for word in ["the", "my", "to", "go", "drive", "from", "work", "place"]:
                    dest_clean = dest_clean.replace(f"{word} ", "").replace(f" {word}", "")
                dest_clean = dest_clean.strip()

                saved = nav_data.get("saved_destinations", {})
                for key, dest_info in saved.items():
                    dest_name = dest_info.get("name", "").lower()
                    dest_address = dest_info.get("address", "").lower()
                    if (
                        dest_clean in key.lower()
                        or key.lower() in dest_clean
                        or dest_clean in dest_name
                        or dest_name in dest_clean
                        or dest_clean in dest_address
                        or dest_address in dest_clean
                    ):
                        eta = dest_info.get("eta_minutes", 0)
                        name = dest_info.get("name", destination)
                        address = dest_info.get("address", "")
                        return {
                            "status": "success",
                            "summary": f"To {name}: approximately {eta} minutes\nAddress: {address}",
                            "destination": name,
                            "address": address,
                            "eta_minutes": eta,
                            "traffic_level": "moderate",
                        }

                available = [d.get("name", k) for k, d in saved.items()]
                return {
                    "status": "error",
                    "error": f"Destination '{destination}' not found",
                    "available_destinations": available,
                }

            # Default commute
            route = nav_data.get("primary_route", {})
            if not route:
                return {"status": "error", "error": "No default commute route configured"}

            eta = route.get("duration_minutes", 0)
            traffic = route.get("traffic_level", "unknown")
            dest_name = route.get("destination_name", "Work")

            return {
                "status": "success",
                "summary": f"To {dest_name}: {eta} minutes ({traffic} traffic)",
                "destination": dest_name,
                "address": route.get("destination", ""),
                "eta_minutes": eta,
                "traffic_level": traffic,
                "distance_km": route.get("distance_km", 0),
            }

        except Exception as e:
            logger.error(f"Failed to get commute time: {e}", exc_info=True)
            return {"status": "error", "error": f"Failed to get commute time: {str(e)}"}

    # ── Finance Query (absorbs query_finance) ────────────────────────

    def _handle_finance_query(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle structured finance queries via dashboard bank endpoints."""
        dashboard_url = self._bridge.dashboard_url
        timeout = self._bridge.timeout
        action = (request.get("finance_action") or "transactions").lower().strip()
        per_page = max(1, min(request.get("per_page", 10), 50))
        page = max(1, request.get("page", 1))

        try:
            if action == "transactions":
                return self._get_transactions(
                    dashboard_url, timeout,
                    category=request.get("search_category"),
                    search=request.get("search"),
                    sort=request.get("sort", "timestamp"),
                    sort_dir=request.get("sort_dir", "desc"),
                    page=page, per_page=per_page,
                    date_from=request.get("date_from"),
                    date_to=request.get("date_to"),
                )
            elif action == "summary":
                return self._get_summary(
                    dashboard_url, timeout,
                    group_by=request.get("group_by", "category"),
                    category=request.get("search_category"),
                    search=request.get("search"),
                    date_from=request.get("date_from"),
                    date_to=request.get("date_to"),
                )
            elif action == "categories":
                return self._get_categories(dashboard_url, timeout)
            elif action == "search":
                search = request.get("search")
                if not search:
                    return {"status": "error", "error": "The 'search' param is required for action='search'."}
                return self._search_transactions(dashboard_url, timeout, query=search)
            else:
                return {
                    "status": "error",
                    "error": f"Unknown finance action '{action}'. Use 'transactions', 'summary', 'categories', or 'search'.",
                }
        except Exception as exc:
            logger.error(f"finance query ({action}) failed: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _get_transactions(url, timeout, **kwargs) -> Dict[str, Any]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        resp = requests.get(f"{url}/bank/transactions", params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        txns = data.get("transactions", [])
        return {
            "status": "success",
            "data": {
                "transactions": _format_transactions(txns),
                "total": data.get("total", len(txns)),
                "page": data.get("page", 1),
                "pages": data.get("pages", 1),
            },
        }

    @staticmethod
    def _get_summary(url, timeout, **kwargs) -> Dict[str, Any]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        resp = requests.get(f"{url}/bank/summary", params=params, timeout=timeout)
        resp.raise_for_status()
        return {"status": "success", "data": resp.json()}

    @staticmethod
    def _get_categories(url, timeout) -> Dict[str, Any]:
        resp = requests.get(f"{url}/bank/categories", timeout=timeout)
        resp.raise_for_status()
        return {"status": "success", "data": resp.json()}

    @staticmethod
    def _search_transactions(url, timeout, query: str, limit: int = 20) -> Dict[str, Any]:
        resp = requests.get(
            f"{url}/bank/search",
            params={"query": query, "limit": limit},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return {
            "status": "success",
            "data": {
                "results": _format_transactions(results),
                "total": data.get("total", len(results)),
                "query": query,
            },
        }


def _format_transactions(txns: list) -> list:
    """Produce concise per-transaction dict for LLM presentation."""
    formatted = []
    for t in txns:
        formatted.append({
            "date": t.get("timestamp", "")[:10],
            "merchant": t.get("merchant", "Unknown"),
            "amount": t.get("amount", 0),
            "category": t.get("spending_category", t.get("category", "Other")),
            "description": t.get("description", ""),
            "type": "debit" if t.get("is_debit", True) else "credit",
        })
    return formatted


# ── Backward-compat module-level functions ───────────────────────────

_default_tool: Optional[UserContextTool] = None


def _get_default() -> UserContextTool:
    global _default_tool
    if _default_tool is None:
        _default_tool = UserContextTool()
    return _default_tool


def get_user_context(
    categories: List[str] = None,
    include_alerts: bool = True,
    destination: str = None,
) -> Dict[str, Any]:
    """Legacy wrapper for backward compatibility."""
    tool = _get_default()
    return tool(
        category="all",
        action="summary",
        categories=categories or ["all"],
        include_alerts=include_alerts,
        destination=destination,
    )


def get_daily_briefing() -> Dict[str, Any]:
    """Legacy wrapper for backward compatibility."""
    return get_user_context(categories=["all"], include_alerts=True)


def get_commute_time(destination: str = None) -> Dict[str, Any]:
    """Legacy wrapper for backward compatibility."""
    tool = _get_default()
    return tool(category="navigation", action="summary", destination=destination)
