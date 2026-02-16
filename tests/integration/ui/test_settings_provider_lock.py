"""
Integration tests for provider lock metadata and connection test API.

Tests settings API endpoints for provider lock/unlock functionality:
- GET /api/settings includes providerLocks for all providers
- Lock metadata structure validation
- Provider lock state based on env configuration
- POST /api/settings/connection-test returns standardized output
- Invalid provider input handling
"""

import pytest
import requests


# UI service base URL
UI_SERVICE_URL = "http://localhost:5001"


@pytest.fixture
def ui_available():
    """Check if UI service is reachable."""
    try:
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=5)
        return response.status_code in [200, 500]
    except requests.RequestException:
        pytest.skip("UI service not reachable - skipping integration tests")


class TestProviderLockMetadata:
    """Tests for GET /api/settings provider lock metadata."""

    def test_get_settings_includes_provider_locks(self, ui_available):
        """Test that GET /api/settings includes providerLocks field."""
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert "providerLocks" in data, "Response missing providerLocks field"
        assert isinstance(data["providerLocks"], dict), "providerLocks should be a dictionary"

    def test_provider_lock_structure(self, ui_available):
        """Test that each provider lock entry has required fields."""
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)
        data = response.json()

        provider_locks = data.get("providerLocks", {})
        assert len(provider_locks) > 0, "providerLocks should not be empty"

        for provider_name, lock_status in provider_locks.items():
            assert "locked" in lock_status, f"Provider {provider_name} missing 'locked' field"
            assert "missingRequirements" in lock_status, f"Provider {provider_name} missing 'missingRequirements' field"
            assert "canTest" in lock_status, f"Provider {provider_name} missing 'canTest' field"

            assert isinstance(lock_status["locked"], bool), f"Provider {provider_name} 'locked' should be boolean"
            assert isinstance(lock_status["missingRequirements"], list), f"Provider {provider_name} 'missingRequirements' should be list"
            assert isinstance(lock_status["canTest"], bool), f"Provider {provider_name} 'canTest' should be boolean"

    def test_local_provider_always_unlocked(self, ui_available):
        """Test that local provider is never locked."""
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)
        data = response.json()

        provider_locks = data.get("providerLocks", {})
        assert "local" in provider_locks, "Local provider should be in providerLocks"

        local_lock = provider_locks["local"]
        assert local_lock["locked"] is False, "Local provider should never be locked"
        assert len(local_lock["missingRequirements"]) == 0, "Local provider should have no missing requirements"

    def test_cloud_provider_lock_based_on_requirements(self, ui_available):
        """Test that cloud providers are locked when missing required credentials."""
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)
        data = response.json()

        provider_locks = data.get("providerLocks", {})

        # Check that cloud providers exist in locks
        cloud_providers = ["nvidia", "openai", "anthropic", "perplexity"]
        for provider in cloud_providers:
            if provider in provider_locks:
                lock_status = provider_locks[provider]
                # If locked, should have missing requirements
                if lock_status["locked"]:
                    assert len(lock_status["missingRequirements"]) > 0, \
                        f"Locked provider {provider} should have missing requirements"
                # If not locked, should have no missing requirements
                else:
                    assert len(lock_status["missingRequirements"]) == 0, \
                        f"Unlocked provider {provider} should have no missing requirements"


class TestConnectionTestAPI:
    """Tests for POST /api/settings/connection-test endpoint."""

    def test_connection_test_requires_provider(self, ui_available):
        """Test that connection-test endpoint requires provider parameter."""
        response = requests.post(
            f"{UI_SERVICE_URL}/api/settings/connection-test",
            json={},
            timeout=10
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "message" in data or "error" in data, "Error response should have message or error field"

    def test_connection_test_invalid_provider(self, ui_available):
        """Test that connection-test rejects invalid provider names."""
        response = requests.post(
            f"{UI_SERVICE_URL}/api/settings/connection-test",
            json={"provider": "invalid_provider_xyz"},
            timeout=10
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert data.get("success") is False, "Invalid provider should return success=false"
        assert "message" in data, "Error response should include message"

    def test_connection_test_standardized_response_shape(self, ui_available):
        """Test that connection-test returns standardized output structure."""
        # Test with a known provider (nvidia will fail without key, but structure should be valid)
        response = requests.post(
            f"{UI_SERVICE_URL}/api/settings/connection-test",
            json={"provider": "nvidia"},
            timeout=20
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()

        # Validate standardized structure
        assert "success" in data, "Response missing 'success' field"
        assert "message" in data, "Response missing 'message' field"
        assert isinstance(data["success"], bool), "'success' should be boolean"
        assert isinstance(data["message"], str), "'message' should be string"

        # Optional details field
        if "details" in data:
            assert isinstance(data["details"], dict), "'details' should be dictionary"

    def test_connection_test_locked_provider_returns_error(self, ui_available):
        """Test that connection test for locked provider returns actionable error."""
        # First check if nvidia is locked
        settings_response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)
        provider_locks = settings_response.json().get("providerLocks", {})

        if "nvidia" in provider_locks and provider_locks["nvidia"]["locked"]:
            # Test connection for locked provider
            response = requests.post(
                f"{UI_SERVICE_URL}/api/settings/connection-test",
                json={"provider": "nvidia"},
                timeout=20
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data.get("success") is False, "Locked provider test should return success=false"
            assert "message" in data, "Error should include message"
            assert len(data["message"]) > 0, "Error message should not be empty"

    def test_connection_test_local_provider_success(self, ui_available):
        """Test that local provider connection test always succeeds."""
        response = requests.post(
            f"{UI_SERVICE_URL}/api/settings/connection-test",
            json={"provider": "local"},
            timeout=20
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") is True, "Local provider test should always succeed"
        assert "message" in data, "Success should include message"


class TestLockUnlockFlow:
    """Tests for complete lock/unlock workflow."""

    def test_all_providers_have_lock_metadata(self, ui_available):
        """Test that all providers in catalog have corresponding lock metadata."""
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)
        data = response.json()

        providers = data.get("providers", {})
        provider_locks = data.get("providerLocks", {})

        for provider_name in providers.keys():
            assert provider_name in provider_locks, \
                f"Provider {provider_name} missing from providerLocks"

    def test_lock_metadata_matches_env_state(self, ui_available):
        """Test that lock state reflects actual environment configuration."""
        response = requests.get(f"{UI_SERVICE_URL}/api/settings", timeout=10)
        data = response.json()

        config = data.get("config", {})
        provider_locks = data.get("providerLocks", {})

        # Nvidia should be locked if no NIM_API_KEY
        if "nvidia" in provider_locks:
            nvidia_lock = provider_locks["nvidia"]
            has_nim_key = config.get("hasNimKey", False)

            if not has_nim_key:
                # Missing key should result in locked state or NIM_API_KEY in missing requirements
                if nvidia_lock["locked"]:
                    assert "NIM_API_KEY" in nvidia_lock["missingRequirements"], \
                        "Locked nvidia provider should list NIM_API_KEY in missing requirements"

    def test_connection_test_non_500_for_all_known_providers(self, ui_available):
        """Test that connection-test returns non-500 status for all valid providers."""
        known_providers = ["local", "nvidia", "openai", "anthropic", "perplexity"]

        for provider in known_providers:
            response = requests.post(
                f"{UI_SERVICE_URL}/api/settings/connection-test",
                json={"provider": provider},
                timeout=20
            )

            # Should never return 500 for valid providers
            assert response.status_code != 500, \
                f"Provider {provider} connection test returned 500 (internal server error)"
            assert response.status_code in [200, 400], \
                f"Provider {provider} returned unexpected status {response.status_code}"
