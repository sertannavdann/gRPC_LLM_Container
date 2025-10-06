import os
import grpc
import logging
from typing import Optional

from .base_client import BaseClient
from shared.generated import cpp_llm_pb2, cpp_llm_pb2_grpc

logger = logging.getLogger(__name__)


class CppLLMClient(BaseClient):
    """Lightweight client for the C++ gRPC LLM service."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, *, timeout_seconds: float = 10.0):
        host = host or os.getenv("CPP_LLM_HOST", "host.docker.internal")
        port = port or int(os.getenv("CPP_LLM_PORT", "50061"))
        super().__init__(host, port)
        self._timeout = timeout_seconds
        self._stub = cpp_llm_pb2_grpc.CppLLMServiceStub(self.channel)

    def run_inference(self, prompt: str) -> dict:
        """Send a single inference request and return both raw and structured outputs."""
        logger.info("cpp-llm-client: sending inference request", extra={"prompt": prompt})
        try:
            response = self._stub.RunInference(
                cpp_llm_pb2.InferenceRequest(input=prompt),
                timeout=self._timeout,
            )
            payload = {
                "output": response.output,
                "intent_payload": response.intent_payload,
            }
            logger.info(
                "cpp-llm-client: received response",
                extra={
                    "output": response.output,
                    "intent_payload": response.intent_payload,
                },
            )
            return payload
        except grpc.RpcError as exc:
            logger.error(
                "cpp-llm-client: inference failed",
                extra={
                    "code": exc.code().name,
                    "details": exc.details(),
                },
            )
            return {
                "output": f"[cpp-llm-error] {exc.details()}",
                "intent_payload": "",
            }
