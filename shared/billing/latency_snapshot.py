"""
Latency Snapshot — Percentile calculator and JSON snapshot writer.

Records p50/p95/p99 latency for key endpoints and persists
as a structured JSON artifact for release verification.
"""
import json
import math
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass
class LatencySnapshot:
    """Structured latency snapshot for verification artifacts."""

    timestamp: str
    orchestrator_version: str
    endpoints: dict[str, dict[str, float]]
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    duration_s: float = 0.0


def compute_percentiles(latencies: list[float]) -> dict[str, float]:
    """Compute p50/p95/p99 using sorted-index method (no numpy)."""
    if not latencies:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}

    sorted_lat = sorted(latencies)
    n = len(sorted_lat)

    def _percentile(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lower = int(math.floor(idx))
        upper = min(lower + 1, n - 1)
        frac = idx - lower
        return sorted_lat[lower] * (1 - frac) + sorted_lat[upper] * frac

    return {
        "p50_ms": round(_percentile(50), 2),
        "p95_ms": round(_percentile(95), 2),
        "p99_ms": round(_percentile(99), 2),
    }


def record_latencies(
    endpoints: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """Compute percentiles for each endpoint's latency samples."""
    return {name: compute_percentiles(lats) for name, lats in endpoints.items()}


def write_snapshot(
    snapshot: LatencySnapshot, path: str = "data/verify_snapshot.json"
) -> None:
    """Write latency snapshot as JSON artifact."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(asdict(snapshot), f, indent=2)


def probe_endpoints(
    base_url: str,
    endpoints: list[str],
    samples: int = 5,
    timeout: float = 10.0,
) -> dict[str, list[float]]:
    """HTTP GET each endpoint N times, collect latencies in ms."""
    api_key = os.environ.get("API_KEY", "")
    results: dict[str, list[float]] = {}

    for ep in endpoints:
        latencies: list[float] = []
        url = f"{base_url.rstrip('/')}{ep}"
        for _ in range(samples):
            req = Request(url)
            if api_key:
                req.add_header("X-API-Key", api_key)
            try:
                start = time.monotonic()
                with urlopen(req, timeout=timeout):
                    pass
                elapsed_ms = (time.monotonic() - start) * 1000
                latencies.append(round(elapsed_ms, 2))
            except (URLError, OSError):
                pass
        results[ep] = latencies

    return results


def _get_git_version() -> str:
    """Get short git hash for snapshot versioning."""
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


DEFAULT_ENDPOINTS = [
    "/admin/health",
    "/admin/modules",
    "/admin/routing-config",
    "/health",
]


if __name__ == "__main__":
    import sys

    base = os.environ.get("VERIFY_BASE_URL", "http://localhost:8003")
    print(f"Probing {base} ({len(DEFAULT_ENDPOINTS)} endpoints, 5 samples each)...")

    raw = probe_endpoints(base, DEFAULT_ENDPOINTS)
    percentiles = record_latencies(raw)

    snapshot = LatencySnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        orchestrator_version=_get_git_version(),
        endpoints=percentiles,
    )

    out_path = os.environ.get("SNAPSHOT_PATH", "data/verify_snapshot.json")
    write_snapshot(snapshot, out_path)
    print(f"Snapshot written to {out_path}")

    for ep, pcts in percentiles.items():
        print(f"  {ep}: p50={pcts['p50_ms']}ms  p95={pcts['p95_ms']}ms  p99={pcts['p99_ms']}ms")
