"""
Observability Setup - Initialize OpenTelemetry, Prometheus, and Logging

This module configures the observability stack for the service.
Call setup_observability() once at service startup.
"""
import os
import logging
from typing import Optional

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader

# gRPC instrumentation
from opentelemetry.instrumentation.grpc import (
    GrpcInstrumentorServer,
    GrpcInstrumentorClient,
)

logger = logging.getLogger(__name__)

# Global state
_initialized = False
_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None


def setup_observability(
    service_name: str,
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
    enable_prometheus: bool = True,
    prometheus_port: int = 8888,
    enable_grpc_instrumentation: bool = True,
) -> None:
    """
    Initialize the observability stack.

    Args:
        service_name: Name of the service (e.g., "orchestrator", "llm_service")
        service_version: Version string for the service
        otlp_endpoint: OTLP collector endpoint (default: from env or localhost:4317)
        enable_prometheus: Whether to expose Prometheus metrics endpoint
        prometheus_port: Port for Prometheus metrics (default: 8888)
        enable_grpc_instrumentation: Whether to auto-instrument gRPC calls
    """
    global _initialized, _tracer_provider, _meter_provider

    if _initialized:
        logger.warning("Observability already initialized, skipping")
        return

    # Get configuration from environment
    otlp_endpoint = otlp_endpoint or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )

    # Create resource describing this service
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    # Setup tracing
    _setup_tracing(resource, otlp_endpoint)

    # Setup metrics
    _setup_metrics(resource, otlp_endpoint, enable_prometheus, prometheus_port)

    # Auto-instrument gRPC
    if enable_grpc_instrumentation:
        _setup_grpc_instrumentation()

    # Configure structured logging
    from .logging_config import configure_logging
    configure_logging(service_name)

    # Suppress noisy OTel SDK internal errors (KeyError in BatchSpanProcessor)
    otel_internal_logger = logging.getLogger("opentelemetry.sdk._shared_internal")
    otel_internal_logger.setLevel(logging.CRITICAL)

    _initialized = True
    logger.info(
        f"Observability initialized for {service_name}",
        extra={
            "service": service_name,
            "otlp_endpoint": otlp_endpoint,
            "prometheus_enabled": enable_prometheus,
        }
    )


def _setup_tracing(resource: Resource, otlp_endpoint: str) -> None:
    """Configure OpenTelemetry tracing."""
    global _tracer_provider

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Add OTLP exporter for distributed tracing
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=True,  # Use TLS in production
        )
        span_processor = BatchSpanProcessor(otlp_exporter)
        _tracer_provider.add_span_processor(span_processor)
    except Exception as e:
        logger.warning(f"Failed to configure OTLP trace exporter: {e}")

    # Set as global tracer provider
    trace.set_tracer_provider(_tracer_provider)


def _setup_metrics(
    resource: Resource,
    otlp_endpoint: str,
    enable_prometheus: bool,
    prometheus_port: int,
) -> None:
    """Configure OpenTelemetry metrics with Prometheus exporter."""
    global _meter_provider

    readers = []

    # Prometheus reader for scraping
    if enable_prometheus:
        try:
            from prometheus_client import start_http_server as _start_prom_http
            prometheus_reader = PrometheusMetricReader()
            readers.append(prometheus_reader)
            _start_prom_http(prometheus_port)
            logger.info(f"Prometheus metrics HTTP server started on port {prometheus_port}")
        except Exception as e:
            logger.warning(f"Failed to configure Prometheus exporter: {e}")

    # OTLP reader for collector
    try:
        otlp_exporter = OTLPMetricExporter(
            endpoint=otlp_endpoint,
            insecure=True,
        )
        otlp_reader = PeriodicExportingMetricReader(
            otlp_exporter,
            export_interval_millis=30000,  # 30 seconds
        )
        readers.append(otlp_reader)
    except Exception as e:
        logger.warning(f"Failed to configure OTLP metric exporter: {e}")

    # Create meter provider
    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=readers,
    )

    # Set as global meter provider
    metrics.set_meter_provider(_meter_provider)


def _setup_grpc_instrumentation() -> None:
    """Auto-instrument gRPC server and client calls."""
    try:
        # Server-side instrumentation
        server_instrumentor = GrpcInstrumentorServer()
        server_instrumentor.instrument()

        # Client-side instrumentation
        client_instrumentor = GrpcInstrumentorClient()
        client_instrumentor.instrument()

        logger.info("gRPC instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument gRPC: {e}")


def shutdown_observability() -> None:
    """Gracefully shutdown observability components."""
    global _initialized, _tracer_provider, _meter_provider

    if not _initialized:
        return

    try:
        if _tracer_provider:
            _tracer_provider.shutdown()

        if _meter_provider:
            _meter_provider.shutdown()

        logger.info("Observability shutdown complete")
    except Exception as e:
        logger.error(f"Error during observability shutdown: {e}")
    finally:
        _initialized = False
