from .base_client import BaseClient
import tool_pb2
import tool_pb2_grpc
import logging
from google.protobuf.struct_pb2 import Struct

logger = logging.getLogger(__name__)

class ToolClient(BaseClient):
    def __init__(self):
        super().__init__("tool_service", 50053)
        self.stub = tool_pb2_grpc.ToolServiceStub(self.channel)

    @BaseClient._retry_decorator()
    def call_tool(self, tool_name: str, params: dict) -> dict:
        """Generic tool execution with parameter validation"""
        try:
            struct_params = Struct()
            struct_params.update(params)
            
            response = self.stub.CallTool(
                tool_pb2.ToolRequest(
                    tool_name=tool_name,
                    params=struct_params
                )
            )
            
            return {
                "success": response.success,
                "output": response.output,
                "data": dict(response.data) if response.data else {}
            }
        except grpc.RpcError as e:
            logger.error(f"Tool {tool_name} failed: {e.details()}")
            return {
                "success": False,
                "output": f"Tool error: {e.code().name}",
                "data": {}
            }

    def web_search(self, query: str, max_results: int = 3) -> str:
        """Specialized web search wrapper"""
        return self.call_tool(
            "web_search",
            {"query": query, "max_results": str(max_results)}
        )["output"]