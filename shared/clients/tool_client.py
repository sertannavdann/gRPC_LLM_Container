import grpc
import logging
from google.protobuf.struct_pb2 import Struct
from .base_client import BaseClient
import tool_pb2
import tool_pb2_grpc

logger = logging.getLogger(__name__)

class ToolClient(BaseClient):
    def __init__(self):
        super().__init__("tool_service", 50053)
        self.stub = tool_pb2_grpc.ToolServiceStub(self.channel)

    @BaseClient.retry_decorator()
    def call_tool(self, tool_name: str, params: dict) -> dict:
        """Execute tool with structured parameters"""
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
                "message": response.message,
                "results": [
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet
                    } for r in response.results
                ],
                "metadata": dict(response.metadata)
            }
        except grpc.RpcError as e:
            logger.error(f"Tool call failed: {e.code().name}")
            return {
                "success": False,
                "message": f"RPC Error: {e.details()}",
                "results": [],
                "metadata": {}
            }

    def web_search(self, query: str, max_results: int = 5) -> list:
        """Execute web search with structured results"""
        response = self.call_tool(
            "web_search",
            {"query": query, "max_results": str(max_results)}
        )
        if response["success"]:
            return response["results"]
        return []