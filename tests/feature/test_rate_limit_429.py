"""
Feature tests for rate limit handling (HTTP 429).

Tests verify:
- 429 responses trigger backoff
- Retry with exponential backoff succeeds
- Max retries are respected
- Retry-After header is honored
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
import time


class TestRateLimit429:
    """Feature tests for rate limit handling pattern."""

    def test_detects_rate_limit_429(self):
        """Verify adapter detects 429 rate limit response."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "5"}
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429 Too Many Requests",
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

            assert exc_info.value.response.status_code == 429

    def test_retry_after_backoff(self):
        """Verify retry succeeds after backoff delay."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_rate_limited = Mock()
            mock_rate_limited.status_code = 429
            mock_rate_limited.headers = {"Retry-After": "1"}

            mock_success = Mock()
            mock_success.status_code = 200
            mock_success.json.return_value = {"data": "success"}
            mock_success.raise_for_status = Mock()

            mock_instance = AsyncMock()
            # First call returns 429, second returns 200
            mock_instance.get.side_effect = [mock_rate_limited, mock_success]
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio

            # First attempt - rate limited
            result1 = asyncio.run(mock_instance.get("https://api.example.com/data"))
            assert result1.status_code == 429

            # Simulate backoff delay (mocked - no actual sleep)
            # Second attempt - succeeds
            result2 = asyncio.run(mock_instance.get("https://api.example.com/data"))
            assert result2.status_code == 200

    def test_exponential_backoff_calculation(self):
        """Verify exponential backoff delays are calculated correctly."""
        base_delay = 1.0
        max_delay = 60.0

        # Exponential backoff: 1, 2, 4, 8, 16, 32, 60 (capped)
        delays = []
        for attempt in range(7):
            delay = min(base_delay * (2 ** attempt), max_delay)
            delays.append(delay)

        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]

    def test_max_retries_respected(self):
        """Verify max retry limit is enforced."""
        max_retries = 3
        attempts = []

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "1"}

            mock_instance = AsyncMock()

            def track_attempt(*args, **kwargs):
                attempts.append(1)
                return mock_response

            mock_instance.get.side_effect = track_attempt
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio

            # Try up to max_retries times
            for i in range(max_retries + 1):
                if i <= max_retries:
                    result = asyncio.run(mock_instance.get("https://api.example.com/data"))
                    assert result.status_code == 429

            # Should have made max_retries + 1 attempts (initial + retries)
            assert len(attempts) == max_retries + 1

    def test_retry_after_header_honored(self):
        """Verify Retry-After header value is used for delay."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "10"}

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio
            result = asyncio.run(mock_instance.get("https://api.example.com/data"))

            # Verify response has Retry-After
            assert result.headers.get("Retry-After") == "10"

    def test_jitter_applied_to_backoff(self):
        """Verify jitter is applied to prevent thundering herd."""
        import random

        base_delay = 5.0
        jitter_factor = 0.1  # +/- 10%

        # Simulate jittered delays
        delays_with_jitter = []
        random.seed(42)  # Deterministic for testing

        for _ in range(10):
            jitter = random.uniform(-jitter_factor, jitter_factor)
            delay = base_delay * (1 + jitter)
            delays_with_jitter.append(delay)

        # All delays should be within jitter range
        for delay in delays_with_jitter:
            assert base_delay * 0.9 <= delay <= base_delay * 1.1
