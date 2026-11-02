"""Exact token counts and timings reported by the LLM service (no model needed)."""

import sys
import types

import pytest

from llm_service.config import LLMServiceConfig
from llm_service.engines import GenParams, GenStats
from llm_service.engines.llamacpp import LlamaCppEngine, reused_prefix


# ── KV prefix reuse mirrors llama-cpp-python's Llama.generate ────────────────
def test_no_cache_reuses_nothing():
    assert reused_prefix([], 0, [1, 2, 3]) == 0


def test_partial_prefix_is_reused():
    assert reused_prefix([1, 2, 9, 9], 4, [1, 2, 3, 4]) == 2


def test_full_prompt_match_reevaluates_last_token():
    # Previous context was prompt + generated tokens: the prompt is fully consumed.
    assert reused_prefix([1, 2, 3, 7, 8], 5, [1, 2, 3]) == 2


def test_exact_live_cache_hit_reuses_everything():
    assert reused_prefix([1, 2, 3], 3, [1, 2, 3]) == 3
    assert reused_prefix([1, 2, 3], 3, [1, 2, 3], requires_eval=True) == 2


# ── derived rates ────────────────────────────────────────────────────────────
def test_genstats_rates():
    s = GenStats(t_request=0.0, t_start=0.5, t_first=1.5, t_end=3.5,
                 prompt_tokens=1000, cached_prompt_tokens=200, completion_tokens=41)
    assert s.queue_ms == pytest.approx(500)
    assert s.prefill_ms == pytest.approx(1000)
    assert s.decode_ms == pytest.approx(2000)
    assert s.tokens_per_sec == pytest.approx(20.0)        # 40 tokens after the first in 2 s
    assert s.prefill_tokens_per_sec == pytest.approx(800)  # only evaluated tokens count


def test_genstats_empty_is_zero_not_error():
    s = GenStats()
    assert s.tokens_per_sec == 0.0 and s.prefill_tokens_per_sec == 0.0 and s.decode_ms == 0.0


# ── llama.cpp counting against llama-cpp-python's real call pattern ─────────
class FakeLlama:
    """
    Reproduces how Llama.create_completion drives stopping_criteria:
    one call per sampled token with the evaluated context (prompt + earlier
    tokens), the end-of-text token sampled but not emitted, and one extra call
    after the loop.
    """

    def __init__(self, prompt_len, emitted, stops_on_eog):
        self.prompt_len, self.emitted, self.stops_on_eog = prompt_len, emitted, stops_on_eog
        self.n_tokens, self._input_ids = 0, []

    def tokenize(self, text, add_bos=True, special=True):
        return list(range(self.prompt_len))

    def __call__(self, prompt, stopping_criteria=None, **kw):
        crit = stopping_criteria[0]
        sampled = self.emitted + (1 if self.stops_on_eog else 0)
        for k in range(sampled):
            crit(list(range(self.prompt_len + k)), None)
            if k < self.emitted:
                yield {"choices": [{"text": f"t{k}", "finish_reason": None}]}
        crit(list(range(self.prompt_len + sampled - 1)), None)  # post-loop call
        yield {"choices": [{"text": "", "finish_reason": "stop" if self.stops_on_eog else "length"}]}


@pytest.fixture
def engine(monkeypatch):
    fake_mod = types.ModuleType("llama_cpp")
    fake_mod.StoppingCriteriaList = list
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_mod)
    return LlamaCppEngine(LLMServiceConfig(model_path="m.gguf"))


@pytest.mark.parametrize("prompt_len,emitted,eog,finish", [
    (14, 40, False, "length"),   # hit max_tokens
    (14, 1, True, "stop"),       # "yes" then end-of-text
    (500, 63, True, "stop"),
])
def test_llamacpp_counts_are_exact(engine, prompt_len, emitted, eog, finish):
    engine._llm = FakeLlama(prompt_len, emitted, eog)
    stats = GenStats()
    out = list(engine.stream("p", GenParams(max_tokens=emitted, temperature=0.1), stats))
    assert len(out) == emitted
    assert stats.prompt_tokens == prompt_len
    assert stats.completion_tokens == emitted
    assert stats.finish_reason == finish
    assert stats.t_start <= stats.t_first <= stats.t_end
