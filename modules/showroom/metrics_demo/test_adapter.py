"""Tests for the Showroom Metrics Demo adapter."""
import asyncio
import pytest
from adapter import MetricsDemoAdapter
from shared.adapters.base import AdapterConfig


def test_fetch_returns_items():
    adapter = MetricsDemoAdapter()
    config = AdapterConfig(category="showroom", platform="metrics_demo")
    raw = asyncio.get_event_loop().run_until_complete(adapter.fetch_raw(config))
    assert "items" in raw
    assert len(raw["items"]) == 3
    assert raw["module_status"] == "active"


def test_transform_extracts_items():
    adapter = MetricsDemoAdapter()
    raw = {"items": [{"metric": "test", "value": 42}]}
    result = adapter.transform(raw)
    assert len(result) == 1
    assert result[0]["value"] == 42


def test_capabilities():
    adapter = MetricsDemoAdapter()
    caps = adapter.get_capabilities()
    assert caps["read"] is True
    assert caps["write"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
