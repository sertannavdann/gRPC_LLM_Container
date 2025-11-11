import grpc
import logging
from typing import Iterator, Optional
from .base_client import BaseClient

# Try local import first (when used as a service), fall back to shared/generated
try:
    from llm_service import llm_pb2
    from llm_service import llm_pb2_grpc
except ModuleNotFoundError:
    try:
        # Import from shared/generated when running in agent_service container
        from shared.generated import llm_pb2, llm_pb2_grpc
    except ModuleNotFoundError:
        # Last resort: try relative import
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'generated'))
        import llm_pb2
        import llm_pb2_grpc

logger = logging.getLogger(__name__)

class LLMClient(BaseClient):
    def __init__(self, host: str = "llm_service", port: int = 50051):
        super().__init__(host, port)
        self.stub = llm_pb2_grpc.LLMServiceStub(self.channel)
        self._stream_timeout = 30

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        # DEBUG: Added logging to trace call path
        logger.info(f"LLMClient.generate() called with prompt ({len(prompt)} chars): {prompt[:200]}")
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

    def generate_stream(self, prompt: str, max_tokens: int = 512, *, temperature: float = 0.7) -> Iterator[llm_pb2.GenerateResponse]:
        """Yield streaming `GenerateResponse` messages for real-time consumption."""

        request = llm_pb2.GenerateRequest(
            prompt=prompt,
            max_tokens=min(max_tokens, 2048),
            temperature=temperature,
        )

        try:
            responses = self.stub.Generate(request, timeout=self._stream_timeout)
            for response in responses:
                yield response

        except grpc.RpcError as exc:
            logger.error("Stream generation failed", extra={"code": exc.code().name, "details": exc.details()})
            error = llm_pb2.GenerateResponse(
                token=f"Stream Error: {exc.details()}",
                is_final=True,
                is_valid_json=False,
            )
            yield error