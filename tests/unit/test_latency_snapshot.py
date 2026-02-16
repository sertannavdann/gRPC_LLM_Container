"""Unit tests for latency snapshot computation and serialization."""
import json
import os

import pytest

from shared.billing.latency_snapshot import (
    LatencySnapshot,
    compute_percentiles,
    record_latencies,
    write_snapshot,
)


class TestComputePercentiles:
    def test_known_data(self):
        result = compute_percentiles([10, 20, 30, 40, 50])
        assert result["p50_ms"] == 30.0

    def test_single_value(self):
        result = compute_percentiles([100])
        assert result["p50_ms"] == 100.0
        assert result["p95_ms"] == 100.0
        assert result["p99_ms"] == 100.0

    def test_empty_list(self):
        result = compute_percentiles([])
        assert result["p50_ms"] == 0.0
        assert result["p95_ms"] == 0.0
        assert result["p99_ms"] == 0.0

    def test_two_values(self):
        result = compute_percentiles([10, 20])
        assert result["p50_ms"] == 15.0

    def test_large_dataset(self):
        data = list(range(1, 101))  # 1..100
        result = compute_percentiles(data)
        assert result["p50_ms"] == 50.5
        assert result["p95_ms"] >= 95.0
        assert result["p99_ms"] >= 99.0

    def test_unsorted_input(self):
        result = compute_percentiles([50, 10, 30, 20, 40])
        assert result["p50_ms"] == 30.0


class TestRecordLatencies:
    def test_multiple_endpoints(self):
        raw = {
            "/health": [10, 20, 30],
            "/admin/modules": [50, 100, 150],
        }
        result = record_latencies(raw)
        assert "/health" in result
        assert "/admin/modules" in result
        assert "p50_ms" in result["/health"]
        assert result["/admin/modules"]["p50_ms"] == 100.0

    def test_empty_endpoints(self):
        result = record_latencies({})
        assert result == {}


class TestWriteSnapshot:
    def test_creates_json_file(self, tmp_path):
        snapshot = LatencySnapshot(
            timestamp="2026-02-16T00:00:00Z",
            orchestrator_version="abc123",
            endpoints={"/health": {"p50_ms": 10, "p95_ms": 20, "p99_ms": 30}},
            total_tests=5,
            passed=5,
            failed=0,
            duration_s=12.5,
        )
        path = str(tmp_path / "snapshot.json")
        write_snapshot(snapshot, path)

        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data["timestamp"] == "2026-02-16T00:00:00Z"
        assert data["orchestrator_version"] == "abc123"
        assert "/health" in data["endpoints"]
        assert data["total_tests"] == 5
        assert data["duration_s"] == 12.5

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "nested" / "deep" / "snapshot.json")
        snapshot = LatencySnapshot(
            timestamp="now",
            orchestrator_version="test",
            endpoints={},
        )
        write_snapshot(snapshot, path)
        assert os.path.exists(path)
