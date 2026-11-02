"""
Engine interface for the LLM service.

An engine owns one loaded model and turns a prompt into text. The servicer
never touches llama.cpp or MLX directly; it asks the configured engine.
Adding a runtime (llama-server, Core ML, ...) means adding one module here.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass(frozen=True)
class GenParams:
    max_tokens: int
    temperature: float
    json_mode: bool = False


@dataclass
class GenStats:
    """
    Exact counts and timings for one generation, filled in by the engine.

    Times are time.perf_counter() values. ``t_request`` is set by the caller
    when the request arrives; the engine sets the rest while it holds its lock,
    so queueing behind another request is separate from model time.
    """
    t_request: float = field(default_factory=time.perf_counter)
    t_start: float = 0.0          # engine lock acquired
    t_first: float = 0.0          # first generated token sampled
    t_end: float = 0.0            # generation finished
    prompt_tokens: int = 0        # incl. BOS
    cached_prompt_tokens: int = 0 # reused from the KV cache, not recomputed
    completion_tokens: int = 0    # excluding the end-of-text token
    finish_reason: str = ""       # "stop" | "length"

    @property
    def queue_ms(self) -> float:
        return max(0.0, (self.t_start - self.t_request) * 1000) if self.t_start else 0.0

    @property
    def prefill_ms(self) -> float:
        return max(0.0, (self.t_first - self.t_start) * 1000) if self.t_first else 0.0

    @property
    def decode_ms(self) -> float:
        return max(0.0, (self.t_end - self.t_first) * 1000) if self.t_first else 0.0

    @property
    def tokens_per_sec(self) -> float:
        s = self.decode_ms / 1000
        return (self.completion_tokens - 1) / s if s > 0 and self.completion_tokens > 1 else 0.0

    @property
    def prefill_tokens_per_sec(self) -> float:
        s = self.prefill_ms / 1000
        evaluated = self.prompt_tokens - self.cached_prompt_tokens
        return evaluated / s if s > 0 and evaluated > 0 else 0.0


class Engine(ABC):
    """One loaded model behind a single-flight lock."""

    name: str = "base"

    def __init__(self, config) -> None:
        self.config = config
        self.effective_device = "cpu"
        # Neither llama.cpp nor MLX is safe for concurrent generation on one
        # model instance, so every engine serialises inference.
        self.lock = threading.Lock()

    @abstractmethod
    def load(self) -> None:
        """Load the model. Must raise on failure."""

    @abstractmethod
    def stream(self, prompt: str, params: GenParams, stats: Optional[GenStats] = None) -> Iterator[str]:
        """Yield text pieces as they are generated; fill ``stats`` if given."""

    def complete(self, prompt: str, params: GenParams, stats: Optional[GenStats] = None) -> str:
        return "".join(self.stream(prompt, params, stats))

    @property
    def supports_hard_json(self) -> bool:
        """True when JSON output is enforced by a grammar, not just validated."""
        return False
