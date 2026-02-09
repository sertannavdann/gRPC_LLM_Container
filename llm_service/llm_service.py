#llm_service.py
import grpc
import logging
import sys
import os
import threading
from concurrent import futures
import json
from json.decoder import JSONDecodeError
from pathlib import Path

from llama_cpp import Llama, LlamaGrammar

try:
    from . import llm_pb2
    from . import llm_pb2_grpc
except ImportError:
    import llm_pb2
    import llm_pb2_grpc

# Import config (works in both package and script mode)
try:
    from .config import get_config
except ImportError:
    from config import get_config

# Import model registry for introspection RPCs
try:
    from .model_registry import resolve_model_spec, MODEL_SPECS, list_all_models
except ImportError:
    from model_registry import resolve_model_spec, MODEL_SPECS, list_all_models

# Import self-consistency from core (consolidated logic)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from core.self_consistency import compute_self_consistency
except ImportError:
    # Fallback if core not available (standalone mode)
    compute_self_consistency = None

from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2_grpc, health_pb2
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("llm_service")

# Load configuration
CONFIG = get_config()
CONFIG.log_config()

# =============================================================================
# CONCURRENCY MANAGEMENT
# =============================================================================
# llama-cpp-python is NOT thread-safe for concurrent inference on a single
# model instance. We use a threading.Lock to serialize all inference requests.
# This prevents GGML_ASSERT crashes and thread pool check failures.
# See: https://github.com/ggml-org/llama.cpp/discussions/499
# =============================================================================
_inference_lock = threading.Lock()

JSON_GRAMMAR = r'''
root ::= object
value ::= object | array | string | number | "true" | "false" | "null"
object ::= "{" ws ( string ws ":" ws value (ws "," ws string ws ":" ws value)* )? ws "}"
array ::= "[" ws ( value (ws "," ws value)* )? ws "]"
string ::= "\"" [^"\\\n]* "\""
number ::= "-"? ( "0" | [1-9] [0-9]* ) ( "." [0-9]+ )? ( [eE] [-+]? [0-9]+ )?
ws ::= [ \t\n]*
'''


class ModelManager:
    """
    Manages LLM model lifecycle: load, switch, and introspection.

    Replaces the old @lru_cache load_model() approach with explicit
    state management and thread-safe model switching.
    """

    def __init__(self, config):
        self._config = config
        self._model = None
        self._model_path = config.model_path
        self._lock = threading.Lock()

    def get_model(self) -> Llama:
        """Get the currently loaded model, loading it if necessary."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._load()
        return self._model

    def _load(self):
        """Load model from the current model path."""
        logger.info("Loading model from %s", self._model_path)
        self._model = Llama(
            model_path=self._model_path,
            n_ctx=self._config.n_ctx,
            n_threads=self._config.n_threads,
            n_batch=self._config.n_batch,
            verbose=self._config.verbose,
        )
        logger.info("Model loaded successfully: %s", Path(self._model_path).name)

    def switch_model(self, new_model_path: str):
        """
        Switch to a different model. Acquires inference lock to block
        all concurrent inference during the switch (~10-30s).
        """
        with _inference_lock:
            with self._lock:
                logger.info("Switching model from %s to %s",
                            Path(self._model_path).name,
                            Path(new_model_path).name)
                # Release old model
                del self._model
                self._model = None
                self._model_path = new_model_path
                self._config.model_path = new_model_path
                self._load()

    @property
    def active_model_path(self) -> str:
        return self._model_path

    @property
    def active_model_filename(self) -> str:
        return Path(self._model_path).name


class HealthServicer(health.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )


# Global model manager
_model_manager = ModelManager(CONFIG)


class LLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request, context):
        try:
            llm = _model_manager.get_model()
            gen_config = {
                "max_tokens": min(request.max_tokens, CONFIG.max_tokens),
                "temperature": max(0.1, min(request.temperature, 1.0)),
                "stream": True
            }

            # Only add grammar if response_format is "json"
            if request.response_format == "json":
                gen_config["grammar"] = self._get_json_grammar()

            # Acquire inference lock to prevent concurrent access to llama model
            # llama-cpp-python is NOT thread-safe for concurrent inference
            with _inference_lock:
                # Generation loop with JSON validation
                output_buffer = ""
                json_valid = True
                for output in llm(request.prompt, **gen_config):
                    token = output["choices"][0]["text"]
                    output_buffer += token


                    # Validate JSON incrementally
                    if request.response_format == "json":
                        try:
                            json.loads(output_buffer)
                            json_valid = True
                        except JSONDecodeError:
                            json_valid = False

                    yield llm_pb2.GenerateResponse(
                        token=token,
                        is_final=False,
                        is_valid_json=json_valid
                    )

                yield llm_pb2.GenerateResponse(
                    token="",
                    is_final=True,
                    is_valid_json=json_valid
                )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            error_msg = f"Type: {type(e).__name__}, Message: {str(e)}, Traceback: {tb}"
            logger.error(f"Generation failed: {error_msg}")
            context.abort(
                grpc.StatusCode.INTERNAL,
                f"Generation error ({type(e).__name__}): {str(e) or 'No message'}"
            )

    def GenerateBatch(self, request, context):
        """
        Generate k samples for self-consistency scoring (Agent0 Phase 2).
        Returns all responses plus majority voting metrics.
        """
        try:
            llm = _model_manager.get_model()
            num_samples = max(1, min(request.num_samples, 10))  # Clamp 1-10
            responses = []

            gen_config = {
                "max_tokens": min(request.max_tokens, CONFIG.max_tokens),
                "temperature": max(0.1, min(request.temperature, 1.0)),
                "stream": False  # Non-streaming for batch
            }

            if request.response_format == "json":
                gen_config["grammar"] = self._get_json_grammar()

            # Acquire inference lock - llama-cpp-python is NOT thread-safe
            with _inference_lock:
                # Generate k samples sequentially (single model instance)
                for i in range(num_samples):
                    logger.info(f"Generating sample {i+1}/{num_samples}")
                    output = llm(request.prompt, **gen_config)
                    text = output["choices"][0]["text"].strip()
                    responses.append(text)

            # Compute self-consistency via consolidated module
            if compute_self_consistency is not None:
                consistency_score, majority_answer, majority_count = compute_self_consistency(responses)
            else:
                # Fallback if core module not available
                majority_answer, majority_count, consistency_score = self._compute_majority_vote_fallback(responses)

            logger.info(f"Self-consistency: {consistency_score:.2f} ({majority_count}/{num_samples} agree)")

            return llm_pb2.GenerateBatchResponse(
                responses=responses,
                self_consistency_score=consistency_score,
                majority_answer=majority_answer,
                majority_count=majority_count
            )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Batch generation failed: {tb}")
            context.abort(
                grpc.StatusCode.INTERNAL,
                f"Batch generation error ({type(e).__name__}): {str(e) or 'No message'}"
            )

    def GetActiveModel(self, request, context):
        """Return information about the currently loaded model."""
        filename = _model_manager.active_model_filename
        spec = resolve_model_spec(_model_manager.active_model_path)

        if spec:
            return llm_pb2.GetActiveModelResponse(
                model_name=spec.name,
                model_filename=filename,
                context_window=spec.context_window,
                max_tokens=spec.max_tokens,
                capabilities=list(spec.capabilities),
                tier=spec.tier,
                backend=spec.backend,
            )
        else:
            return llm_pb2.GetActiveModelResponse(
                model_name=filename,
                model_filename=filename,
                context_window=CONFIG.n_ctx,
                max_tokens=CONFIG.max_tokens,
                capabilities=[],
                tier="unknown",
                backend="llama-cpp",
            )

    def ListModels(self, request, context):
        """Return all known models from the registry."""
        models = []
        for spec in list_all_models():
            models.append(llm_pb2.ModelInfo(
                filename=spec.name,  # For GGUF, use registry key; for AirLLM, use name
                name=spec.name,
                context_window=spec.context_window,
                recommended_ctx=spec.recommended_ctx,
                capabilities=list(spec.capabilities),
                tier=spec.tier,
            ))

        return llm_pb2.ListModelsResponse(
            models=models,
            active_model=_model_manager.active_model_filename,
        )

    def _compute_majority_vote_fallback(self, responses: list) -> tuple:
        """
        Fallback majority voting if core module not available.
        Returns (majority_answer, count, p̂ score).
        """
        from collections import Counter

        if not responses:
            return "", 0, 0.0

        # Normalize responses for comparison
        normalized = []
        for r in responses:
            try:
                parsed = json.loads(r)
                if isinstance(parsed, dict):
                    answer = parsed.get("content", parsed.get("answer", r))
                    normalized.append(str(answer).strip().lower())
                else:
                    normalized.append(str(parsed).strip().lower())
            except json.JSONDecodeError:
                normalized.append(r.strip().lower())

        counter = Counter(normalized)
        if not counter:
            return "", 0, 0.0

        most_common_norm, count = counter.most_common(1)[0]

        for i, norm in enumerate(normalized):
            if norm == most_common_norm:
                majority_answer = responses[i]
                break
        else:
            majority_answer = responses[0]

        consistency_score = count / len(responses)
        return majority_answer, count, consistency_score

    def _get_json_grammar(self):
        """Define strict JSON grammar for LLM"""
        grammar_str = r'''
root ::= object
value ::= object | array | string | number | "true" | "false" | "null"
object ::= "{" ws ( string ws ":" ws value (ws "," ws string ws ":" ws value)* )? ws "}"
array ::= "[" ws ( value (ws "," ws value)* )? ws "]"
string ::= "\"" [^"\\\n]* "\""
number ::= "-"? ( "0" | [1-9] [0-9]* ) ( "." [0-9]+ )? ( [eE] [-+]? [0-9]+ )?
ws ::= [ \t\n]*
'''
        return LlamaGrammar.from_string(grammar_str)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=CONFIG.max_workers))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceServicer(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)

    reflection.enable_server_reflection([
        llm_pb2.DESCRIPTOR.services_by_name['LLMService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME
    ], server)

    server.add_insecure_port(f"{CONFIG.host}:{CONFIG.port}")
    logger.info(f"LLM Service operational on {CONFIG.host}:{CONFIG.port}")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
