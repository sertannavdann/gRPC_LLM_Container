"""
Unit tests for the finance_query tool.

Tests all four actions (transactions, summary, categories, search)
with mocked HTTP responses from the dashboard bank endpoints.
"""

import pytest
from unittest.mock import Mock, patch

from tools.builtin.finance_query import (
    query_finance,
    _format_transactions,
)


# ── Fixture data ──────────────────────────────────────────────────────

SAMPLE_TRANSACTIONS = [
    {
        "timestamp": "2025-12-01T10:00:00",
        "merchant": "Uber",
        "amount": 25.50,
        "spending_category": "Transportation",
        "description": "Uber ride downtown",
        "is_debit": True,
    },
    {
        "timestamp": "2025-12-02T12:30:00",
        "merchant": "Whole Foods",
        "amount": 87.30,
        "spending_category": "Food & Dining",
        "description": "Groceries",
        "is_debit": True,
    },
]


def _mock_json_response(data, status=200):
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = data
    resp.raise_for_status = Mock()
    return resp


# ── Tests ─────────────────────────────────────────────────────────────

class TestQueryFinanceTransactions:
    @patch("tools.builtin.finance_query.requests.get")
    def test_transactions_success(self, mock_get):
        mock_get.return_value = _mock_json_response({
            "transactions": SAMPLE_TRANSACTIONS,
            "total": 2,
            "page": 1,
            "pages": 1,
        })

        result = query_finance(action="transactions", per_page=5)

        assert result["status"] == "success"
        assert len(result["data"]["transactions"]) == 2
        assert result["data"]["transactions"][0]["merchant"] == "Uber"
        mock_get.assert_called_once()

    @patch("tools.builtin.finance_query.requests.get")
    def test_transactions_with_sort(self, mock_get):
        mock_get.return_value = _mock_json_response({
            "transactions": SAMPLE_TRANSACTIONS,
            "total": 2,
            "page": 1,
            "pages": 1,
        })

        query_finance(action="transactions", sort="amount", sort_dir="desc")
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))
        assert params["sort"] == "amount"
        assert params["sort_dir"] == "desc"


class TestQueryFinanceSummary:
    @patch("tools.builtin.finance_query.requests.get")
    def test_summary_by_category(self, mock_get):
        mock_get.return_value = _mock_json_response({
            "group_by": "category",
            "groups": [
                {"name": "Food & Dining", "total": 500, "count": 10},
                {"name": "Transportation", "total": 200, "count": 5},
            ],
            "total_transactions": 15,
        })

        result = query_finance(action="summary", group_by="category")
        assert result["status"] == "success"
        assert "groups" in result["data"]


class TestQueryFinanceCategories:
    @patch("tools.builtin.finance_query.requests.get")
    def test_categories_list(self, mock_get):
        mock_get.return_value = _mock_json_response({
            "categories": [
                {"name": "Food & Dining", "total": 500, "count": 10},
            ],
        })

        result = query_finance(action="categories")
        assert result["status"] == "success"
        assert "categories" in result["data"]


class TestQueryFinanceSearch:
    @patch("tools.builtin.finance_query.requests.get")
    def test_search_by_merchant(self, mock_get):
        mock_get.return_value = _mock_json_response({
            "query": "uber",
            "results": SAMPLE_TRANSACTIONS[:1],
            "total": 1,
        })

        result = query_finance(action="search", search="uber")
        assert result["status"] == "success"
        assert result["data"]["total"] == 1

    def test_search_missing_query(self):
        result = query_finance(action="search", search=None)
        assert result["status"] == "error"
        assert "required" in result["error"].lower()


class TestQueryFinanceEdgeCases:
    def test_unknown_action(self):
        result = query_finance(action="foobar")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_per_page_clamping(self):
        """per_page should be clamped between 1 and 50."""
        with patch("tools.builtin.finance_query.requests.get") as mock_get:
            mock_get.return_value = _mock_json_response({"transactions": [], "total": 0, "page": 1, "pages": 0})
            query_finance(action="transactions", per_page=999)
            params = mock_get.call_args.kwargs.get("params", {})
            assert params["per_page"] == 50

    @patch("tools.builtin.finance_query.requests.get")
    def test_http_error(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        result = query_finance(action="transactions")
        assert result["status"] == "error"


class TestFormatTransactions:
    def test_format_basic(self):
        formatted = _format_transactions(SAMPLE_TRANSACTIONS)
        assert len(formatted) == 2
        assert formatted[0]["date"] == "2025-12-01"
        assert formatted[0]["merchant"] == "Uber"
        assert formatted[0]["type"] == "debit"

    def test_format_empty(self):
        assert _format_transactions([]) == []
