# LLM Tier Benchmarks

Host: Apple M4 Max, 36 GB unified memory, macOS 26.5.
Runtimes: llama-cpp-python 0.3.36 (ggml 0.25.3, Metal build), mlx 0.32.3, mlx-lm 0.32.0.
Tool: `scripts/llm_bench.py` (`make llm-bench`). Raw JSON is written to `logs/llm/`.

## How numbers are measured (from 2026-10-12)

The service reports a `Usage` message on the final stream chunk, so the benchmark no
longer estimates anything:

| Field | Source |
|---|---|
| `prompt_tokens`, `completion_tokens` | The engine's own tokenizer. Completion excludes the end-of-text token. |
| `cached_prompt_tokens` | Prompt prefix llama.cpp reused from the previous request's KV cache. MLX reports 0. |
| `queue_ms` | Time waiting for another request to finish on the same tier. |
| `prefill_ms` | Engine start to first token sampled: prompt evaluation plus one sampling step. |
| `decode_ms`, `tokens_per_sec` | First to last token; rate is (completion − 1) / decode time. |
| `prefill_tokens_per_sec` | (prompt − cached) / prefill time, so cache hits do not inflate it. |

The counts are checked against independent ground truth. A 40-token cap reports exactly
40 with finish reason `length`. A natural stop reports the tokens emitted. The prompt count
matches the model tokenizer. `tests/unit/test_llm_usage.py` locks this in, including
llama-cpp-python's extra stopping-criteria call after the loop, which made a call
counter over-count by one.

Every benchmark prompt starts with a unique tag, so no request reuses the previous one's
cache. Use `--allow-cache` to measure warm-cache behaviour on purpose. The client also
reports wall time minus server time. That gRPC and Python overhead measured about 1 ms
per request, so it is not a meaningful error source.

## Exact baseline (2026-10-25, idle GPU)

Measured with `make llm-bench` and server-side `Usage`, two passes each, no other GPU
apps running, 43% memory free. Both passes agreed within 1%, so these are the
prediction baselines.

| Tier | Model | Decode tok/s | Prefill, 46-token prompt | Prefill, 1,863-token prompt | Prefill tok/s |
|---|---|---:|---:|---:|---:|
| heavy, llama.cpp Metal | Qwen2.5-14B Q4_K_M, ctx 16K | 36.1 | 188 ms | 5.1 s | 364 |
| standard, MLX | Qwen2.5-3B 4-bit, ctx 8K | 158.7 | 52 ms | 1.04 s | 1,790 |

Client overhead was 0.4-0.5 ms per request. Raw JSON: `logs/llm/bench-*-20261025-*.json`.

## Stability (2026-10-25)

`make llm-stability TIER=<tier>` (`scripts/llm_stability.py`) checks the things that
break GPU serving rather than how fast it goes: health plus reported device, exact
accounting at the cap and on a natural stop, four concurrent requests serialised through
the engine lock, a soak with a decode-degradation limit (15%), RSS growth of the tier
process (512 MB limit), a clean error on a prompt longer than the context window with
the process still SERVING, and optionally a prompt filling 70% of the window.
`make llm-stability-all` runs every tier in `LLM_TIERS`;
`tests/integration/test_llm_gpu_stability.py` runs the same script for each tier with a
live pid file and skips when none is running.

| Check | heavy, 14B llama.cpp | standard, 3B MLX |
|---|---|---|
| Soak, 60 s | 32 req, 35.9 → 35.8 tok/s, 0.1% drop, 0 errors | 134 req, 158.2 → 157.7 tok/s, 0.3% drop, 0 errors |
| Concurrency, 4 parallel | all completed, max queue 3.1 s | all completed, max queue 0.75 s |
| RSS over soak | 10,404 → 10,448 MB (+43) | 244 → 248 MB (+3) |
| Overflow (2× ctx prompt) | rejected INTERNAL, still SERVING | skipped (MLX has no hard limit) |
| 70% context fill | 9,580 tokens, prefill 32.7 s (293 tok/s) | 4,801 tokens, prefill 2.9 s (1,663 tok/s) |

A second run with a 30 s soak repeated the result (0.0% and 0.5% drop, RSS +2 MB and
+0 MB). Prefill speed on the 14B falls from 364 to 293 tok/s between 1.9K and 9.6K
tokens as attention cost grows; that is expected, not a fault.

Note on the `stop` check: without a chat template a 3B model keeps writing after "OK"
instead of emitting end-of-text, so that one prompt is wrapped in Qwen's ChatML format
to test the engine's EOS handling rather than the model's inclination. Server-side
templating remains redesign step 3.

## Earlier client-side estimates

**The numbers below predate exact usage.** They were measured on the client: decode counted
streamed chunks, prefill assumed four characters per token, and repeated prompts could
hit llama.cpp's prefix cache. They were also taken while another app held the GPU. Use the
exact baseline above instead; these are kept only for the before/after contrast with Docker CPU.

The prompt set has three parts. **long** asks for a 128-token answer. **prefill** sends
a 1,841-token prompt and asks for a 64-token summary. **sustain** repeats the long
prompt for the stated time.

## Before and after (client-side estimates, 2026-10-11)

| Config | Model | Decode tok/s | TTFT, long | TTFT, 1,841-token prompt |
|---|---|---:|---:|---:|
| Before: Docker CPU, llama.cpp | Qwen2.5-3B Q5_K_M | 39 | 1.43 s | 18.6 s |
| Host Metal, llama.cpp | Qwen2.5-3B Q5_K_M | 72-91 | 0.06 s | 1.6-3.6 s |
| **Host Metal, MLX (standard default)** | Qwen2.5-3B 4-bit | **115-134** | **0.06-0.09 s** | **1.2-3.3 s** |
| **Host Metal, llama.cpp (heavy)** | Qwen2.5-14B Q4_K_M | **22-30** | 0.21-0.42 s | 6.1-9.0 s |

For the 3B model, moving off Docker took decode from 39 to about 120 tokens per second.
Time to first token on a short prompt dropped from 1.4 s to under 0.1 s. The 14B heavy
model could not run usefully in the 8 GB Docker VM at all.

## Sustained decode

| Tier | Duration | Decode at start | at 60 s | at end | Retained |
|---|---:|---:|---:|---:|---:|
| heavy, 14B llama.cpp Metal | 300 s | 24.9 | 25.4 | 23.9 | 96% |
| standard, 3B MLX | 120 s | 114.1 | 110.2 | 111.8 | 98% |

Both tiers were loaded while these ran. Neither shows thermal throttling.

## Heavy tier load evidence

From `logs/llm/heavy.log` with `LLM_VERBOSE=1`:

```
ggml_metal_device_init: GPU name:   MTL0 (Apple M4 Max)
ggml_metal_device_init: recommendedMaxWorkingSetSize  = 30150.67 MB
load_tensors: offloaded 49/49 layers to GPU
llama_context: flash_attn            = enabled
llama_kv_cache: size = 1632.00 MiB ( 16384 cells,  48 layers,  1/1 seqs), K (q8_0):  816.00 MiB, V (q8_0):  816.00 MiB
```

The model loads in about 5 s.

## Prompt-processing settings, 14B

Measured by calling `Llama.eval` directly on the 1,841-token prompt.

| Setting | Prefill tok/s |
|---|---:|
| Flash attention, q8_0 KV, batch 2048 / micro-batch 512 (shipped) | 377 |
| Flash attention, f16 KV, 2048 / 512 | 360 |
| No flash attention, f16 KV, 512 / 512 | 260 |

Flash attention is worth about 45%. A q8_0 KV cache halves KV memory at no speed cost.
Runs with micro-batch 2048 returned before the GPU finished, so their timings were
invalid and are not shown.

## Caveats

- **The GPU was shared.** During these runs another app, most likely Unreal Editor,
  held the GPU at about 78% utilization while the tiers were idle. That is the likely
  cause of the heavy tier ranging from 22 to 30 tok/s between runs. Rerun with other GPU
  apps closed before comparing against these numbers.
- **On 2026-10-12 the machine was too loaded to re-measure.** With exact counters, MLX
  decoded at 4 to 28 tok/s instead of 115 to 134, while the GPU sat at 67-79%
  utilization with the tiers idle and iCloud sync used most of a CPU core. Re-run on a
  quiet machine before using any number here as a prediction baseline.
- **Power was not measured.** `make llm-bench POWER=1` needs `sudo` for `powermetrics`.
  The ANE/GPU/CPU experiments recorded about 17 W on the GPU rail for a 4B background
  model.
- Compare only rows from the same macOS build and runtime versions.

## End-to-end check

`make query` through the orchestrator container, with both tiers on the host:
"What is 17 times 23?" returned the correct answer (391) via the math tool in 70 s.
Most of that time was the model repeating its answer until the 2,048-token cap.
The orchestrator sends raw `System:/User:` prompts without the model's chat
template, so the model never emits its end-of-turn token. That is redesign step 3
(server-side templating), not an inference-speed problem.

