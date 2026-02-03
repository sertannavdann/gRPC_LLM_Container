"""
Distributed Tracing - OpenTelemetry trace context and correlation IDs.

Provides utilities for:
- Creating and managing trace spans
- Propagating context across service boundaries
- Correlation ID generation and extraction
"""
import uuid
from contextvars import ContextVar
from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Tracer, Span, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.context import Context, get_current, attach, detach

# Context variable for correlation ID (survives async boundaries)
_correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)

# Propagator for W3C Trace Context
_propagator = TraceContextTextMapPropagator()

# Module-level tracer cache
_tracer: Optional[Tracer] = None


def get_tracer(name: str = "grpc_llm") -> Tracer:
    """Get or create the tracer for this application."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(name, version="1.0.0")
    return _tracer


def get_correlation_id() -> str:
    """
    Get the current correlation ID.

    Creates a new one if not set.
    """
    cid = _correlation_id_var.get()
    if cid is None:
        cid = str(uuid.uuid4())
        _correlation_id_var.set(cid)
    return cid


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id_var.set(correlation_id)


def clear_correlation_id() -> None:
    """Clear the correlation ID (call at request end)."""
    _correlation_id_var.set(None)


@contextmanager
def create_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
    tracer: Optional[Tracer] = None,
) -> Generator[Span, None, None]:
    """
    Create a new span within the current trace context.

    Usage:
        with create_span("process_query", attributes={"query_length": len(query)}):
            # ... operation ...

    Args:
        name: Name of the span
        kind: SpanKind (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER)
        attributes: Initial span attributes
        tracer: Optional tracer instance (uses default if not provided)

    Yields:
        The created span
    """
    t = tracer or get_tracer()
    attrs = attributes or {}

    # Add correlation ID to all spans
    correlation_id = get_correlation_id()
    attrs["correlation_id"] = correlation_id

    with t.start_as_current_span(name, kind=kind, attributes=attrs) as span:
        yield span


def inject_context(carrier: Dict[str, str]) -> Dict[str, str]:
    """
    Inject trace context into a carrier dict (e.g., gRPC metadata, HTTP headers).

    Usage:
        metadata = {}
        inject_context(metadata)
        # metadata now contains traceparent, tracestate headers

    Args:
        carrier: Dict to inject headers into

    Returns:
        The carrier with trace context headers added
    """
    _propagator.inject(carrier)

    # Also inject correlation ID
    correlation_id = get_correlation_id()
    if correlation_id:
        carrier["x-correlation-id"] = correlation_id

    return carrier


def extract_context(carrier: Dict[str, str]) -> Context:
    """
    Extract trace context from a carrier dict.

    Usage:
        # In gRPC interceptor
        context = extract_context(dict(metadata))
        token = attach(context)
        try:
            # ... handle request ...
        finally:
            detach(token)

    Args:
        carrier: Dict containing trace headers

    Returns:
        OpenTelemetry Context object
    """
    # Extract correlation ID if present
    correlation_id = carrier.get("x-correlation-id")
    if correlation_id:
        set_correlation_id(correlation_id)

    return _propagator.extract(carrier)


def get_current_span() -> Optional[Span]:
    """Get the current active span."""
    return trace.get_current_span()


def add_span_attributes(attributes: Dict[str, Any]) -> None:
    """Add attributes to the current span."""
    span = get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_exception(exception: Exception, attributes: Optional[Dict] = None) -> None:
    """Record an exception on the current span."""
    span = get_current_span()
    if span and span.is_recording():
        span.record_exception(exception, attributes=attributes)
        span.set_status(trace.StatusCode.ERROR, str(exception))


class GrpcMetadataCarrier:
    """
    Carrier that adapts gRPC metadata to/from dict format.

    Usage:
        # Injecting context into outgoing call
        metadata = [("key", "value")]
        carrier = GrpcMetadataCarrier.from_metadata(metadata)
        inject_context(carrier)
        new_metadata = carrier.to_metadata()

        # Extracting context from incoming call
        carrier = GrpcMetadataCarrier.from_metadata(context.invocation_metadata())
        ctx = extract_context(carrier)
    """

    def __init__(self, data: Optional[Dict[str, str]] = None):
        self._data = data or {}

    @classmethod
    def from_metadata(cls, metadata) -> "GrpcMetadataCarrier":
        """Create carrier from gRPC metadata."""
        data = {}
        if metadata:
            for key, value in metadata:
                if isinstance(key, bytes):
                    key = key.decode("utf-8", errors="ignore")
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                data[key.lower()] = value
        return cls(data)

    def to_metadata(self):
        """Convert carrier back to gRPC metadata format."""
        return [(k, v) for k, v in self._data.items()]

    def __getitem__(self, key: str) -> str:
        return self._data.get(key.lower(), "")

    def __setitem__(self, key: str, value: str) -> None:
        self._data[key.lower()] = value

    def get(self, key: str, default: str = None) -> Optional[str]:
        return self._data.get(key.lower(), default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()
