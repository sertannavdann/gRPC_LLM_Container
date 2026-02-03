"""
Custom Metrics - Tool calls, provider usage, costs, and latency tracking.

Provides pre-configured metrics for the gRPC LLM framework:
- Request latency histograms
- Tool call counters and duration
- Provider usage and cost tracking
- Error rate counters
"""
from dataclasses import dataclass
from typing import Dict, Optional, Callable, List
import time

from opentelemetry import metrics
from opentelemetry.metrics import Meter, Counter, Histogram, ObservableGauge

# Module-level meter cache
_meter: Optional[Meter] = None


def get_meter(name: str = "grpc_llm") -> Meter:
    """Get or create the meter for this application."""
    global _meter
    if _meter is None:
        _meter = metrics.get_meter(name, version="1.0.0")
    return _meter


@dataclass
class RequestMetrics:
    """Metrics for gRPC request handling."""

    # Request count by method and status
    requests_total: Counter

    # Request duration histogram
    request_duration_ms: Histogram

    # Active requests gauge
    active_requests: ObservableGauge

    # Error count by type
    errors_total: Counter


@dataclass
class ToolMetrics:
    """Metrics for tool execution."""

    # Tool call count by tool name
    tool_calls_total: Counter

    # Tool execution duration
    tool_duration_ms: Histogram

    # Tool success/failure rate
    tool_errors_total: Counter

    # Tools per request histogram
    tools_per_request: Histogram


@dataclass
class ProviderMetrics:
    """Metrics for LLM provider usage."""

    # Requests by provider
    provider_requests_total: Counter

    # Provider latency
    provider_latency_ms: Histogram

    # Token usage by provider
    tokens_total: Counter

    # Estimated cost (observable gauge updated periodically)
    estimated_cost_usd: ObservableGauge

    # Provider errors
    provider_errors_total: Counter


# Shared state for observable gauges
_active_requests: int = 0
_cumulative_costs: Dict[str, float] = {}


def _get_active_requests() -> int:
    """Callback for active requests gauge."""
    return _active_requests


def _get_cumulative_costs() -> List[metrics.Observation]:
    """Callback for cost gauge."""
    observations = []
    for provider, cost in _cumulative_costs.items():
        observations.append(
            metrics.Observation(cost, {"provider": provider})
        )
    return observations


def create_request_metrics(meter: Optional[Meter] = None) -> RequestMetrics:
    """
    Create metrics for request handling.

    Returns:
        RequestMetrics dataclass with configured metric instruments
    """
    m = meter or get_meter()

    requests_total = m.create_counter(
        name="grpc_requests_total",
        description="Total number of gRPC requests",
        unit="1",
    )

    request_duration_ms = m.create_histogram(
        name="grpc_request_duration_ms",
        description="Request duration in milliseconds",
        unit="ms",
    )

    active_requests = m.create_observable_gauge(
        name="grpc_active_requests",
        description="Number of currently active requests",
        unit="1",
        callbacks=[lambda options: [metrics.Observation(_active_requests)]],
    )

    errors_total = m.create_counter(
        name="grpc_errors_total",
        description="Total number of errors",
        unit="1",
    )

    return RequestMetrics(
        requests_total=requests_total,
        request_duration_ms=request_duration_ms,
        active_requests=active_requests,
        errors_total=errors_total,
    )


def create_tool_metrics(meter: Optional[Meter] = None) -> ToolMetrics:
    """
    Create metrics for tool execution tracking.

    Returns:
        ToolMetrics dataclass with configured metric instruments
    """
    m = meter or get_meter()

    tool_calls_total = m.create_counter(
        name="tool_calls_total",
        description="Total number of tool calls",
        unit="1",
    )

    tool_duration_ms = m.create_histogram(
        name="tool_duration_ms",
        description="Tool execution duration in milliseconds",
        unit="ms",
    )

    tool_errors_total = m.create_counter(
        name="tool_errors_total",
        description="Total number of tool execution errors",
        unit="1",
    )

    tools_per_request = m.create_histogram(
        name="tools_per_request",
        description="Number of tools called per request",
        unit="1",
    )

    return ToolMetrics(
        tool_calls_total=tool_calls_total,
        tool_duration_ms=tool_duration_ms,
        tool_errors_total=tool_errors_total,
        tools_per_request=tools_per_request,
    )


def create_provider_metrics(meter: Optional[Meter] = None) -> ProviderMetrics:
    """
    Create metrics for LLM provider tracking.

    Returns:
        ProviderMetrics dataclass with configured metric instruments
    """
    m = meter or get_meter()

    provider_requests_total = m.create_counter(
        name="llm_provider_requests_total",
        description="Total requests by LLM provider",
        unit="1",
    )

    provider_latency_ms = m.create_histogram(
        name="llm_provider_latency_ms",
        description="LLM provider response latency in milliseconds",
        unit="ms",
    )

    tokens_total = m.create_counter(
        name="llm_tokens_total",
        description="Total tokens processed",
        unit="1",
    )

    estimated_cost_usd = m.create_observable_gauge(
        name="llm_estimated_cost_usd",
        description="Cumulative estimated cost in USD",
        unit="USD",
        callbacks=[lambda options: _get_cumulative_costs()],
    )

    provider_errors_total = m.create_counter(
        name="llm_provider_errors_total",
        description="Total provider errors",
        unit="1",
    )

    return ProviderMetrics(
        provider_requests_total=provider_requests_total,
        provider_latency_ms=provider_latency_ms,
        tokens_total=tokens_total,
        estimated_cost_usd=estimated_cost_usd,
        provider_errors_total=provider_errors_total,
    )


# Convenience functions for updating metrics

def increment_active_requests() -> None:
    """Increment active request counter."""
    global _active_requests
    _active_requests += 1


def decrement_active_requests() -> None:
    """Decrement active request counter."""
    global _active_requests
    _active_requests = max(0, _active_requests - 1)


def add_provider_cost(provider: str, cost_usd: float) -> None:
    """Add to cumulative provider cost."""
    global _cumulative_costs
    _cumulative_costs[provider] = _cumulative_costs.get(provider, 0) + cost_usd


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, histogram: Histogram, attributes: Optional[Dict] = None):
        self.histogram = histogram
        self.attributes = attributes or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.histogram.record(duration_ms, self.attributes)
        return False


def time_operation(histogram: Histogram, **attributes) -> TimerContext:
    """
    Create a context manager for timing an operation.

    Usage:
        with time_operation(metrics.request_duration_ms, method="QueryAgent"):
            # ... operation ...
    """
    return TimerContext(histogram, attributes)
