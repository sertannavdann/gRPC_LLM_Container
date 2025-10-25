"""
gRPC test client for agent service integration tests.

Provides simplified interface for testing agent_service via gRPC.
"""

import grpc
import logging
from typing import Optional
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from agent_service import agent_pb2, agent_pb2_grpc

logger = logging.getLogger(__name__)


class AgentTestClient:
    """
    gRPC test client for agent_service.
    
    Simplifies testing by providing type-safe methods with
    automatic connection management and error handling.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 50054,
        timeout: int = 30,
    ):
        """
        Initialize test client.
        
        Args:
            host: Agent service hostname
            port: Agent service port
            timeout: Request timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.address = f"{host}:{port}"
        
        # Create channel and stub
        self.channel = grpc.insecure_channel(self.address)
        self.stub = agent_pb2_grpc.AgentServiceStub(self.channel)
        
        logger.info(f"AgentTestClient connected to {self.address}")
    
    def query(
        self,
        user_input: str,
        debug_mode: bool = False,
    ) -> agent_pb2.AgentReply:
        """
        Send query to agent service.
        
        Args:
            user_input: User query text
            debug_mode: Enable debug mode with detailed execution info
        
        Returns:
            agent_pb2.AgentReply: Response with final_answer, context_used, sources, execution_graph
        
        Raises:
            grpc.RpcError: On gRPC failure
        """
        request = agent_pb2.AgentRequest(
            user_query=user_input,
            debug_mode=debug_mode,
        )
        
        logger.info(f"Query: {user_input[:50]}... (debug={debug_mode})")
        
        try:
            response = self.stub.QueryAgent(request, timeout=self.timeout)
            logger.info(f"Response: {response.final_answer[:100]}...")
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()}: {e.details()}")
            raise
    
    def get_metrics(self) -> agent_pb2.MetricsResponse:
        """
        Get agent service metrics.
        
        Returns:
            agent_pb2.MetricsResponse: Metrics including tool_usage, tool_errors, llm_calls, avg_response_time
        
        Raises:
            grpc.RpcError: On gRPC failure
        """
        request = agent_pb2.GetMetricsRequest()
        
        logger.info("Fetching metrics...")
        
        try:
            response = self.stub.GetMetrics(request, timeout=self.timeout)
            logger.info(f"Metrics: llm_calls={response.llm_calls}, avg_time={response.avg_response_time:.2f}s")
            return response
        except grpc.RpcError as e:
            logger.error(f"Metrics error: {e.code()}: {e.details()}")
            raise
    
    def health_check(self) -> bool:
        """
        Check if agent service is healthy.
        
        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            # Try a simple query with short timeout
            response = self.query(
                user_input="hello",
                debug_mode=False,
            )
            
            # Check for valid response
            is_healthy = (
                response is not None
                and len(response.final_answer) > 0
            )
            
            logger.info(f"Health check: {'✓' if is_healthy else '✗'}")
            return is_healthy
        
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    

    
    def close(self):
        """Close gRPC channel and cleanup resources."""
        if self.channel:
            self.channel.close()
            logger.info("AgentTestClient closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
