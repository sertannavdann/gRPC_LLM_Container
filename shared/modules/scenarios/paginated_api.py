"""
Paginated API Scenario - API with cursor-based pagination.

Example: GitHub API, Twitter API, Stripe API
Pattern: Cursor/offset pagination, max pages guard, repeated cursor detection
"""
from .registry import ScenarioDefinition

SCENARIO = ScenarioDefinition(
    id="paginated_api",
    name="Paginated API",
    description="API with cursor-based or offset pagination for large result sets",
    nl_intent="Integrate with a search/list/collection API that returns paginated results",
    category="social",
    auth_type="api_key",
    capabilities={
        "read": True,
        "write": False,
        "pagination": True,
        "rate_limited": False,
    },
    required_methods=["fetch_raw", "transform", "get_schema"],
    test_suites=["auth_api_key", "pagination_cursor", "schema_drift"],
    edge_cases=[
        "Infinite pagination loop (same cursor repeated)",
        "Max pages guard prevents infinite requests",
        "Empty final page handling",
        "Cursor encoding/decoding",
        "Page size parameter validation",
    ],
    example_platforms=["github", "twitter", "stripe"],
)
