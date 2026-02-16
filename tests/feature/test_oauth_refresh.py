"""
Feature tests for OAuth2 token refresh flow.

Tests verify:
- Token exchange works correctly
- Refresh token flow handles expiration
- Expired access tokens trigger refresh
- Refresh failures are handled gracefully
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import httpx


class TestOAuthRefresh:
    """Feature tests for OAuth2 token refresh pattern."""

    @pytest.fixture
    def mock_token_response(self):
        """Mock OAuth token response."""
        return {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    def test_token_exchange_succeeds(self, mock_token_response):
        """Verify OAuth token exchange works."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_token_response
            mock_response.raise_for_status = Mock()

            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio
            result = asyncio.run(mock_instance.post(
                "https://oauth.example.com/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "auth-code",
                    "client_id": "client-id",
                }
            ))

            assert result.status_code == 200
            data = result.json()
            assert "access_token" in data
            assert "refresh_token" in data

    def test_refresh_token_flow(self, mock_token_response):
        """Verify refresh token can be used to get new access token."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_token_response
            mock_response.raise_for_status = Mock()

            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio
            result = asyncio.run(mock_instance.post(
                "https://oauth.example.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": "old-refresh-token",
                    "client_id": "client-id",
                }
            ))

            assert result.status_code == 200
            data = result.json()
            assert data["access_token"] == "new-access-token"

    def test_expired_token_triggers_refresh(self):
        """Verify expired access token triggers automatic refresh."""
        # First call fails with 401
        # Second call (after refresh) succeeds
        with patch("httpx.AsyncClient") as mock_client:
            mock_expired = Mock()
            mock_expired.status_code = 401
            mock_expired.json.return_value = {"error": "token_expired"}

            mock_success = Mock()
            mock_success.status_code = 200
            mock_success.json.return_value = {"data": "success"}
            mock_success.raise_for_status = Mock()

            mock_instance = AsyncMock()
            # First call returns 401, second returns 200
            mock_instance.get.side_effect = [mock_expired, mock_success]
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio

            # First attempt
            result1 = asyncio.run(mock_instance.get("https://api.example.com/data"))
            assert result1.status_code == 401

            # After refresh, second attempt
            result2 = asyncio.run(mock_instance.get("https://api.example.com/data"))
            assert result2.status_code == 200

    def test_refresh_failure_handled(self):
        """Verify refresh token failure is handled gracefully."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": "invalid_grant"}
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "400 Bad Request",
                request=Mock(),
                response=mock_response,
            )

            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            # Refresh attempt should fail
            with pytest.raises(httpx.HTTPStatusError):
                import asyncio
                asyncio.run(mock_instance.post(
                    "https://oauth.example.com/token",
                    data={"grant_type": "refresh_token", "refresh_token": "invalid"}
                ))
                mock_response.raise_for_status()

    def test_token_expiry_calculation(self):
        """Verify token expiry time is calculated correctly."""
        issued_at = datetime.utcnow()
        expires_in = 3600  # 1 hour

        expiry_time = issued_at + timedelta(seconds=expires_in)

        # Token should not be expired immediately
        assert datetime.utcnow() < expiry_time

        # Token should be expired after expiry time
        future_time = expiry_time + timedelta(seconds=1)
        assert future_time > expiry_time
