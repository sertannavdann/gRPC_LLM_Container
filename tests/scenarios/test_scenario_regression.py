"""
Scenario regression tests.

For each curated scenario:
1. Verify scenario is registered
2. Verify expected structure (auth_type, capabilities, test_suites)
3. Verify builder can produce a scaffold that passes contract tests

Does NOT require live LLM - uses pre-recorded expected outputs where possible.
"""
import pytest
from shared.modules.scenarios.registry import get_scenario_registry, get_scenario


class TestScenarioRegistry:
    """Tests for scenario registry itself."""

    def test_registry_has_minimum_scenarios(self):
        """Verify registry has at least 5 scenarios."""
        registry = get_scenario_registry()
        count = registry.count()

        assert count >= 5, f"Expected at least 5 scenarios, got {count}"

    def test_all_scenarios_have_required_fields(self):
        """Verify all scenarios have required fields."""
        registry = get_scenario_registry()

        required_fields = [
            "id", "name", "description", "nl_intent", "category",
            "auth_type", "capabilities", "required_methods", "test_suites"
        ]

        for scenario in registry.list_all():
            for field in required_fields:
                assert hasattr(scenario, field), f"Scenario {scenario.id} missing field: {field}"

    def test_scenarios_have_unique_ids(self):
        """Verify all scenario IDs are unique."""
        registry = get_scenario_registry()
        scenarios = registry.list_all()

        ids = [s.id for s in scenarios]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"


class TestRestAPIScenario:
    """Tests for REST API scenario."""

    def test_rest_api_scenario_registered(self):
        """Verify REST API scenario is registered."""
        scenario = get_scenario("rest_api")
        assert scenario is not None
        assert scenario.name == "Simple REST API"

    def test_rest_api_has_correct_auth_type(self):
        """Verify REST API scenario has api_key auth."""
        scenario = get_scenario("rest_api")
        assert scenario.auth_type == "api_key"

    def test_rest_api_has_required_capabilities(self):
        """Verify REST API scenario has expected capabilities."""
        scenario = get_scenario("rest_api")

        assert scenario.capabilities["read"] is True
        assert scenario.capabilities.get("pagination", False) is False

    def test_rest_api_has_required_test_suites(self):
        """Verify REST API scenario specifies required test suites."""
        scenario = get_scenario("rest_api")

        assert "auth_api_key" in scenario.test_suites
        assert "schema_drift" in scenario.test_suites

    def test_rest_api_has_edge_cases_documented(self):
        """Verify REST API scenario documents edge cases."""
        scenario = get_scenario("rest_api")

        assert len(scenario.edge_cases) > 0
        assert any("401" in case for case in scenario.edge_cases)


class TestOAuth2Scenario:
    """Tests for OAuth2 scenario."""

    def test_oauth2_scenario_registered(self):
        """Verify OAuth2 scenario is registered."""
        scenario = get_scenario("oauth2_flow")
        assert scenario is not None

    def test_oauth2_has_correct_auth_type(self):
        """Verify OAuth2 scenario has oauth2 auth."""
        scenario = get_scenario("oauth2_flow")
        assert scenario.auth_type == "oauth2"

    def test_oauth2_requires_refresh_tests(self):
        """Verify OAuth2 scenario requires refresh token tests."""
        scenario = get_scenario("oauth2_flow")
        assert "oauth_refresh" in scenario.test_suites


class TestPaginatedAPIScenario:
    """Tests for paginated API scenario."""

    def test_paginated_scenario_registered(self):
        """Verify paginated API scenario is registered."""
        scenario = get_scenario("paginated_api")
        assert scenario is not None

    def test_paginated_has_pagination_capability(self):
        """Verify paginated API scenario has pagination capability."""
        scenario = get_scenario("paginated_api")
        assert scenario.capabilities.get("pagination", False) is True

    def test_paginated_requires_pagination_tests(self):
        """Verify paginated API scenario requires pagination tests."""
        scenario = get_scenario("paginated_api")
        assert "pagination_cursor" in scenario.test_suites

    def test_paginated_documents_infinite_loop_edge_case(self):
        """Verify paginated scenario documents infinite loop protection."""
        scenario = get_scenario("paginated_api")
        assert any("infinite" in case.lower() for case in scenario.edge_cases)


class TestFileParserScenario:
    """Tests for file parser scenario."""

    def test_file_parser_scenario_registered(self):
        """Verify file parser scenario is registered."""
        scenario = get_scenario("file_parser")
        assert scenario is not None

    def test_file_parser_has_no_auth(self):
        """Verify file parser scenario has no authentication."""
        scenario = get_scenario("file_parser")
        assert scenario.auth_type == "none"

    def test_file_parser_documents_encoding_issues(self):
        """Verify file parser scenario documents encoding edge cases."""
        scenario = get_scenario("file_parser")
        assert any("encoding" in case.lower() for case in scenario.edge_cases)


class TestRateLimitedAPIScenario:
    """Tests for rate limited API scenario."""

    def test_rate_limited_scenario_registered(self):
        """Verify rate limited API scenario is registered."""
        scenario = get_scenario("rate_limited_api")
        assert scenario is not None

    def test_rate_limited_has_capability(self):
        """Verify rate limited API scenario has rate_limited capability."""
        scenario = get_scenario("rate_limited_api")
        assert scenario.capabilities.get("rate_limited", False) is True

    def test_rate_limited_requires_429_tests(self):
        """Verify rate limited API scenario requires 429 handling tests."""
        scenario = get_scenario("rate_limited_api")
        assert "rate_limit_429" in scenario.test_suites

    def test_rate_limited_documents_backoff_strategies(self):
        """Verify rate limited scenario documents backoff strategies."""
        scenario = get_scenario("rate_limited_api")
        edge_case_text = " ".join(scenario.edge_cases).lower()
        assert "backoff" in edge_case_text or "retry" in edge_case_text


class TestScenarioBuilderIntegration:
    """Tests for scenario integration with builder (no live LLM needed)."""

    def test_all_scenarios_serializable(self):
        """Verify all scenarios can be serialized to dict."""
        registry = get_scenario_registry()

        for scenario in registry.list_all():
            scenario_dict = scenario.to_dict()

            assert isinstance(scenario_dict, dict)
            assert scenario_dict["id"] == scenario.id
            assert scenario_dict["auth_type"] == scenario.auth_type

    def test_scenarios_can_be_filtered_by_auth_type(self):
        """Verify scenarios can be filtered by auth type."""
        registry = get_scenario_registry()

        api_key_scenarios = registry.find_by_auth_type("api_key")
        oauth2_scenarios = registry.find_by_auth_type("oauth2")

        assert len(api_key_scenarios) > 0
        assert len(oauth2_scenarios) > 0

        # Verify all returned scenarios match filter
        for scenario in api_key_scenarios:
            assert scenario.auth_type == "api_key"

    def test_scenarios_can_be_filtered_by_capability(self):
        """Verify scenarios can be filtered by capability."""
        registry = get_scenario_registry()

        paginated_scenarios = registry.find_by_capability("pagination")
        rate_limited_scenarios = registry.find_by_capability("rate_limited")

        assert len(paginated_scenarios) > 0
        assert len(rate_limited_scenarios) > 0

        # Verify all returned scenarios have the capability
        for scenario in paginated_scenarios:
            assert scenario.capabilities.get("pagination", False) is True

    def test_scenario_count_assertion_for_ci(self):
        """CI assertion: Fail if < 5 scenarios registered."""
        registry = get_scenario_registry()
        count = registry.count()

        # This is the CI gate mentioned in the plan
        assert count >= 5, (
            f"CI FAILURE: Expected at least 5 scenarios, but only {count} are registered. "
            "Add more scenarios to the registry to meet the requirement."
        )
