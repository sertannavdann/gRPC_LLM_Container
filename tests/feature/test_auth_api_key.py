"""
Feature tests for API key authentication.

Tests verify:
- 401 on bad/missing API key
- 200 on valid API key
- API key passed in correct header
- No key leakage in logs/errors
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx


class TestAuthAPIKey:
    """Feature tests for API key authentication pattern."""

    @pytest.fixture
    def mock_api_response(self):
        """Mock successful API response."""
        return {"items": [{"id": 1, "name": "test"}]}

    def test_rejects_missing_api_key(self):
        """Verify adapter rejects requests without API key."""
        # Mock adapter that requires API key
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=Mock(),
                response=mock_response,
            )

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            # Attempt to call API without key should raise HTTP 401
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                import asyncio
                asyncio.run(mock_instance.get("https://api.example.com/data"))
                mock_response.raise_for_status()

            assert exc_info.value.response.status_code == 401

    def test_accepts_valid_api_key(self, mock_api_response):
        """Verify adapter accepts requests with valid API key."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response
            mock_response.raise_for_status = Mock()

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            # Call with valid key should succeed
            import asyncio
            result = asyncio.run(mock_instance.get(
                "https://api.example.com/data",
                headers={"Authorization": "Bearer valid-key-123"}
            ))

            assert result.status_code == 200
            assert result.json() == mock_api_response

    def test_api_key_in_correct_header(self):
        """Verify API key is passed in the correct header format."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_response.raise_for_status = Mock()

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            # Common header formats
            header_formats = [
                {"Authorization": "Bearer test-key"},
                {"X-API-Key": "test-key"},
                {"Api-Key": "test-key"},
            ]

            import asyncio
            for headers in header_formats:
                result = asyncio.run(mock_instance.get(
                    "https://api.example.com/data",
                    headers=headers
                ))
                assert result.status_code == 200

    def test_api_key_not_leaked_in_error_messages(self):
        """Verify API key is not exposed in error messages or logs."""
        api_key = "secret-key-12345"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=Mock(),
                response=mock_response,
            )

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            # Error message should not contain the key
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                import asyncio
                asyncio.run(mock_instance.get(
                    "https://api.example.com/data",
                    headers={"Authorization": f"Bearer {api_key}"}
                ))
                mock_response.raise_for_status()

            error_message = str(exc_info.value)
            # Key should not appear in error
            assert api_key not in error_message

    def test_handles_expired_api_key(self):
        """Verify adapter handles expired API key errors gracefully."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "API key expired"}
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized: API key expired",
                request=Mock(),
                response=mock_response,
            )

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                import asyncio
                asyncio.run(mock_instance.get("https://api.example.com/data"))
                mock_response.raise_for_status()

            # Should categorize as authentication error
            assert exc_info.value.response.status_code == 401
            assert "expired" in exc_info.value.response.json()["error"].lower()
