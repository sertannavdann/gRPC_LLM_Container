"""
Observability Stack - OpenTelemetry + Prometheus + Structured Logging

This module provides unified observability for the gRPC LLM framework:
- Metrics: Prometheus-compatible metrics via OpenTelemetry
- Tracing: Distributed tracing with correlation IDs
- Logging: Structured logging with automatic context propagation

Usage:
    from shared.observability import setup_observability, get_meter, get_tracer, get_logger

    # Initialize once at service startup
    setup_observability(service_name="orchestrator")

    # Get instrumentation objects
    meter = get_meter()
    tracer = get_tracer()
    logger = get_logger(__name__)
"""
from .setup import setup_observability, shutdown_observability
from .metrics import (
    get_meter,
    create_request_metrics,
    create_tool_metrics,
    create_provider_metrics,
    RequestMetrics,
    ToolMetrics,
    ProviderMetrics,
    increment_active_requests,
    decrement_active_requests,
    time_operation,
)
from .tracing import (
    get_tracer,
    create_span,
    inject_context,
    extract_context,
    get_correlation_id,
    set_correlation_id,
)
from .logging_config import (
    get_logger,
    configure_logging,
    bind_context,
)

__all__ = [
    # Setup
    "setup_observability",
    "shutdown_observability",
    # Metrics
    "get_meter",
    "create_request_metrics",
    "create_tool_metrics",
    "create_provider_metrics",
    "RequestMetrics",
    "ToolMetrics",
    "ProviderMetrics",
    "increment_active_requests",
    "decrement_active_requests",
    "time_operation",
    # Tracing
    "get_tracer",
    "create_span",
    "inject_context",
    "extract_context",
    "get_correlation_id",
    "set_correlation_id",
    # Logging
    "get_logger",
    "configure_logging",
    "bind_context",
]
