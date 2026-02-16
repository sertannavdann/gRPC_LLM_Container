from tools.builtin.context_bridge import _normalize_context_for_tools


def test_normalize_navigation_handles_none_destination_name():
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

    result = _normalize_context_for_tools(payload)

    assert "navigation" in result
    assert "unknown" in result["navigation"]["saved_destinations"]
    assert result["navigation"]["saved_destinations"]["unknown"]["name"] == "Unknown"
