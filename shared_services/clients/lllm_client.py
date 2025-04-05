from .base_client import BaseClient
import llm_pb2
import llm_pb2_grpc
import logging
from typing import Iterator

logger = logging.getLogger(__name__)

class LLMClient(BaseClient):
    def __init__(self):
        super().__init__("llm_service", 50051)
        self.stub = llm_pb2_grpc.LLMServiceStub(self.channel)

    @BaseClient._retry_decorator()
    def generate_stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        """
        Stream LLM response with proper error handling
        Marks method as retryable through decorator metadata
        """
        try:
            for response in self.stub.Generate(
                llm_pb2.GenerateRequest(
                    prompt=prompt,
                    max_tokens=min(max_tokens, 1024),
                    temperature=0.7
                )
            ):
                if not response.is_final:
                    yield response.token
        except grpc.RpcError as e:
            logger.error(f"LLM generation failed: {e.code().name}")
            raise

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        """Full response generation with auto-chunk handling"""
        return "".join([token for token in self.generate_stream(prompt, max_tokens)])