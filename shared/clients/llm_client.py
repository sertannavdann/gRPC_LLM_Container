import grpc
import logging
from typing import Iterator, Optional, Dict, Tuple
from .base_client import BaseClient

# Try local import first (when used as a service), fall back to shared/generated
try:
    from llm_service import llm_pb2
    from llm_service import llm_pb2_grpc
except ModuleNotFoundError:
    try:
        # Import from shared/generated as fallback
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

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7, response_format: str = "") -> str:
        """
        Generate text from LLM.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            response_format: Optional format constraint (e.g., "json")

        Returns:
            Generated text
        """
        try:
            responses = self.stub.Generate(
                llm_pb2.GenerateRequest(
                    prompt=prompt,
                    max_tokens=min(max_tokens, 2048),
                    temperature=temperature,
                    response_format=response_format
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

    def generate_batch(
        self,
        prompt: str,
        num_samples: int = 5,
        max_tokens: int = 512,
        temperature: float = 0.7,
        response_format: str = ""
    ) -> dict:
        """
        Generate k samples for self-consistency scoring (Agent0 Phase 2).
        """
        try:
            response = self.stub.GenerateBatch(
                llm_pb2.GenerateBatchRequest(
                    prompt=prompt,
                    num_samples=min(num_samples, 10),
                    max_tokens=min(max_tokens, 2048),
                    temperature=temperature,
                    response_format=response_format
                ),
                timeout=120  # Longer timeout for batch generation
            )
            return {
                "responses": list(response.responses),
                "self_consistency_score": response.self_consistency_score,
                "majority_answer": response.majority_answer,
                "majority_count": response.majority_count
            }
        except grpc.RpcError as e:
            logger.error(f"Batch generation failed: {e.code().name}")
            return {
                "responses": [],
                "self_consistency_score": 0.0,
                "majority_answer": f"LLM Service Error: {e.details()}",
                "majority_count": 0
            }

    def get_active_model(self) -> dict:
        """Get information about the currently loaded model on this instance."""
        try:
            response = self.stub.GetActiveModel(
                llm_pb2.GetActiveModelRequest(),
                timeout=5,
            )
            return {
                "model_name": response.model_name,
                "model_filename": response.model_filename,
                "context_window": response.context_window,
                "max_tokens": response.max_tokens,
                "capabilities": list(response.capabilities),
                "tier": response.tier,
                "backend": response.backend,
            }
        except grpc.RpcError as e:
            logger.error(f"GetActiveModel failed: {e.code().name}")
            return {"error": str(e.details())}

    def list_models(self) -> dict:
        """List all known models from the registry."""
        try:
            response = self.stub.ListModels(
                llm_pb2.ListModelsRequest(),
                timeout=5,
            )
            models = []
            for m in response.models:
                models.append({
                    "filename": m.filename,
                    "name": m.name,
                    "context_window": m.context_window,
                    "recommended_ctx": m.recommended_ctx,
                    "capabilities": list(m.capabilities),
                    "tier": m.tier,
                })
            return {
                "models": models,
                "active_model": response.active_model,
            }
        except grpc.RpcError as e:
            logger.error(f"ListModels failed: {e.code().name}")
            return {"models": [], "active_model": "", "error": str(e.details())}


class LLMClientPool:
    """
    LIDM: Manages connections to multiple LLM service instances.

    Routes requests to the appropriate tier based on capability requirements.
    """

    def __init__(self, endpoints: Dict[str, str]):
        """
        Args:
            endpoints: Mapping of tier → "host:port" strings.
                       e.g. {"heavy": "llm_service:50051", "standard": "llm_service_standard:50051"}
        """
        self.clients: Dict[str, LLMClient] = {}
        for tier, endpoint in endpoints.items():
            if not endpoint:
                continue
            host, port_str = endpoint.rsplit(":", 1)
            port = int(port_str)
            self.clients[tier] = LLMClient(host=host, port=port)
            logger.info(f"LLMClientPool: {tier} → {host}:{port}")

        if not self.clients:
            logger.warning("LLMClientPool initialized with no endpoints")

    def get_client(self, tier: str) -> Optional[LLMClient]:
        """Get client for a specific tier. Falls back to 'standard', then any available."""
        if tier in self.clients:
            return self.clients[tier]
        if "standard" in self.clients:
            logger.debug(f"Tier '{tier}' not available, falling back to 'standard'")
            return self.clients["standard"]
        # Return any available client
        if self.clients:
            fallback_tier = next(iter(self.clients))
            logger.debug(f"Tier '{tier}' not available, falling back to '{fallback_tier}'")
            return self.clients[fallback_tier]
        return None

    def generate(self, prompt: str, tier: str = "standard", **kwargs) -> str:
        """Generate using a specific tier's LLM instance."""
        client = self.get_client(tier)
        if client is None:
            return "Error: No LLM service available"
        return client.generate(prompt, **kwargs)

    def get_active_models(self) -> Dict[str, dict]:
        """Query active model info from all connected instances."""
        results = {}
        for tier, client in self.clients.items():
            results[tier] = client.get_active_model()
        return results

    @property
    def available_tiers(self) -> list:
        return list(self.clients.keys())
