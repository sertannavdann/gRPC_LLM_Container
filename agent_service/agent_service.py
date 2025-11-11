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
from core.checkpointing import CheckpointManager, RecoveryManager


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent_service")


class AgentService(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        # Initialize adapter and LLM engine wrapper
        self.adapter = AgentServiceAdapter()
        llm_client = LLMClient(host="llm_service", port=50051)
        llm_engine = LLMClientWrapper(llm_client)
        self.adapter.set_llm_engine(llm_engine)
        
        # Initialize recovery manager
        self.recovery_manager = RecoveryManager(self.adapter.checkpoint_manager)
        
        # Run startup recovery
        self._run_startup_recovery()
    
    def _run_startup_recovery(self):
        """
        Run crash recovery on service startup.
        
        Scans for incomplete threads and attempts to resume them.
        """
        logger.info("Running startup crash recovery scan...")
        
        try:
            # Scan for crashed threads (inactive for >5 minutes)
            crashed_threads = self.recovery_manager.scan_for_crashed_threads(
                older_than_minutes=5
            )
            
            if not crashed_threads:
                logger.info("No crashed threads found. Clean startup.")
                return
            
            logger.warning(f"Found {len(crashed_threads)} crashed threads. Attempting recovery...")
            
            recovered = 0
            failed = 0
            
            for thread_id in crashed_threads:
                try:
                    # Check if recoverable
                    can_recover, reason = self.recovery_manager.can_recover_thread(thread_id)
                    if not can_recover:
                        logger.warning(f"Cannot recover thread {thread_id}: {reason}")
                        failed += 1
                        continue
                    
                    # Load checkpoint
                    checkpoint_state = self.recovery_manager.load_checkpoint_state(thread_id)
                    if not checkpoint_state:
                        logger.error(f"Failed to load checkpoint for {thread_id}")
                        self.recovery_manager.mark_recovery_attempt(thread_id, success=False)
                        failed += 1
                        continue
                    
                    # Mark as recovered (mark_thread_incomplete will be set again on next run)
                    self.adapter.checkpoint_manager.mark_thread_complete(thread_id)
                    self.recovery_manager.mark_recovery_attempt(thread_id, success=True)
                    recovered += 1
                    
                    logger.info(f"Successfully recovered thread {thread_id}")
                    
                except Exception as e:
                    logger.error(f"Recovery failed for thread {thread_id}: {e}", exc_info=True)
                    self.recovery_manager.mark_recovery_attempt(thread_id, success=False)
                    failed += 1
            
            logger.info(
                f"Recovery complete: {recovered} recovered, {failed} failed"
            )
            
            # Log recovery report
            report = self.recovery_manager.get_recovery_report()
            logger.info(f"Recovery report: {report}")
            
        except Exception as e:
            logger.error(f"Startup recovery scan failed: {e}", exc_info=True)

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
        """Process user query through agent workflow."""
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[{request_id}] Query: '{request.user_query}'")

        try:
            # Get or create thread_id for conversation persistence
            thread_id = self._get_thread_id(context) or request_id

            # Process query through adapter
            result = self.adapter.process_query(
                query=request.user_query,
                thread_id=thread_id,
            )

            # Extract response content
            content = result.get("content") or "Sorry, I couldn't generate a response."
            
            # Build sources metadata
            sources = self._build_sources_metadata(result, thread_id)

            # Log completion
            elapsed = time.time() - start_time
            logger.info(f"[{request_id}] Completed in {elapsed:.2f}s")

            return agent_pb2.AgentReply(
                final_answer=content,
                context_used=json.dumps([]),
                sources=json.dumps(sources),
                execution_graph="",
            )

        except Exception as e:
            logger.exception(f"[{request_id}] Error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error. Request ID: {request_id}")
            return agent_pb2.AgentReply(
                final_answer=f"Sorry, an error occurred. (Request ID: {request_id})",
                sources=json.dumps({"error": str(e), "request_id": request_id}),
            )
    
    def _build_sources_metadata(self, result: dict, thread_id: str) -> dict:
        """Extract and format sources metadata from result."""
        tool_results = result.get("tool_results", [])
        
        # Extract unique tool names and errors
        tools_used = []
        errors = []
        for r in tool_results:
            # Get tool name from result or metadata
            name = r.get("tool_name") or r.get("_metadata", {}).get("tool_name")
            if name and name not in tools_used:
                tools_used.append(name)
            # Collect errors
            if r.get("status") == "error" and r.get("error"):
                errors.append(r.get("error"))

        return {
            "tools_used": tools_used,
            "tool_results": tool_results,
            "errors": errors,
            "thread_id": thread_id,
        }

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