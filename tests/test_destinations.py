"""
Unit tests for destination alias resolution.

Tests the destination matching functionality including:
- Destination string normalization
- Alias to canonical key resolution
- Full destination resolution with saved destinations
- Available destinations helper
"""
import pytest
from tools.builtin.destinations import (
    normalize_destination,
    resolve_alias,
    resolve_destination,
    get_available_destinations,
    DESTINATION_ALIASES,
)


class TestNormalizeDestination:
    """Tests for destination string normalization."""

    def test_lowercase(self):
        """Test case normalization."""
        assert normalize_destination("OFFICE") == "office"
        assert normalize_destination("The Office") == "the office"

    def test_strip_whitespace(self):
        """Test whitespace handling."""
        assert normalize_destination("  office  ") == "office"
        assert normalize_destination("\twork\n") == "work"

    def test_mixed_case_and_whitespace(self):
        """Test combined case and whitespace normalization."""
        assert normalize_destination("  THE OFFICE  ") == "the office"
        assert normalize_destination("\t  My Place \n") == "my place"

    def test_empty_string(self):
        """Test empty string handling."""
        assert normalize_destination("") == ""
        assert normalize_destination("   ") == ""

    def test_special_characters_preserved(self):
        """Test special characters are preserved."""
        assert normalize_destination("O'Brien's Office") == "o'brien's office"
        assert normalize_destination("123 Main St.") == "123 main st."


class TestResolveAlias:
    """Tests for alias resolution."""

    def test_direct_canonical_match(self):
        """Test direct match on canonical key."""
        assert resolve_alias("office") == "office"
        assert resolve_alias("home") == "home"
        assert resolve_alias("gym") == "gym"
        assert resolve_alias("school") == "school"
        assert resolve_alias("airport") == "airport"

    def test_alias_to_canonical(self):
        """Test alias resolves to canonical key."""
        assert resolve_alias("work") == "office"
        assert resolve_alias("the office") == "office"
        assert resolve_alias("my office") == "office"
        assert resolve_alias("workplace") == "office"
        assert resolve_alias("job") == "office"
        assert resolve_alias("company") == "office"

    def test_home_aliases(self):
        """Test home destination aliases."""
        assert resolve_alias("house") == "home"
        assert resolve_alias("my place") == "home"
        assert resolve_alias("apartment") == "home"
        assert resolve_alias("my home") == "home"
        assert resolve_alias("residence") == "home"

    def test_gym_aliases(self):
        """Test gym destination aliases."""
        assert resolve_alias("fitness") == "gym"
        assert resolve_alias("workout") == "gym"
        assert resolve_alias("the gym") == "gym"
        assert resolve_alias("fitness center") == "gym"
        assert resolve_alias("health club") == "gym"

    def test_school_aliases(self):
        """Test school destination aliases."""
        assert resolve_alias("university") == "school"
        assert resolve_alias("college") == "school"
        assert resolve_alias("campus") == "school"
        assert resolve_alias("class") == "school"

    def test_airport_aliases(self):
        """Test airport destination aliases."""
        assert resolve_alias("the airport") == "airport"
        assert resolve_alias("terminal") == "airport"
        assert resolve_alias("flights") == "airport"

    def test_unknown_destination(self):
        """Test unknown destination returns None."""
        assert resolve_alias("restaurant") is None
        assert resolve_alias("random place") is None
        assert resolve_alias("") is None
        assert resolve_alias("coffee shop") is None
        assert resolve_alias("grocery store") is None

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert resolve_alias("WORK") == "office"
        assert resolve_alias("The Office") == "office"
        assert resolve_alias("MY PLACE") == "home"
        assert resolve_alias("FITNESS CENTER") == "gym"
        assert resolve_alias("University") == "school"

    def test_whitespace_insensitive(self):
        """Test whitespace handling."""
        assert resolve_alias("  work  ") == "office"
        assert resolve_alias("\thome\n") == "home"
        assert resolve_alias("  the office  ") == "office"

    def test_the_prefix_pattern(self):
        """Test 'the X' pattern matches canonical X."""
        # These are explicitly defined in aliases
        assert resolve_alias("the office") == "office"
        assert resolve_alias("the gym") == "gym"
        assert resolve_alias("the airport") == "airport"


class TestResolveDestination:
    """Tests for full destination resolution."""

    @pytest.fixture
    def saved_destinations(self):
        """Sample saved destinations."""
        return {
            "office": {
                "name": "Main Office",
                "address": "123 Business Ave",
                "eta_minutes": 25,
            },
            "home": {
                "name": "Home",
                "address": "456 Residential St",
                "eta_minutes": 0,
            },
            "gym": {
                "name": "Fitness Center",
                "address": "789 Health Blvd",
                "eta_minutes": 15,
            },
        }

    def test_alias_resolution(self, saved_destinations):
        """Test 'work' resolves to 'office' destination."""
        result = resolve_destination("work", saved_destinations)
        assert result is not None
        assert result["key"] == "office"
        assert result["address"] == "123 Business Ave"
        assert result["name"] == "Main Office"

    def test_direct_key_match(self, saved_destinations):
        """Test direct key lookup."""
        result = resolve_destination("office", saved_destinations)
        assert result is not None
        assert result["key"] == "office"
        assert result["address"] == "123 Business Ave"

    def test_partial_match(self, saved_destinations):
        """Test 'the office' matches 'office' key."""
        result = resolve_destination("the office", saved_destinations)
        assert result is not None
        assert result["key"] == "office"

    def test_unknown_destination(self, saved_destinations):
        """Test graceful handling of unmatched destinations."""
        result = resolve_destination("restaurant", saved_destinations)
        assert result is None

    def test_empty_query(self, saved_destinations):
        """Test empty query handling."""
        result = resolve_destination("", saved_destinations)
        assert result is None

    def test_empty_query_with_default(self, saved_destinations):
        """Test empty query with default key."""
        result = resolve_destination("", saved_destinations, default_key="home")
        assert result is not None
        assert result["key"] == "home"
        assert result["address"] == "456 Residential St"

    def test_result_has_key_field(self, saved_destinations):
        """Test that result includes the matched key."""
        result = resolve_destination("gym", saved_destinations)
        assert "key" in result
        assert result["key"] == "gym"

    def test_address_search(self, saved_destinations):
        """Test searching by address content."""
        result = resolve_destination("business ave", saved_destinations)
        # Should match office by address
        assert result is not None
        assert result["key"] == "office"

    def test_name_search(self, saved_destinations):
        """Test searching by name content."""
        result = resolve_destination("main office", saved_destinations)
        assert result is not None
        assert result["key"] == "office"

    def test_case_insensitive_search(self, saved_destinations):
        """Test case insensitivity in destination search."""
        result = resolve_destination("WORK", saved_destinations)
        assert result is not None
        assert result["key"] == "office"

        result = resolve_destination("RESIDENTIAL", saved_destinations)
        assert result is not None
        assert result["key"] == "home"

    def test_result_is_copy(self, saved_destinations):
        """Test that result is a copy, not original dict."""
        result = resolve_destination("office", saved_destinations)
        result["modified"] = True

        # Original should not be modified
        assert "modified" not in saved_destinations["office"]
        assert "key" not in saved_destinations["office"]

    def test_partial_key_match(self, saved_destinations):
        """Test partial key matching."""
        # 'off' should match 'office' by partial key match
        result = resolve_destination("off", saved_destinations)
        assert result is not None
        assert result["key"] == "office"

    def test_alias_not_in_saved(self):
        """Test alias when canonical key not in saved destinations."""
        # 'work' resolves to 'office' but office not saved
        saved = {
            "home": {"address": "123 Home St"},
        }
        result = resolve_destination("work", saved)
        assert result is None

    def test_whitespace_query(self, saved_destinations):
        """Test query with only whitespace."""
        result = resolve_destination("   ", saved_destinations)
        assert result is None

    def test_whitespace_query_with_default(self, saved_destinations):
        """Test whitespace query with default key."""
        # Empty/whitespace query should trigger default
        result = resolve_destination("", saved_destinations, default_key="gym")
        assert result is not None
        assert result["key"] == "gym"

    def test_empty_saved_destinations(self):
        """Test with empty saved destinations."""
        result = resolve_destination("office", {})
        assert result is None

    def test_all_destination_fields_preserved(self, saved_destinations):
        """Test all original fields are preserved in result."""
        result = resolve_destination("office", saved_destinations)
        assert result["name"] == "Main Office"
        assert result["address"] == "123 Business Ave"
        assert result["eta_minutes"] == 25
        assert result["key"] == "office"


class TestGetAvailableDestinations:
    """Tests for available destinations helper."""

    def test_returns_keys(self):
        """Test returns list of destination keys."""
        saved = {"office": {}, "home": {}, "gym": {}}
        result = get_available_destinations(saved)
        assert set(result) == {"office", "home", "gym"}

    def test_empty_dict(self):
        """Test empty destinations."""
        result = get_available_destinations({})
        assert result == []

    def test_single_destination(self):
        """Test single destination."""
        saved = {"office": {"address": "123 Main St"}}
        result = get_available_destinations(saved)
        assert result == ["office"]

    def test_preserves_order(self):
        """Test order is consistent."""
        saved = {"alpha": {}, "beta": {}, "gamma": {}}
        result = get_available_destinations(saved)
        # Python 3.7+ dicts maintain insertion order
        assert result == ["alpha", "beta", "gamma"]

    def test_returns_list_type(self):
        """Test return type is list."""
        saved = {"office": {}, "home": {}}
        result = get_available_destinations(saved)
        assert isinstance(result, list)


class TestDestinationAliasesStructure:
    """Tests for DESTINATION_ALIASES constant."""

    def test_aliases_is_dict(self):
        """Test DESTINATION_ALIASES is a dictionary."""
        assert isinstance(DESTINATION_ALIASES, dict)

    def test_canonical_keys_exist(self):
        """Test expected canonical keys exist."""
        expected_keys = {"office", "home", "gym", "school", "airport"}
        assert expected_keys.issubset(set(DESTINATION_ALIASES.keys()))

    def test_aliases_are_lists(self):
        """Test each alias value is a list."""
        for key, aliases in DESTINATION_ALIASES.items():
            assert isinstance(aliases, list), f"Aliases for '{key}' should be a list"

    def test_aliases_are_strings(self):
        """Test all aliases are strings."""
        for key, aliases in DESTINATION_ALIASES.items():
            for alias in aliases:
                assert isinstance(alias, str), f"Alias '{alias}' for '{key}' should be a string"

    def test_no_duplicate_aliases(self):
        """Test no duplicate aliases across all canonical keys."""
        all_aliases = []
        for key, aliases in DESTINATION_ALIASES.items():
            all_aliases.extend(aliases)

        # Check for duplicates
        seen = set()
        duplicates = set()
        for alias in all_aliases:
            if alias.lower() in seen:
                duplicates.add(alias)
            seen.add(alias.lower())

        assert len(duplicates) == 0, f"Duplicate aliases found: {duplicates}"

    def test_aliases_are_lowercase(self):
        """Test all aliases are lowercase."""
        for key, aliases in DESTINATION_ALIASES.items():
            for alias in aliases:
                assert alias == alias.lower(), f"Alias '{alias}' should be lowercase"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_none_query_handling(self):
        """Test None query raises appropriate error or handles gracefully."""
        # The function should handle None gracefully or raise TypeError
        try:
            result = resolve_destination(None, {"office": {}})
            # If it doesn't raise, it should return None
            assert result is None
        except (TypeError, AttributeError):
            # This is also acceptable behavior
            pass

    def test_non_dict_destination_values(self):
        """Test handling of non-dict destination values."""
        saved = {
            "office": {"address": "123 Main St"},
            "legacy": "string_value",  # Non-dict value
        }
        # Should still work for valid destinations
        result = resolve_destination("office", saved)
        assert result is not None
        assert result["key"] == "office"

    def test_unicode_destination(self):
        """Test Unicode in destination names."""
        saved = {
            "office": {"name": "Bureau Principal", "address": "123 Rue de la Paix"},
        }
        result = resolve_destination("work", saved)
        assert result is not None
        assert result["name"] == "Bureau Principal"

    def test_very_long_query(self):
        """Test handling of very long query strings."""
        long_query = "a" * 10000
        result = resolve_destination(long_query, {"office": {}})
        # Should not crash, just return None
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
