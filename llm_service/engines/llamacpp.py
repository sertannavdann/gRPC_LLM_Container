"""llama.cpp engine (llama-cpp-python). CPU, Metal, or CUDA depending on the build."""

from __future__ import annotations

import logging
import sys
import time
from typing import Iterator, Optional

from .base import Engine, GenParams, GenStats

logger = logging.getLogger("llm_service.engines.llamacpp")

JSON_GRAMMAR = r'''
root ::= object
value ::= object | array | string | number | "true" | "false" | "null"
object ::= "{" ws ( string ws ":" ws value (ws "," ws string ws ":" ws value)* )? ws "}"
array ::= "[" ws ( value (ws "," ws value)* )? ws "]"
string ::= "\"" [^"\\\n]* "\""
number ::= "-"? ( "0" | [1-9] [0-9]* ) ( "." [0-9]+ )? ( [eE] [-+]? [0-9]+ )?
ws ::= [ \t\n]*
'''


def detect_device(n_gpu_layers: int, supports_offload: bool, platform: str) -> str:
    """Name the device that will actually run the model."""
    if n_gpu_layers == 0 or not supports_offload:
        return "cpu"
    return "metal" if platform == "darwin" else "cuda"


def reused_prefix(cached_ids, n_cached: int, prompt_ids: list, requires_eval: bool = False) -> int:
    """
    Prompt tokens llama-cpp-python will take from the KV cache instead of evaluating.

    Mirrors ``Llama.generate``: it keeps the longest common prefix with the
    previous context, but re-evaluates the last prompt token when the whole
    prompt matches (to refresh logits), unless the cache is an exact live hit.
    """
    if n_cached <= 0 or not prompt_ids:
        return 0
    longest = 0
    for a, b in zip(list(cached_ids[:n_cached]), prompt_ids):
        if a != b:
            break
        longest += 1
    consumed = longest == len(prompt_ids)
    if consumed and n_cached == len(prompt_ids) and not requires_eval:
        return len(prompt_ids)
    return longest - 1 if consumed else longest


def build_llama_kwargs(cfg, llama_cpp_module) -> dict:
    """Translate LLMServiceConfig into Llama(...) keyword arguments."""
    kwargs = dict(
        model_path=cfg.model_path,
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        n_batch=cfg.n_batch,
        n_ubatch=min(cfg.n_ubatch, cfg.n_batch),
        n_gpu_layers=cfg.n_gpu_layers,
        flash_attn=cfg.flash_attn,
        use_mlock=cfg.mlock,
        verbose=cfg.verbose,
    )
    if cfg.kv_cache_type != "f16":
        ggml_type = getattr(llama_cpp_module, f"GGML_TYPE_{cfg.kv_cache_type.upper()}")
        kwargs["type_k"] = ggml_type
        kwargs["type_v"] = ggml_type
    return kwargs


class LlamaCppEngine(Engine):
    name = "llamacpp"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._llm = None
        self._grammar = None

    def load(self) -> None:
        import llama_cpp
        from llama_cpp import Llama, LlamaGrammar

        cfg = self.config
        self.effective_device = detect_device(
            cfg.n_gpu_layers, bool(llama_cpp.llama_supports_gpu_offload()), sys.platform
        )
        logger.info(
            "Loading %s with llama.cpp: device=%s gpu_layers=%s threads=%s ctx=%s "
            "batch=%s/%s flash_attn=%s kv=%s mlock=%s",
            cfg.model_path, self.effective_device, cfg.n_gpu_layers, cfg.n_threads,
            cfg.n_ctx, cfg.n_batch, cfg.n_ubatch, cfg.flash_attn, cfg.kv_cache_type, cfg.mlock,
        )
        self._llm = Llama(**build_llama_kwargs(cfg, llama_cpp))
        self._grammar = LlamaGrammar.from_string(JSON_GRAMMAR, verbose=False)

    @property
    def supports_hard_json(self) -> bool:
        return True

    def _gen_config(self, params: GenParams, stream: bool) -> dict:
        gen = {"max_tokens": params.max_tokens, "temperature": params.temperature, "stream": stream}
        if params.json_mode:
            gen["grammar"] = self._grammar
        return gen

    def stream(self, prompt: str, params: GenParams, stats: Optional[GenStats] = None) -> Iterator[str]:
        stats = stats if stats is not None else GenStats()
        with self.lock:
            llm = self._llm
            stats.t_start = time.perf_counter()
            prompt_ids = llm.tokenize(prompt.encode("utf-8"), add_bos=True, special=True)
            stats.prompt_tokens = len(prompt_ids)
            stats.cached_prompt_tokens = reused_prefix(
                getattr(llm, "_input_ids", []), llm.n_tokens, prompt_ids,
                bool(getattr(llm, "_requires_eval", False)),
            )

            # llama-cpp-python calls the stopping criteria once per sampled token
            # with the evaluated context: the prompt plus every earlier sampled
            # token (the new token is appended on the next step). So the first
            # call sees exactly the prompt, and the length grows by one per token.
            # It is called once more after the loop with an equal-length context,
            # so counting calls would over-count.
            first_len = 0
            max_len = 0

            def track(input_ids, _logits) -> bool:
                nonlocal first_len, max_len
                n = len(input_ids)
                if not first_len:
                    first_len = n
                    stats.t_first = time.perf_counter()
                max_len = max(max_len, n)
                return False

            gen = self._gen_config(params, stream=True)
            gen["stopping_criteria"] = self._stopping_list([track])
            finish = None
            for output in llm(prompt, **gen):
                choice = output["choices"][0]
                finish = choice.get("finish_reason") or finish
                if choice["text"]:
                    yield choice["text"]
            stats.t_end = time.perf_counter()
            stats.finish_reason = finish or "stop"
            if first_len:
                stats.prompt_tokens = first_len
                sampled = max_len - first_len + 1
                # The end-of-text token is sampled but is not part of the output.
                stats.completion_tokens = sampled - 1 if stats.finish_reason == "stop" else sampled

    @staticmethod
    def _stopping_list(fns):
        from llama_cpp import StoppingCriteriaList
        return StoppingCriteriaList(fns)

    def complete(self, prompt: str, params: GenParams, stats: Optional[GenStats] = None) -> str:
        return "".join(self.stream(prompt, params, stats))
