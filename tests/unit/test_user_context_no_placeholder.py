"""
UserContextTool must never hand the model a placeholder.

Regression (USAGE-LOG S3): with explicit categories the tool returned
"FINANCE: data available\\nWEATHER: data available" with status=success and
the model invented the numbers. Unavailable data is an error to report.
"""
from unittest.mock import MagicMock, patch

from tools.builtin.context_bridge import ContextBridge
from tools.builtin.user_context import UserContextTool


def _tool() -> UserContextTool:
    bridge = ContextBridge(dashboard_url="http://dashboard.test:8001")
    bridge.is_mock_mode = lambda: False  # type: ignore[method-assign]
    return UserContextTool(context_bridge=bridge)


def test_unreachable_dashboard_is_an_error_not_a_placeholder():
    tool = _tool()
    with patch("tools.builtin.user_context.requests.get", side_effect=ConnectionError("down")):
        result = tool(category="all", action="summary", categories=["finance", "weather", "calendar"])

    assert result["status"] == "error"
    assert "unavailable" in result["error"].lower()
    assert "data available" not in str(result).lower()


def test_requested_categories_are_forwarded_to_the_dashboard_summary():
    tool = _tool()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "summary": "FINANCE:\nNo transactions found.",
        "categories_retrieved": ["finance"],
        "alert_count": 0,
    }
    with patch("tools.builtin.user_context.requests.get", return_value=resp) as get:
        result = tool(category="all", action="summary", categories=["finance"])

    assert result["status"] == "success"
    assert result["summary"].startswith("FINANCE")
    url = get.call_args[0][0]
    assert url.endswith("/context/summary/default")
    assert get.call_args.kwargs["params"]["categories"] == ["finance"]


def test_all_categories_sends_no_filter():
    tool = _tool()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"summary": "CALENDAR:\nNo events.", "categories_retrieved": ["calendar"]}
    with patch("tools.builtin.user_context.requests.get", return_value=resp) as get:
        tool(category="all", action="summary", categories=["all"])
    assert "categories" not in get.call_args.kwargs["params"]
