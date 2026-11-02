"""
MLX engine (mlx-lm). Apple Silicon GPU only; installed on the host, never in Docker.

The model path is an MLX model directory or a Hugging Face repo id such as
``mlx-community/Qwen2.5-3B-Instruct-4bit``. JSON mode is soft: the servicer
validates the output, but nothing constrains the tokens.
"""

from __future__ import annotations

import logging
import time
from typing import Iterator, Optional

from .base import Engine, GenParams, GenStats

logger = logging.getLogger("llm_service.engines.mlx")

STOP_TOKENS = ("<|endoftext|>", "<|im_end|>", "<|eot_id|>", "<|end_of_text|>")


class MlxEngine(Engine):
    name = "mlx"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._model = None
        self._tokenizer = None

    def load(self) -> None:
        try:
            import mlx_lm
        except ImportError as exc:  # pragma: no cover - depends on host install
            raise RuntimeError(
                "LLM_ENGINE=mlx needs mlx-lm on an Apple Silicon host: "
                "make llm-venv installs it into llm_service/.venv"
            ) from exc

        cfg = self.config
        if cfg.model_path.endswith(".gguf"):
            raise ValueError("The mlx engine cannot load a .gguf file")
        logger.info("Loading %s with MLX on the Metal GPU", cfg.model_path)
        self._model, self._tokenizer = mlx_lm.load(cfg.model_path)
        # Raw-prompt callers rely on the end-of-text token stopping generation,
        # as llama.cpp does from GGUF metadata. MLX tokenizers often list only
        # the chat end token, so register the common end tokens the vocab has.
        vocab = self._tokenizer.get_vocab() if hasattr(self._tokenizer, "get_vocab") else {}
        for token in STOP_TOKENS:
            if token in vocab:
                self._tokenizer.add_eos_token(token)
        self.effective_device = "metal"

    def stream(self, prompt: str, params: GenParams, stats: Optional[GenStats] = None) -> Iterator[str]:
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        stats = stats if stats is not None else GenStats()
        sampler = make_sampler(temp=params.temperature)
        with self.lock:
            stats.t_start = time.perf_counter()
            last = None
            for response in stream_generate(
                self._model, self._tokenizer, prompt,
                max_tokens=params.max_tokens, sampler=sampler,
            ):
                if last is None:
                    stats.t_first = time.perf_counter()
                last = response
                if response.text:
                    yield response.text
            stats.t_end = time.perf_counter()
            if last is not None:
                # No cross-request prompt cache is used, so nothing is reused.
                stats.prompt_tokens = int(last.prompt_tokens)
                stats.finish_reason = last.finish_reason or "length"
                # generation_tokens counts the end-of-text token when it stops on one.
                n = int(last.generation_tokens)
                stats.completion_tokens = n - 1 if stats.finish_reason == "stop" else n
