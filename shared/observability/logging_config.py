"""
Structured Logging - JSON logging with automatic context propagation.

Uses structlog for structured logging with:
- Automatic trace/correlation ID injection
- JSON output for log aggregation
- Context propagation across async boundaries
"""
import logging
import sys
from typing import Optional, Dict, Any
from contextvars import ContextVar

try:
    import structlog
    from structlog.contextvars import merge_contextvars, bind_contextvars, clear_contextvars
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None

# Context for additional log fields
_log_context: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})


def configure_logging(
    service_name: str,
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """
    Configure structured logging for the service.

    Args:
        service_name: Name of the service for log identification
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_output: Whether to output JSON (True) or human-readable (False)
    """
    if not STRUCTLOG_AVAILABLE:
        # Fall back to standard logging
        _configure_standard_logging(service_name, log_level)
        return

    # Shared processors for all loggers
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_service_info(service_name),
        _add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        # JSON output for production/log aggregation
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    ))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)


def _configure_standard_logging(service_name: str, log_level: str) -> None:
    """Fallback configuration using standard logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=f"%(asctime)s - {service_name} - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _add_service_info(service_name: str):
    """Processor to add service information to all log entries."""
    def processor(logger, method_name, event_dict):
        event_dict["service"] = service_name
        return event_dict
    return processor


def _add_trace_context(logger, method_name, event_dict):
    """Processor to add trace context to log entries."""
    try:
        from .tracing import get_correlation_id, get_current_span

        # Add correlation ID
        correlation_id = get_correlation_id()
        if correlation_id:
            event_dict["correlation_id"] = correlation_id

        # Add trace/span IDs if available
        span = get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")

    except ImportError:
        pass

    return event_dict


def get_logger(name: str = None) -> Any:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        structlog.BoundLogger or logging.Logger
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        return logging.getLogger(name)


def bind_context(**kwargs) -> None:
    """
    Bind key-value pairs to the logging context.

    These will be included in all subsequent log entries in this context.

    Usage:
        bind_context(user_id="123", request_id="abc")
        logger.info("Processing request")  # includes user_id and request_id
    """
    if STRUCTLOG_AVAILABLE:
        bind_contextvars(**kwargs)
    else:
        # Store in context var for standard logging
        ctx = _log_context.get().copy()
        ctx.update(kwargs)
        _log_context.set(ctx)


def clear_context() -> None:
    """Clear the logging context (call at end of request)."""
    if STRUCTLOG_AVAILABLE:
        clear_contextvars()
    else:
        _log_context.set({})


class LogContext:
    """
    Context manager for scoped logging context.

    Usage:
        with LogContext(user_id="123", action="process"):
            logger.info("Starting")
            # ... work ...
            logger.info("Done")
        # Context is cleared after the block
    """

    def __init__(self, **kwargs):
        self.context = kwargs
        self._token = None

    def __enter__(self):
        bind_context(**self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if STRUCTLOG_AVAILABLE:
            # structlog handles context automatically with contextvars
            pass
        else:
            clear_context()
        return False
