"""
Finance Query Tool — structured access to bank transaction data.

Bridges the dashboard_service bank endpoints (transactions, summary,
categories, search) so the LLM can answer itemised finance questions
like "show my 5 largest purchases" or "how much did I spend on food
this month".

All calls go through the dashboard REST API (same network as the
context bridge) so there are no direct DB dependencies.
"""

import logging
import os
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger(__name__)

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8001")
_TIMEOUT = 10  # seconds


# ── Public tool functions (registered in orchestrator) ────────────────

def query_finance(
    action: str = "transactions",
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "timestamp",
    sort_dir: str = "desc",
    page: int = 1,
    per_page: int = 10,
    group_by: str = "category",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query the user's bank transaction data.

    Use this tool when the user asks about their spending, purchases,
    transactions, bank account, finances, or wants to see specific
    transaction details.

    Args:
        action (str): One of "transactions", "summary", "categories",
            or "search".  Default "transactions".
        category (str): Filter by spending category (e.g. "Food & Dining",
            "Transportation").  Optional.
        search (str): Free-text search across merchants / descriptions.
            Required when action="search".
        sort (str): Sort field — "timestamp", "amount", "merchant",
            "category".  Default "timestamp".
        sort_dir (str): "asc" or "desc".  Default "desc" (newest first).
        page (int): Page number (1-based).  Default 1.
        per_page (int): Results per page (1-50).  Default 10.
        group_by (str): Grouping for summary — "category", "company",
            "month", "year".  Default "category".
        date_from (str): Start date filter (YYYY-MM-DD).  Optional.
        date_to (str): End date filter (YYYY-MM-DD).  Optional.

    Returns:
        Dict with status key:
            - status: "success" or "error"
            - data: The query results (transactions list, summary groups,
              categories, or search matches)

    Examples:
        - query_finance(action="transactions", sort="amount", sort_dir="desc", per_page=5)
          → 5 largest transactions
        - query_finance(action="summary", group_by="category")
          → spending totals grouped by category
        - query_finance(action="search", search="uber")
          → all Uber-related transactions
        - query_finance(action="categories")
          → list of all spending categories with totals
    """
    action = (action or "transactions").lower().strip()
    per_page = max(1, min(per_page, 50))
    page = max(1, page)

    try:
        if action == "transactions":
            return _get_transactions(
                category=category,
                search=search,
                sort=sort,
                sort_dir=sort_dir,
                page=page,
                per_page=per_page,
                date_from=date_from,
                date_to=date_to,
            )
        elif action == "summary":
            return _get_summary(
                group_by=group_by,
                category=category,
                search=search,
                date_from=date_from,
                date_to=date_to,
            )
        elif action == "categories":
            return _get_categories()
        elif action == "search":
            if not search:
                return {
                    "status": "error",
                    "error": "The 'search' parameter is required for action='search'.",
                }
            return _search_transactions(query=search)
        else:
            return {
                "status": "error",
                "error": (
                    f"Unknown action '{action}'. "
                    "Use 'transactions', 'summary', 'categories', or 'search'."
                ),
            }
    except Exception as exc:
        logger.error(f"query_finance({action}) failed: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}


# ── Private HTTP helpers ──────────────────────────────────────────────

def _get_transactions(**kwargs) -> Dict[str, Any]:
    params = {k: v for k, v in kwargs.items() if v is not None}
    resp = requests.get(
        f"{DASHBOARD_URL}/bank/transactions",
        params=params,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # Enrich for readability
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


def _get_summary(**kwargs) -> Dict[str, Any]:
    params = {k: v for k, v in kwargs.items() if v is not None}
    resp = requests.get(
        f"{DASHBOARD_URL}/bank/summary",
        params=params,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "status": "success",
        "data": data,
    }


def _get_categories() -> Dict[str, Any]:
    resp = requests.get(
        f"{DASHBOARD_URL}/bank/categories",
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "status": "success",
        "data": data,
    }


def _search_transactions(query: str, limit: int = 20) -> Dict[str, Any]:
    resp = requests.get(
        f"{DASHBOARD_URL}/bank/search",
        params={"query": query, "limit": limit},
        timeout=_TIMEOUT,
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
    """
    Produce a concise per-transaction dict the LLM can present directly.

    Strips internal metadata, keeps human-readable fields.
    """
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
