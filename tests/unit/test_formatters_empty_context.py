"""
The dashboard summary formatters must survive the aggregator's empty defaults.

Regression: with no health/navigation/weather adapter configured the context
carries None values; the formatters raised, /context/summary returned 500 and
the orchestrator fell back to a placeholder the model then filled in.
"""
import pytest

from dashboard_service.formatters import build_full_summary

EMPTY_CONTEXT = {
    "finance": {"transactions": [], "accounts": [], "platforms": []},
    "calendar": {"events": [], "next_3": [], "imminent": [], "today_count": 0, "platforms": []},
    "health": {
        "metrics": [], "today": {}, "steps": 0, "steps_goal": 10000, "steps_progress": 0,
        "heart_rate": None, "hrv": None, "sleep_hours": None, "sleep_score": None,
        "readiness": None, "platforms": [],
    },
    "navigation": {"routes": [], "primary_route": None, "commute": {}, "platforms": []},
    "weather": {"current": None, "forecasts": [], "platforms": []},
    "gaming": {"profiles": [], "platforms": []},
}


def test_empty_context_formats_without_raising():
    result = build_full_summary(EMPTY_CONTEXT)
    assert set(result["categories_retrieved"]) == set(EMPTY_CONTEXT)
    assert result["alert_count"] == 0
    summary = result["summary"]
    assert "No health data available." in summary
    assert "No weather data available." in summary
    assert "No commute configured." in summary
    assert "No finance data available" in summary
    assert "No calendar data available" in summary
    # Never format an absent category as a measurement.
    assert "$0.00" not in summary
    assert "Readiness" not in summary


@pytest.mark.parametrize("category", sorted(EMPTY_CONTEXT))
def test_each_empty_category_alone(category):
    build_full_summary({category: EMPTY_CONTEXT[category]})


def test_real_finance_totals_are_rendered():
    ctx = {
        "finance": {
            "transactions": [], "accounts": [], "platforms": ["cibc"],
            "recent_count": 3, "total_expenses_period": 120.5,
            "total_income_period": 300.0, "net_cashflow": 179.5,
        }
    }
    summary = build_full_summary(ctx)["summary"]
    assert "FINANCE" in summary
    assert "120" in summary or "300" in summary or "179" in summary
