"""
LLM gRPC service.

Serves one model through a pluggable engine (llama.cpp or MLX). Run it
inside Docker for the CPU fallback, or natively on macOS for Metal:

    python -m llm_service.llm_service          # from the repo root (host)
    python llm_service.py                      # inside the container
"""
import grpc
import logging
import sys
import os
from concurrent import futures
import json
from json.decoder import JSONDecodeError
from pathlib import Path

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
    from .model_registry import resolve_model_spec, list_all_models
except ImportError:
    from model_registry import resolve_model_spec, list_all_models

try:
    from .engines import create_engine, GenParams, GenStats
except ImportError:
    from engines import create_engine, GenParams, GenStats

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

SERVICE_NAME = "llm.LLMService"

# One engine per process. Each engine serialises inference with its own lock,
# because neither llama.cpp nor MLX is safe for concurrent generation.
_engine = create_engine(CONFIG)


def _usage(stats: "GenStats") -> "llm_pb2.Usage":
    return llm_pb2.Usage(
        prompt_tokens=stats.prompt_tokens,
        completion_tokens=stats.completion_tokens,
        tokens_per_sec=stats.tokens_per_sec,
        cached_prompt_tokens=stats.cached_prompt_tokens,
        queue_ms=stats.queue_ms,
        prefill_ms=stats.prefill_ms,
        decode_ms=stats.decode_ms,
        prefill_tokens_per_sec=stats.prefill_tokens_per_sec,
    )


def _params(request) -> "GenParams":
    return GenParams(
        max_tokens=min(request.max_tokens or CONFIG.max_tokens, CONFIG.max_tokens),
        temperature=max(0.1, min(request.temperature, 1.0)),
        json_mode=request.response_format == "json",
    )


class LLMServiceServicer(llm_pb2_grpc.LLMServiceServicer):
    def Generate(self, request, context):
        stats = GenStats()  # t_request = now, before waiting for the engine
        try:
            params = _params(request)
            output_buffer = ""
            json_valid = True
            for token in _engine.stream(request.prompt, params, stats):
                output_buffer += token

                # Validate JSON incrementally
                if params.json_mode:
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
                is_valid_json=json_valid,
                finish_reason=stats.finish_reason,
                usage=_usage(stats),
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
            params = _params(request)
            num_samples = max(1, min(request.num_samples, 10))  # Clamp 1-10
            responses = []

            # Generate k samples sequentially (single model instance)
            for i in range(num_samples):
                logger.info(f"Generating sample {i+1}/{num_samples}")
                responses.append(_engine.complete(request.prompt, params).strip())

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
        """Return information about the loaded model and what is running it."""
        filename = Path(CONFIG.model_path).name
        spec = resolve_model_spec(CONFIG.model_path)
        common = dict(
            model_filename=filename,
            device=_engine.effective_device,
            engine=_engine.name,
        )

        if spec:
            return llm_pb2.GetActiveModelResponse(
                model_name=spec.name,
                context_window=CONFIG.n_ctx,
                max_tokens=CONFIG.max_tokens,
                capabilities=list(spec.capabilities),
                tier=CONFIG.tier or spec.tier,
                backend=spec.backend,
                **common,
            )
        return llm_pb2.GetActiveModelResponse(
            model_name=filename,
            context_window=CONFIG.n_ctx,
            max_tokens=CONFIG.max_tokens,
            capabilities=[],
            tier=CONFIG.tier or "unknown",
            backend=_engine.name,
            **common,
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
            active_model=Path(CONFIG.model_path).name,
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


def _set_health(servicer, status) -> None:
    servicer.set("", status)
    servicer.set(SERVICE_NAME, status)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=CONFIG.max_workers))
    llm_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceServicer(), server)

    # Health reports NOT_SERVING until the model is resident, so compose
    # healthchecks and the host supervisor never route to a loading model.
    health_servicer = health.HealthServicer()
    _set_health(health_servicer, health_pb2.HealthCheckResponse.NOT_SERVING)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    reflection.enable_server_reflection([
        llm_pb2.DESCRIPTOR.services_by_name['LLMService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME
    ], server)

    server.add_insecure_port(f"{CONFIG.host}:{CONFIG.port}")
    server.start()
    logger.info(f"LLM Service listening on {CONFIG.host}:{CONFIG.port} (loading model...)")

    try:
        _engine.load()
    except Exception:
        logger.exception("Model load failed; shutting down")
        server.stop(0)
        sys.exit(1)

    _set_health(health_servicer, health_pb2.HealthCheckResponse.SERVING)
    logger.info(
        "Model ready: %s engine=%s device=%s tier=%s",
        Path(CONFIG.model_path).name, _engine.name, _engine.effective_device, CONFIG.tier or "(registry)",
    )

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
