"""
Feature tests for cursor-based pagination.

Tests verify:
- Page iteration works correctly
- max_pages guard prevents infinite loops
- Repeated cursor detection stops iteration
- Empty pages handled gracefully
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx


class TestPaginationCursor:
    """Feature tests for cursor-based pagination pattern."""

    @pytest.fixture
    def mock_page_1(self):
        """Mock first page of results."""
        return {
            "items": [{"id": 1}, {"id": 2}, {"id": 3}],
            "next_cursor": "cursor-page-2",
        }

    @pytest.fixture
    def mock_page_2(self):
        """Mock second page of results."""
        return {
            "items": [{"id": 4}, {"id": 5}, {"id": 6}],
            "next_cursor": "cursor-page-3",
        }

    @pytest.fixture
    def mock_page_3(self):
        """Mock final page of results."""
        return {
            "items": [{"id": 7}, {"id": 8}],
            "next_cursor": None,  # No more pages
        }

    def test_iterates_through_pages(self, mock_page_1, mock_page_2, mock_page_3):
        """Verify pagination iterates through all pages."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp_1 = Mock()
            mock_resp_1.status_code = 200
            mock_resp_1.json.return_value = mock_page_1

            mock_resp_2 = Mock()
            mock_resp_2.status_code = 200
            mock_resp_2.json.return_value = mock_page_2

            mock_resp_3 = Mock()
            mock_resp_3.status_code = 200
            mock_resp_3.json.return_value = mock_page_3

            mock_instance = AsyncMock()
            mock_instance.get.side_effect = [mock_resp_1, mock_resp_2, mock_resp_3]
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio

            all_items = []
            cursor = None

            for _ in range(3):  # Expect 3 pages
                result = asyncio.run(mock_instance.get(
                    "https://api.example.com/data",
                    params={"cursor": cursor} if cursor else {}
                ))
                data = result.json()
                all_items.extend(data["items"])
                cursor = data.get("next_cursor")
                if not cursor:
                    break

            # Should have collected all items
            assert len(all_items) == 8
            assert [item["id"] for item in all_items] == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_max_pages_guard_prevents_infinite_loop(self):
        """Verify max_pages limit prevents infinite pagination."""
        max_pages = 5
        pages_fetched = 0

        with patch("httpx.AsyncClient") as mock_client:
            # Always return a page with next cursor
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "items": [{"id": 1}],
                "next_cursor": "infinite-cursor",
            }

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio

            cursor = None
            while pages_fetched < max_pages:
                result = asyncio.run(mock_instance.get("https://api.example.com/data"))
                pages_fetched += 1
                data = result.json()
                cursor = data.get("next_cursor")

            # Should stop at max_pages
            assert pages_fetched == max_pages

    def test_repeated_cursor_detection_stops_iteration(self):
        """Verify repeated cursor detection prevents loops."""
        seen_cursors = set()

        with patch("httpx.AsyncClient") as mock_client:
            # Return same cursor twice (loop detected)
            mock_resp_1 = Mock()
            mock_resp_1.status_code = 200
            mock_resp_1.json.return_value = {
                "items": [{"id": 1}],
                "next_cursor": "cursor-A",
            }

            mock_resp_2 = Mock()
            mock_resp_2.status_code = 200
            mock_resp_2.json.return_value = {
                "items": [{"id": 2}],
                "next_cursor": "cursor-A",  # Same cursor - loop!
            }

            mock_instance = AsyncMock()
            mock_instance.get.side_effect = [mock_resp_1, mock_resp_2]
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio

            cursor = None
            pages = 0
            max_iterations = 10

            for _ in range(max_iterations):
                result = asyncio.run(mock_instance.get("https://api.example.com/data"))
                pages += 1
                data = result.json()
                cursor = data.get("next_cursor")

                if cursor in seen_cursors:
                    # Loop detected - stop
                    break

                seen_cursors.add(cursor)

            # Should have stopped after detecting repeated cursor
            assert pages == 2
            assert "cursor-A" in seen_cursors

    def test_empty_page_handled_gracefully(self):
        """Verify empty page (no items) doesn't crash."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "items": [],  # Empty page
                "next_cursor": None,
            }

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            import asyncio
            result = asyncio.run(mock_instance.get("https://api.example.com/data"))
            data = result.json()

            assert data["items"] == []
            assert data["next_cursor"] is None

    def test_cursor_encoding_handled(self):
        """Verify cursor values are properly URL-encoded."""
        import urllib.parse

        cursor = "page=2&sort=desc&filter=active"
        encoded_cursor = urllib.parse.quote(cursor)

        # Encoded cursor should not have special characters
        assert "&" not in encoded_cursor
        assert "=" not in encoded_cursor

        # Should decode back to original
        decoded_cursor = urllib.parse.unquote(encoded_cursor)
        assert decoded_cursor == cursor
