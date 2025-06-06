import grpc
import logging
from typing import Iterator, Optional
from .base_client import BaseClient
import llm_pb2
import llm_pb2_grpc

logger = logging.getLogger(__name__)

class LLMClient(BaseClient):
    def __init__(self, host: str = "llm_service", port: int = 50051):
        super().__init__(host, port)
        self.stub = llm_pb2_grpc.LLMServiceStub(self.channel)
        self._stream_timeout = 30

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        try:
            responses = self.stub.Generate(
                llm_pb2.GenerateRequest(
                    prompt=prompt,
                    max_tokens=min(max_tokens, 2048),
                    temperature=temperature
                ),
                timeout=30
            )
            output = ""
            for response in responses:
                output += response.token
                if response.is_final:
                    break
            return output.strip()
        except grpc.RpcError as e:
            logger.error(f"Generation failed: {e.code().name}")
            return f"LLM Service Error: {e.details()}"

    def generate_stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]:
        """Streaming response with timeout protection"""
        try:
            responses = self.stub.Generate(
                llm_pb2.GenerationRequest(
                    prompt=prompt,
                    max_tokens=min(max_tokens, 2048)
                ),
                timeout=self._stream_timeout
            )
            
            for response in responses:
                yield response.token
                
        except grpc.RpcError as e:
            logger.error(f"Stream generation failed: {e.code().name}")
            yield f"Stream Error: {e.details()}"