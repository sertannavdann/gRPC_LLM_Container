"""
DEPRECATED: This client is marked for removal in Stage 4.
Use agent_service.tools.web.vertex_search() instead.

Legacy tool_service has been removed. This client is kept temporarily
for backward compatibility with existing tests.
"""
import warnings
import grpc
import logging
from google.protobuf.struct_pb2 import Struct
from .base_client import BaseClient

logger = logging.getLogger(__name__)


def deprecated(message):
    """Decorator to mark functions as deprecated"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} is deprecated. {message}",
                category=DeprecationWarning,
                stacklevel=2
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator


class ToolClient(BaseClient):
    """
    DEPRECATED: Legacy tool service client.
    
    This class is maintained for backward compatibility only.
    New code should use function tools in agent_service/tools/.
    """
    
    @deprecated("Use agent_service.tools.web.vertex_search() instead")
    def __init__(self):
        warnings.warn(
            "ToolClient is deprecated and will be removed in Stage 4. "
            "Use function tools in agent_service/tools/ instead.",
            DeprecationWarning,
            stacklevel=2
        )
        # Note: tool_service no longer exists, this will fail if called
        # Kept for reference only
        raise NotImplementedError(
            "tool_service has been removed. Use agent_service.tools.web.vertex_search() instead."
        )
    
    @deprecated("Use agent_service.tools.web.vertex_search() instead")
    def call_tool(self, tool_name: str, params: dict) -> dict:
        """DEPRECATED: Execute tool with structured parameters"""
        raise NotImplementedError(
            "tool_service has been removed. Use function tools instead."
        )
    
    @deprecated("Use agent_service.tools.web.vertex_search() instead")
    def web_search(self, query: str, max_results: int = 5) -> list:
        """DEPRECATED: Execute web search with structured results"""
        raise NotImplementedError(
            "tool_service has been removed. Use agent_service.tools.web.vertex_search() instead."
        )