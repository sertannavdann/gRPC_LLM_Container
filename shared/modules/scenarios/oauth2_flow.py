"""
OAuth2 Flow Scenario - OAuth2 API with token refresh.

Example: Google Calendar, Microsoft Graph, Salesforce
Pattern: OAuth2 auth code flow, token refresh, scoped access
"""
from .registry import ScenarioDefinition

SCENARIO = ScenarioDefinition(
    id="oauth2_flow",
    name="OAuth2 API",
    description="OAuth2 API with authorization code flow and token refresh",
    nl_intent="Integrate with a calendar/CRM/productivity API that uses OAuth2 for authentication",
    category="calendar",
    auth_type="oauth2",
    capabilities={
        "read": True,
        "write": True,
        "pagination": False,
        "rate_limited": False,
    },
    required_methods=["fetch_raw", "transform", "get_schema"],
    test_suites=["oauth_refresh", "schema_drift"],
    edge_cases=[
        "Access token expiration and automatic refresh",
        "Refresh token expiration requires re-auth",
        "Invalid grant errors during token exchange",
        "Scope permissions mismatch",
        "Concurrent request token refresh race condition",
    ],
    example_platforms=["google_calendar", "microsoft_graph", "salesforce"],
)
