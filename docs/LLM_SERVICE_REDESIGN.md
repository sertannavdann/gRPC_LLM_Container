# LLM Service Redesign: Heterogeneous Inference on Apple Silicon

Status: proposal (NEXUS branch)
Scope: `llm_service/`, `shared/proto/llm.proto`, `shared/clients/llm_client.py`, LIDM tier wiring
Target hardware: M4 Max, 36 GB unified memory (40-core GPU, 16-core Neural Engine)

---

## 1. What the service is today

`llm_service` is a single-model gRPC server built on `llama-cpp-python`. The proto exposes
four RPCs (`Generate` streaming, `GenerateBatch` for self-consistency, `GetActiveModel`,
`ListModels`). A `ModelManager` lazily loads one GGUF, a global `threading.Lock` serialises
every inference call, and a `model_registry.py` maps GGUF filenames to `n_ctx`, temperature,
capabilities, and a LIDM tier (`heavy`, `standard`, `light`, `micro`, `ultra`). The orchestrator
reaches one or more instances through `LLMClientPool`, keyed by tier, and
`orchestrator/capability_map.py` decides which tier a capability needs.

That shape is sound. The problems are in where it runs and what it assumes.

### 1.1 Findings that drive the redesign

| # | Finding | Evidence | Consequence |
|---|---------|----------|-------------|
| F1 | **Inference runs CPU-only inside the Docker Linux VM.** `Llama(...)` is constructed without `n_gpu_layers`; the image is `python:3.11-slim` on x86/arm Linux. Docker Desktop on macOS exposes neither Metal nor the Neural Engine to containers. | `llm_service/llm_service.py` `ModelManager._load`, `llm_service/Dockerfile` | The M4 Max GPU and NPU are idle. The compose comment "3B model within 7.6GiB Docker RAM" is the ceiling this imposes. |
| F2 | **The committed `llama-cli` binary is dead weight.** It is a 50 KB arm64 Mach-O stub dynamically linked against `@rpath/libllama.dylib`, `libggml-metal.dylib`, `libggml-blas.dylib`, none of which are in the repo. It is also a chat CLI, not a server, and `.gitignore` already lists `llm_service/llama/`. | `strings llm_service/llama/llama-cli`, `git ls-files` | Cannot run standalone; nothing references it. Remove from git. |
| F3 | **Two backends, two servicers, duplicated logic.** `airllm_service.py` re-implements the servicer, majority vote, and health with different clamps (`num_samples` cap 5 vs 10) and fake word-level streaming. AirLLM is CUDA-only and disabled in compose. | `llm_service/airllm_service.py`, `docker-compose.yaml` (commented `llm_service_airllm`) | No backend seam exists, so adding MLX or Core ML means a third copy. |
| F4 | **Prompt formatting is the client's job, and clients disagree.** `LocalProvider._format_messages` emits `System:/User:/Assistant:` lines; `openai_wrapper.format_chat_prompt` emits ChatML; the orchestrator has its own `_format_messages`. The server receives a raw string and never applies the model's chat template. | `shared/providers/local_provider.py`, `llm_service/openai_wrapper.py` | Instruct models are driven off-template. Quality and JSON adherence suffer, and switching models means auditing every caller. |
| F5 | **`GenerateBatch` is k sequential full generations under one lock.** Self-consistency with k=5 costs 5x wall-clock and holds every other tier caller. | `LLMServiceServicer.GenerateBatch` | Fine for a 0.5B router; unusable on the heavy tier. Batched sampling from a shared prefill is the fix (MLX and llama.cpp both support it). |
| F6 | **The registry's heavy model does not fit the machine.** `Mistral-Small-24B-Instruct-2501.Q8_0.gguf` is ~25 GB. With macOS (~4 GB) and the Docker VM (7.6 GB) resident, ~24 GB remains for model + KV + NPU model. | `llm_service/model_registry.py`, compose comment | Heavy tier must be 4-bit (or a MoE) on this box. See §5. |
| F7 | **Small correctness bugs.** `openai_wrapper.GRPCClient.generate` yields `response.text`; the field is `token`. `llm_service_standard` sets `N_CTX=4096`, but config reads `LLM_CTX_SIZE`. `make lidm-status` labels heavy as Mistral-24B and standard as Qwen-14B while compose loads Qwen-3B and Qwen-0.5B. | files named | Wrapper streaming is broken today; standard tier silently uses registry default. Also, commit 028a3be renamed the registry key to `Qwen2.5-14B-Instruct-Q4_K_M.gguf` while `tests/unit/test_model_registry.py::test_known_model_qwen14b` still looks up the `Q4_K` name, so that test now fails. |
| F8 | **Health is a constant.** `HealthServicer.Check` always returns `SERVING`, including during the 30-120 s preload and during `switch_model`. | `llm_service.py` | Compose marks the container healthy before it can answer; the orchestrator's first calls hit the load. |
| F9 | **`switch_model` is dead code.** No RPC or env path calls it. | grep | Model switching should be a supervisor concern (restart with new env), not an in-process feature. |

---

## 2. Design goals

1. Use the M4 Max GPU for the heavy tier and the Neural Engine for the small tiers, concurrently.
2. One servicer, N backends. Backend is a config choice, not a code fork.
3. Server-side chat templating and structured output, so every caller sends messages, not strings.
4. Keep the gRPC contract and `LLMClientPool` tier model. The orchestrator should not notice the change beyond faster responses and a richer `GetActiveModel`.
5. Keep the Docker CPU path alive for CI and non-Mac hosts.

---

## 3. Target topology

```
┌──────────────────────── macOS host (native processes) ────────────────────────┐
│                                                                               │
│  llm-heavy   :50051  backend=mlx      device=gpu   Qwen3-30B-A3B 4-bit (~17GB) │
│  llm-utility :50061  backend=coreml   device=ane   Qwen3-1.7B / Llama-3.2-3B  │
│  (optional)  :50063  backend=llama-cpp device=gpu  any GGUF, n_gpu_layers=-1   │
│                                                                               │
└───────────────▲───────────────────────────────▲───────────────────────────────┘
                │ host.docker.internal:50051    │ host.docker.internal:50061
┌───────────────┴───────────────────────────────┴───────────────────────────────┐
│  Docker Compose (Linux VM, 7.6 GiB)                                           │
│  orchestrator  chroma_service  sandbox_service  ui  dashboard  otel  ...      │
│  llm_service (CPU llama.cpp)  ← profile "cpu-fallback" only, for CI/non-Mac   │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Why native host processes

Metal and the ANE are only reachable from a macOS process. The inference tier therefore
moves out of Compose and is supervised by `make llm-up` (a `launchd` plist or a small
`scripts/llm_supervisor.sh`). The rest of the stack is unchanged except for endpoint values:

```
LLM_HEAVY_HOST=host.docker.internal:50051
LLM_STANDARD_HOST=host.docker.internal:50061
```

`LLMClientPool.reconfigure` already hot-swaps endpoints, and `capability_map.get_lidm_endpoints`
already reads these variables, so no orchestrator code changes are required for routing.

### 3.2 Tier to device mapping

| LIDM tier | Device | Backend | Model class | Roles (from `capability_map.py`) |
|-----------|--------|---------|-------------|-----------------------------------|
| `heavy` | GPU (Metal) | `mlx` (default) or `llama-cpp` with `n_gpu_layers=-1` | 24B-32B dense 4-bit, or 30B-A3B MoE | coding, reasoning, analysis |
| `standard` / `light` | NPU (ANE) | `coreml` | 1B-4B, ANE-compiled | routing, classification, extraction, fast_response, finance, math, multilingual |
| `micro` | NPU (ANE) | `coreml` | 0.5B-1B | routing, classification |
| `ultra` | external | provider gateway | hosted API | verification, deep_research |

`ultra` stops meaning "AirLLM 70B". On this hardware it is the existing provider gateway
(Anthropic/OpenAI/Perplexity) behind the same `LLMService` contract. AirLLM stays as an
optional Linux/CUDA backend but is no longer a second servicer (§4.2).

### 3.3 What the NPU model is for, and what it is not for

The GPU and NPU share the unified memory bus, but an agentic loop rarely saturates it from
both sides at the same instant: the NPU router does prefill-heavy, compute-bound work on
a ~1-2 GB model while the GPU does bandwidth-bound decode on a ~17 GB model. Measured
ANE throughput for this class is roughly 45-60 tok/s on 1B and ~9 tok/s on 8B, so the
utility model should stay at or below ~3B.

Good roles for the ANE tier, all of which already exist as capabilities in this branch:

- **Upfront intent router**: `DelegationManager` decomposition, replacing the heavy-tier call
  that currently classifies before it reasons.
- **Structured extraction**: tool-argument extraction and JSON repair on the router's output.
- **Critic / verifier**: `GenerateBatch` self-consistency scoring on the *utility* model to
  gate whether a heavy-tier answer needs a retry. This turns `ENABLE_SELF_CONSISTENCY`
  from a 5x heavy-tier cost into a cheap NPU side-check.
- **Summariser**: conversation-window compaction for `AGENT_CONTEXT_WINDOW`.

Not a good role: **speculative drafter for the GPU model**. Speculative decoding needs the
draft and target to exchange logits per step in-process. MLX already does this on the GPU
with `draft_model` (a 0.5B-1.7B MLX draft next to the 30B target). A cross-process ANE
drafter adds gRPC latency per step and loses the gain. Keep drafting inside the heavy
backend and keep the ANE model an independent agent.

---

## 4. Service redesign

### 4.1 Package layout

```
llm_service/
  server.py              # grpc bootstrap, health, reflection (replaces llm_service.py)
  servicer.py            # one LLMServiceServicer; all RPC logic; backend-agnostic
  config.py              # + LLM_BACKEND, LLM_DEVICE, LLM_MODEL (id or path), LLM_DRAFT_MODEL
  model_registry.py      # + backend/device/format fields; MLX and CoreML entries
  backends/
    base.py              # InferenceBackend protocol
    llama_cpp.py         # current code, plus n_gpu_layers, chat template, batched sampling
    mlx.py               # mlx-lm: stream_generate, prompt cache, draft_model, logits processors
    coreml.py            # ANEMLL/CoreML-LLM compiled models; fixed-shape prefill + decode
    airllm.py            # optional; CUDA only
  templating.py          # chat template application (tokenizer.apply_chat_template / jinja)
  structured.py          # JSON grammar (llama) / Outlines-MLX logits processor (mlx) / post-validate (coreml)
  openai_wrapper.py      # unchanged contract; fix .text -> .token; use ChatRequest messages
```

### 4.2 Backend protocol

```python
class InferenceBackend(Protocol):
    name: str                      # "llama-cpp" | "mlx" | "coreml" | "airllm"
    device: str                    # "cpu" | "gpu" | "ane" | "cuda"

    def load(self, spec: ModelSpec, cfg: LLMServiceConfig) -> None: ...
    def unload(self) -> None: ...
    def info(self) -> BackendInfo: ...        # n_ctx, tok/s estimate, memory_bytes, supports_*
    def render(self, messages: list[Message], tools: list[dict] | None) -> str: ...
    def stream(self, prompt: str, params: GenParams) -> Iterator[Chunk]: ...
    def sample_n(self, prompt: str, n: int, params: GenParams) -> list[str]: ...
    def count_tokens(self, text: str) -> int: ...
```

Rules the servicer enforces regardless of backend:

- Single-flight per process. Neither llama.cpp nor MLX is safe for concurrent generation
  on one model, and ANE Core ML models serialise on the accelerator anyway. Keep the lock,
  but move it into the backend so a future continuous-batching backend can drop it.
- `sample_n` is a real batched sample when the backend supports it (MLX: batch of n from a
  shared prompt cache; llama.cpp: `n_seq_max=n` with shared prefix), and a sequential loop
  otherwise. Self-consistency stops costing k prefill passes.
- Health reports `NOT_SERVING` until `load()` returns, and during any reload.
- `GetActiveModel` returns `backend`, `device`, `memory_bytes`, and `draft_model` so
  `make lidm-status` and the dashboard show what the hardware is doing.

### 4.3 Proto changes (additive, backward compatible)

```proto
message Message { string role = 1; string content = 2; }

message GenerateRequest {
  string prompt = 1;                 // legacy; ignored when messages is set
  int32 max_tokens = 2;
  float temperature = 3;
  string response_format = 4;        // "text" | "json" | "json_schema"
  repeated Message messages = 5;     // NEW: server applies the model's chat template
  string json_schema = 6;            // NEW: enforced by grammar/logits-processor when supported
  repeated string stop = 7;          // NEW
  float top_p = 8;                   // NEW
  string model = 9;                  // NEW: registry key; empty = instance default
}

message GenerateResponse {
  string token = 1;
  bool is_final = 2;
  bool is_valid_json = 3;
  string finish_reason = 4;          // NEW: "stop" | "length" | "error"
  Usage usage = 5;                   // NEW: only on the final chunk
}

message Usage { int32 prompt_tokens = 1; int32 completion_tokens = 2; float tokens_per_sec = 3; }

message GetActiveModelResponse {
  // existing fields 1-7 unchanged
  string device = 8;                 // NEW: cpu | gpu | ane | cuda
  int64 memory_bytes = 9;            // NEW
  string draft_model = 10;           // NEW
  bool supports_json_schema = 11;    // NEW
}
```

Clients keep working: `prompt` remains valid, and `messages` is opt-in. `LocalProvider`,
the orchestrator wrapper, and `openai_wrapper` migrate to `messages` and delete their
three private formatters. Token accounting in `LocalProvider` and `openai_wrapper` moves
from `len(text.split())` to the returned `Usage`.

### 4.4 Configuration

| Variable | Values | Notes |
|----------|--------|-------|
| `LLM_BACKEND` | `llama-cpp` (default in Docker), `mlx`, `coreml`, `airllm` | Selects `backends/<name>.py` |
| `LLM_DEVICE` | `auto`, `cpu`, `gpu`, `ane`, `cuda` | `auto` picks the backend's native device |
| `LLM_MODEL` | registry key, HF repo id (`mlx-community/...`), or path | Replaces `LLM_MODEL_PATH`; the old name stays as an alias |
| `LLM_DRAFT_MODEL` | HF id or path | MLX and llama.cpp only; enables in-process speculative decoding |
| `LLM_GPU_LAYERS` | int, `-1` = all | llama.cpp only; default `-1` when `LLM_DEVICE=gpu` |
| `LLM_CTX_SIZE`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` | unchanged | Registry auto-configures when unset |
| `LLM_TIER` | `heavy` etc. | Reported in `GetActiveModel`; lets one binary serve any tier |

`model_registry.ModelSpec` gains `backend`, `device`, `format` (`gguf`, `mlx`, `coreml`),
`source` (HF id), and `memory_gb`. `resolve_model_spec` matches on registry key, HF id,
or filename so the same entry works for a local path and a hub id.

### 4.5 Structured output per backend

| Backend | Mechanism | Guarantee |
|---------|-----------|-----------|
| llama-cpp | GBNF grammar (existing `JSON_GRAMMAR`) or `LlamaGrammar.from_json_schema` | Hard |
| mlx | Outlines MLX logits processor from `json_schema`; fall back to JSON grammar via the same processor | Hard |
| coreml | No token-level constraint on ANE; prompt for JSON, validate, one repair pass on the same tier | Soft, validated |

`is_valid_json` is computed identically for all three by the servicer, as today.

### 4.6 Process supervision on macOS

`make llm-up` starts the native tier processes from a `uv`/`venv` at `llm_service/.venv`
(Python 3.11+, `mlx-lm`, `coremltools`, `llama-cpp-python` built with `CMAKE_ARGS="-DGGML_METAL=on"`).
Each tier is one process with its own env file under `config/llm/<tier>.env`. `make llm-status`
replaces `lidm-status` and reads labels from `GetActiveModel` instead of hard-coding model names.

The Docker `llm_service` container remains behind `profiles: [cpu-fallback]` so
`docker compose up` on a Linux CI runner or a non-Mac laptop still works unchanged.

---

## 5. Memory budget for 36 GB

| Resident | Approx GB |
|----------|-----------|
| macOS + apps | 4-5 |
| Docker Desktop VM (per compose comment) | 7.6 |
| Available for inference | ~23-24 |

Fit table for the heavy tier, with 16K context KV included:

| Model | Format | Weights | KV @16K | Fits with ANE model (+2 GB) |
|-------|--------|---------|---------|------------------------------|
| Qwen3-30B-A3B (MoE) | MLX 4-bit | ~17 | ~1.5 | Yes, best tok/s for size |
| Qwen2.5/3-32B dense | MLX 4-bit | ~18.5 | ~2 | Yes, tight |
| Mistral-Small-24B | MLX 4-bit / Q4_K_M | ~14 | ~3 | Yes, comfortable |
| Mistral-Small-24B | Q8_0 (current registry) | ~25 | ~3 | **No** |
| Qwen2.5-14B | Q4_K / MLX 4-bit | ~8.5 | ~1.5 | Yes, leaves room for a 3B draft |
| Llama-3.1-70B | any | 35-40 | | **No** (drop AirLLM entry on Mac) |

Raise the GPU wired limit if the heavy model plus KV exceeds the default ~75% cap:
`sudo sysctl iogpu.wired_limit_mb=28000`. Stop the Docker VM when benchmarking the tier alone;
its 7.6 GB is the single largest non-inference tenant.

Utility tier on the ANE: Qwen3-1.7B or Llama-3.2-3B compiled with ANEMLL at 4-6 bit is
1-2 GB resident and leaves the GPU untouched.

---

## 6. Migration plan

Each step is independently shippable and keeps `make up` working.

1. **Cleanup (no behaviour change).** Remove `llm_service/llama/llama-cli` from git. Fix
   `openai_wrapper` `.text` to `.token`. Fix `N_CTX` to `LLM_CTX_SIZE` in compose. Make
   `lidm-status` read names from `GetActiveModel`. Health returns `NOT_SERVING` until loaded.
2. **Backend seam.** Extract `backends/base.py` and `backends/llama_cpp.py` from the current
   `ModelManager`; `airllm_service.py` becomes `backends/airllm.py` and its servicer is deleted.
   Unit tests: servicer with a fake backend (streaming, batch, clamps, JSON validation).
3. **Server-side templating and proto additions.** Add `messages`, `json_schema`, `stop`,
   `Usage`. Migrate `LocalProvider`, orchestrator wrapper, and `openai_wrapper` to `messages`.
   Regenerate stubs with `make proto-gen`. Regression: existing string-prompt callers pass.
4. **Metal for llama.cpp.** `LLM_GPU_LAYERS=-1` when `LLM_DEVICE=gpu`; native `make llm-up`
   with the Metal wheel; compose points at `host.docker.internal`. Benchmark with
   `scripts/test_inference_speed.py` before and after. This alone is the biggest win and
   needs no new backend.
5. **MLX backend for the heavy tier.** `backends/mlx.py` with `stream_generate`, prompt cache,
   optional `draft_model`, Outlines logits processor. Registry entries for
   `mlx-community/*` 4-bit models. Compare against step 4 on the same prompts.
6. **Core ML backend for the utility tier.** Convert the router model with ANEMLL, serve on
   :50061 with `LLM_DEVICE=ane`. Switch `capability_map` so `routing`, `classification`,
   `extraction`, and self-consistency scoring resolve to `standard`.
7. **Batched `sample_n`.** Replace sequential `GenerateBatch` with shared-prefill sampling on
   llama.cpp and MLX. Re-enable `ENABLE_SELF_CONSISTENCY` on the utility tier by default.

Validation gates per step: unit tests green, `make status` healthy,
`scripts/test_inference_speed.py` numbers recorded in `docs/KNOWN-ISSUES.md` or a new
`docs/BENCHMARKS.md`, and one end-to-end orchestrator query through both tiers.

---

## 7. Decisions and open questions

Decided:

- MLX is the default heavy backend on Apple Silicon; llama.cpp with Metal is the
  compatibility backend for GGUF-only models. Both live behind the same seam.
- The utility tier runs on the ANE as an independent agent, not as a drafter for the GPU.
- Inference processes run natively on the host. Docker keeps the CPU fallback only.
- `ultra` maps to the external provider gateway on this hardware.

Open:

- Which router/critic model on the ANE: Qwen3-1.7B (better JSON adherence in our prompts)
  versus Llama-3.2-3B (higher ANEMLL throughput reports). Decide by running the existing
  `tests/integration/test_self_consistency_workflow.py` prompts against both.
- Whether the `heavy` default is Qwen3-30B-A3B (fastest) or Mistral-Small-24B 4-bit
  (best coding/JSON in the current registry). The registry can carry both; compose picks.
- Whether to keep `GenerateBatch` as an RPC or fold it into `Generate` with `n>1` once
  `sample_n` exists.
