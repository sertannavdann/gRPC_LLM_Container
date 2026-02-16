"""
Rate Limited API Scenario - API with 429 responses and retry logic.

Example: Gaming APIs, Social media APIs
Pattern: 429 handling, exponential backoff, Retry-After header
"""
from .registry import ScenarioDefinition

SCENARIO = ScenarioDefinition(
    id="rate_limited_api",
    name="Rate Limited API",
    description="API with rate limiting that returns 429 responses and requires retry logic",
    nl_intent="Integrate with a gaming/social API that enforces rate limits via 429 responses",
    category="gaming",
    auth_type="api_key",
    capabilities={
        "read": True,
        "write": False,
        "pagination": False,
        "rate_limited": True,
    },
    required_methods=["fetch_raw", "transform", "get_schema"],
    test_suites=["auth_api_key", "rate_limit_429", "schema_drift"],
    edge_cases=[
        "429 with Retry-After header in seconds",
        "429 with Retry-After header in HTTP date",
        "Exponential backoff without Retry-After",
        "Max retries exhausted",
        "Jitter to prevent thundering herd",
        "Rate limit reset at specific time window",
    ],
    example_platforms=["clashroyale", "twitter", "reddit"],
)
