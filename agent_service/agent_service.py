"""
Agent gRPC service wiring the new core workflow via the Adapter.

Removes deprecated orchestration and legacy registries.
Reads thread-id from gRPC metadata to enable conversation persistence.
"""

import uuid
import json
import time
import logging
from concurrent import futures
from typing import Optional

import grpc
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2_grpc, health_pb2

# Protobuf imports
try:
    from . import agent_pb2
    from . import agent_pb2_grpc
except ImportError:
    import agent_pb2
    import agent_pb2_grpc

# Adapter and client wrapper
from adapter import AgentServiceAdapter
from llm_wrapper import LLMClientWrapper
from shared.clients.llm_client import LLMClient


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent_service")


class AgentService(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        # Initialize adapter and LLM engine wrapper
        self.adapter = AgentServiceAdapter()
        llm_client = LLMClient(host="llm_service", port=50051)
        llm_engine = LLMClientWrapper(llm_client)
        self.adapter.set_llm_engine(llm_engine)

    def _get_thread_id(self, context: grpc.ServicerContext) -> Optional[str]:
        """Extract thread-id from gRPC metadata if provided."""
        try:
            md = context.invocation_metadata()
            for item in md:
                # item is a tuple (key, value)
                key = (item[0] or "").lower()
                if key == "thread-id":
                    val = item[1]
                    if isinstance(val, bytes):
                        try:
                            return val.decode("utf-8", errors="ignore")
                        except Exception:
                            return None
                    if isinstance(val, str):
                        return val
                    return None
        except Exception:
            pass
        return None

    def QueryAgent(self, request, context):
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[Req ID: {request_id}] Received query: '{request.user_query}'")

        try:
            thread_id = self._get_thread_id(context) or request_id

            result = self.adapter.process_query(
                query=request.user_query,
                thread_id=thread_id,
                context=None,
                user_id=None,
            )

            content = result.get("content") or "Sorry, I couldn't generate a response."
            tool_results = result.get("tool_results", [])

            # Summarize tools used and errors (if any)
            tools_used = []
            errors = []
            for r in tool_results:
                name = r.get("tool_name") or r.get("_metadata", {}).get("tool_name")
                if name and name not in tools_used:
                    tools_used.append(name)
                if r.get("status") == "error" and r.get("error"):
                    errors.append(r.get("error"))

            sources = {
                "tools_used": tools_used,
                "tool_results": tool_results,
                "errors": errors,
                "thread_id": thread_id,
            }

            processing_time = time.time() - start_time
            logger.info(f"[Req ID: {request_id}] Completed in {processing_time:.2f}s")

            return agent_pb2.AgentReply(
                final_answer=content,
                context_used=json.dumps([]),
                sources=json.dumps(sources),
                execution_graph="",
            )

        except Exception as e:
            logger.exception(f"[Req ID: {request_id}] Error processing request: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error processing request. ID: {request_id}")
            return agent_pb2.AgentReply(
                final_answer=f"I'm sorry, but an error occurred while processing your request. (Request ID: {request_id})",
                sources=json.dumps({"error": str(e), "request_id": request_id}),
            )

    def GetMetrics(self, request, context):
        metrics = self.adapter.get_metrics()
        return agent_pb2.MetricsResponse(
            tool_usage=json.dumps({}),
            tool_errors=json.dumps({}),
            llm_calls=0,
            avg_response_time=metrics.get("success_rate", 0.0),
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentService(), server)

    # Health check setup
    health_pb2_grpc.add_HealthServicer_to_server(health.HealthServicer(), server)

    # Reflection setup
    service_names = (
        agent_pb2.DESCRIPTOR.services_by_name['AgentService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port('[::]:50054')
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    serve()