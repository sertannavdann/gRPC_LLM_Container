"""Tests for the Hello World test adapter."""
import asyncio
import pytest


def test_hello_adapter_loads():
    """Verify the adapter can be imported and instantiated."""
    from adapter import HelloAdapter
    adapter = HelloAdapter()
    assert adapter.category == "test"
    assert adapter.platform == "hello"


def test_hello_adapter_capabilities():
    """Verify capabilities are correctly reported."""
    from adapter import HelloAdapter
    adapter = HelloAdapter()
    caps = adapter.get_capabilities()
    assert caps["read"] is True
    assert caps["write"] is False


def test_hello_adapter_fetch():
    """Verify fetch_raw returns expected structure."""
    from adapter import HelloAdapter
    adapter = HelloAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        adapter.fetch_raw(adapter.config)
    )
    assert "items" in result
    assert len(result["items"]) > 0
    assert result["items"][0]["status"] == "ok"


def test_hello_adapter_transform():
    """Verify transform extracts items correctly."""
    from adapter import HelloAdapter
    adapter = HelloAdapter()
    raw = {"items": [{"message": "test", "status": "ok"}]}
    result = adapter.transform(raw)
    assert len(result) == 1
    assert result[0]["message"] == "test"
