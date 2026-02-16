"""
REST API Scenario - Simple REST API with API key auth.

Example: Weather API, Stock API, News API
Pattern: GET endpoint, API key in header, JSON response
"""
from .registry import ScenarioDefinition

SCENARIO = ScenarioDefinition(
    id="rest_api",
    name="Simple REST API",
    description="Simple REST API with API key authentication and JSON responses",
    nl_intent="Integrate with a weather/stocks/news API that requires an API key and returns JSON data",
    category="weather",  # Example category
    auth_type="api_key",
    capabilities={
        "read": True,
        "write": False,
        "pagination": False,
        "rate_limited": False,
    },
    required_methods=["fetch_raw", "transform", "get_schema"],
    test_suites=["auth_api_key", "schema_drift"],
    edge_cases=[
        "Invalid API key returns 401",
        "Missing required parameters return 400",
        "Network timeout handling",
        "JSON parsing errors",
        "Rate limiting without explicit headers",
    ],
    example_platforms=["openweather", "alphavantage", "newsapi"],
)
