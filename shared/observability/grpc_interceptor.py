"""
gRPC Interceptor for Observability - Automatic metrics and tracing.

Provides a server interceptor that automatically:
- Track request latency
- Count requests by method and status
- Propagate trace context
- Add correlation IDs
"""
import time
import logging
from typing import Callable, Any, Optional

import grpc
from grpc import ServerInterceptor

from opentelemetry.trace import SpanKind

from .metrics import (
    create_request_metrics,
    increment_active_requests,
    decrement_active_requests,
    time_operation,
    RequestMetrics,
)
from .tracing import (
    create_span,
    extract_context,
    set_correlation_id,
    get_correlation_id,
    GrpcMetadataCarrier,
)

logger = logging.getLogger(__name__)


class ObservabilityServerInterceptor(ServerInterceptor):
    """
    Server interceptor that adds observability to all gRPC handlers.

    Features:
    - Request duration metrics
    - Error counting
    - Trace context extraction
    - Correlation ID propagation
    """

    def __init__(self, metrics: Optional[RequestMetrics] = None):
        self.metrics = metrics or create_request_metrics()

    def intercept_service(self, continuation, handler_call_details):
        """Intercept the service call to add observability."""
        method = handler_call_details.method

        # Create wrapped handler
        handler = continuation(handler_call_details)
        if handler is None:
            return None

        # Wrap based on handler type
        if handler.unary_unary:
            return self._wrap_unary_handler(handler, method)
        elif handler.unary_stream:
            return self._wrap_streaming_handler(handler, method)
        elif handler.stream_unary:
            return self._wrap_streaming_handler(handler, method)
        elif handler.stream_stream:
            return self._wrap_streaming_handler(handler, method)

        return handler

    def _wrap_unary_handler(self, handler, method: str):
        """Wrap a unary-unary handler with observability."""
        original_handler = handler.unary_unary

        def instrumented_handler(request, context):
            return self._handle_request(
                original_handler, request, context, method, "unary"
            )

        return grpc.unary_unary_rpc_method_handler(
            instrumented_handler,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    def _wrap_streaming_handler(self, handler, method: str):
        """Wrap streaming handlers (placeholder - returns original)."""
        # For streaming, we'd need more complex handling
        # This is a simplified implementation
        return handler

    def _handle_request(
        self,
        handler: Callable,
        request: Any,
        context: grpc.ServicerContext,
        method: str,
        request_type: str,
    ):
        """Handle a request with full observability instrumentation."""
        start_time = time.perf_counter()
        status = "ok"

        try:
            # Extract trace context from metadata
            metadata = context.invocation_metadata() or []
            carrier = GrpcMetadataCarrier.from_metadata(metadata)
            trace_context = extract_context(carrier)

            # Get or create correlation ID
            correlation_id = carrier.get("x-correlation-id") or get_correlation_id()
            set_correlation_id(correlation_id)

            # Increment active requests
            increment_active_requests()

            # Record request
            self.metrics.requests_total.add(
                1, {"method": method, "type": request_type}
            )

            # Create span for this request
            with create_span(
                name=method,
                kind=SpanKind.SERVER,
                attributes={
                    "rpc.method": method,
                    "rpc.system": "grpc",
                },
            ):
                # Call the actual handler
                response = handler(request, context)
                return response

        except grpc.RpcError as e:
            status = "error"
            self.metrics.errors_total.add(
                1, {"method": method, "error_type": "rpc_error"}
            )
            raise
        except Exception as e:
            status = "error"
            self.metrics.errors_total.add(
                1, {"method": method, "error_type": type(e).__name__}
            )
            logger.exception(f"Error in {method}")
            raise
        finally:
            # Record duration
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.request_duration_ms.record(
                duration_ms, {"method": method, "status": status}
            )
            decrement_active_requests()
