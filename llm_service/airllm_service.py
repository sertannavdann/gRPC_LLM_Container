"""
AirLLM-backed gRPC service implementing the LLMService proto interface.

Uses AirLLM for layer-streaming inference of 70B+ models on limited VRAM.
HuggingFace safetensors format (NOT GGUF).

Key characteristics:
- Layer streaming: ~5-10 tok/s for 70B (slow but functional on 4GB VRAM)
- 4-bit compression via bitsandbytes
- Sequential request processing (AirLLM limitation)
- Requires CUDA GPU + 64GB+ system RAM
"""

import grpc
import logging
import os
import threading
import json
from concurrent import futures
from pathlib import Path

import torch

try:
    import llm_pb2
    import llm_pb2_grpc
except ImportError:
    from . import llm_pb2
    from . import llm_pb2_grpc

from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2_grpc, health_pb2

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("airllm_service")

# Configuration from environment
MODEL_REPO = os.getenv("MODEL_REPO", "meta-llama/Llama-3.1-70B-Instruct")
COMPRESSION = os.getenv("COMPRESSION", "4bit")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
HOST = os.getenv("LLM_HOST", "[::]")
PORT = int(os.getenv("LLM_PORT", "50051"))

# Sequential lock — AirLLM processes one request at a time
_inference_lock = threading.Lock()


class AirLLMModelManager:
    """Manages AirLLM model lifecycle."""

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._model_repo = MODEL_REPO
        self._lock = threading.Lock()

    def get_model(self):
        """Get or load the AirLLM model."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._load()
        return self._model

    def get_tokenizer(self):
        """Get the model's tokenizer."""
        self.get_model()  # Ensure model is loaded
        return self._tokenizer

    def _load(self):
        """Load model via AirLLM with layer streaming."""
        from airllm import AutoModel

        logger.info(f"Loading AirLLM model: {self._model_repo} (compression={COMPRESSION})")
        logger.info("This may take several minutes on first load (model sharding)...")

        self._model = AutoModel.from_pretrained(
            self._model_repo,
            compression=COMPRESSION,
        )
        self._tokenizer = self._model.tokenizer
        logger.info(f"AirLLM model loaded: {self._model_repo}")

    @property
    def model_name(self) -> str:
        return Path(self._model_repo).name

    @property
    def model_repo(self) -> str:
        return self._model_repo


# Global model manager
_model_manager = AirLLMModelManager()


class HealthServicer(health.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )


class AirLLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    """gRPC service backed by AirLLM for 70B+ model inference."""

    def Generate(self, request, context):
        """Streaming generation via AirLLM."""
        try:
            model = _model_manager.get_model()
            tokenizer = _model_manager.get_tokenizer()

            max_tokens = min(request.max_tokens or MAX_TOKENS, MAX_TOKENS)
            temperature = max(0.1, min(request.temperature or 0.7, 1.0))

            # Tokenize input
            input_ids = tokenizer(
                request.prompt,
                return_tensors="pt",
                truncation=True,
                max_length=8192,
            ).input_ids

            with _inference_lock:
                with torch.no_grad():
                    output_ids = model.generate(
                        input_ids,
                        max_new_tokens=max_tokens,
                        do_sample=temperature > 0.1,
                        temperature=temperature,
                    )

            # Decode output (skip input tokens)
            input_length = input_ids.shape[1]
            generated_ids = output_ids[0][input_length:]
            generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

            # Stream tokens (AirLLM generates all at once, we simulate streaming)
            words = generated_text.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                yield llm_pb2.GenerateResponse(
                    token=token,
                    is_final=False,
                    is_valid_json=False,
                )

            yield llm_pb2.GenerateResponse(
                token="",
                is_final=True,
                is_valid_json=False,
            )

        except Exception as e:
            import traceback
            logger.error(f"AirLLM generation failed: {traceback.format_exc()}")
            context.abort(
                grpc.StatusCode.INTERNAL,
                f"AirLLM generation error ({type(e).__name__}): {str(e)}"
            )

    def GenerateBatch(self, request, context):
        """Batch generation for self-consistency (sequential for AirLLM)."""
        try:
            model = _model_manager.get_model()
            tokenizer = _model_manager.get_tokenizer()

            num_samples = max(1, min(request.num_samples, 5))  # Cap lower for AirLLM
            max_tokens = min(request.max_tokens or MAX_TOKENS, MAX_TOKENS)
            temperature = max(0.1, min(request.temperature or 0.7, 1.0))

            input_ids = tokenizer(
                request.prompt,
                return_tensors="pt",
                truncation=True,
                max_length=8192,
            ).input_ids

            responses = []
            input_length = input_ids.shape[1]

            with _inference_lock:
                for i in range(num_samples):
                    logger.info(f"AirLLM batch sample {i+1}/{num_samples}")
                    with torch.no_grad():
                        output_ids = model.generate(
                            input_ids,
                            max_new_tokens=max_tokens,
                            do_sample=True,
                            temperature=temperature,
                        )
                    generated_ids = output_ids[0][input_length:]
                    text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
                    responses.append(text)

            # Simple majority vote
            from collections import Counter
            normalized = [r.strip().lower() for r in responses]
            counter = Counter(normalized)
            if counter:
                most_common, count = counter.most_common(1)[0]
                idx = normalized.index(most_common)
                majority_answer = responses[idx]
                score = count / len(responses)
            else:
                majority_answer = responses[0] if responses else ""
                count = 1
                score = 1.0

            return llm_pb2.GenerateBatchResponse(
                responses=responses,
                self_consistency_score=score,
                majority_answer=majority_answer,
                majority_count=count,
            )

        except Exception as e:
            import traceback
            logger.error(f"AirLLM batch failed: {traceback.format_exc()}")
            context.abort(
                grpc.StatusCode.INTERNAL,
                f"AirLLM batch error ({type(e).__name__}): {str(e)}"
            )

    def GetActiveModel(self, request, context):
        """Return AirLLM model info."""
        return llm_pb2.GetActiveModelResponse(
            model_name=_model_manager.model_name,
            model_filename=_model_manager.model_repo,
            context_window=131_072,
            max_tokens=MAX_TOKENS,
            capabilities=["reasoning", "verification", "analysis", "deep_research"],
            tier="ultra",
            backend="airllm",
        )

    def ListModels(self, request, context):
        """List the single AirLLM model."""
        model_info = llm_pb2.ModelInfo(
            filename=_model_manager.model_repo,
            name=_model_manager.model_name,
            context_window=131_072,
            recommended_ctx=8192,
            capabilities=["reasoning", "verification", "analysis", "deep_research"],
            tier="ultra",
        )
        return llm_pb2.ListModelsResponse(
            models=[model_info],
            active_model=_model_manager.model_name,
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(AirLLMServiceServicer(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)

    reflection.enable_server_reflection([
        llm_pb2.DESCRIPTOR.services_by_name['LLMService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME,
    ], server)

    server.add_insecure_port(f"{HOST}:{PORT}")
    logger.info(f"AirLLM Service operational on {HOST}:{PORT}")
    logger.info(f"Model: {MODEL_REPO} | Compression: {COMPRESSION}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
