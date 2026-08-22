"""Unit tests for tools.builtin.context_bridge.ContextBridge.normalize().

Updated after the Phase 5 (05-05) refactor replaced the module-level
_normalize_context_for_tools() switch with ContextBridge.normalize(), which
delegates per-category normalization to each adapter's
normalize_category_for_tools() and passes through categories without a real
adapter (health, navigation) as {"status": "no adapter configured", "raw": ...}.
"""
from tools.builtin.context_bridge import ContextBridge


def test_normalize_navigation_handles_none_destination_name():
    """A navigation payload with a None destination name must not crash normalize()."""
    payload = {
        "navigation": {
            "routes": [
                {
                    "destination": {"name": None, "address": "123 Main St"},
                    "duration_minutes": 12,
                }
            ]
        }
    }

    result = ContextBridge().normalize(payload)

    # Navigation has no dedicated adapter: passthrough with status marker
    assert "navigation" in result
    assert result["navigation"]["status"] == "no adapter configured"
    assert result["navigation"]["raw"] == payload["navigation"]


def test_normalize_skips_empty_categories():
    """Empty category payloads are dropped from the normalized result."""
    result = ContextBridge().normalize({"navigation": {}, "health": None})
    assert result == {}
