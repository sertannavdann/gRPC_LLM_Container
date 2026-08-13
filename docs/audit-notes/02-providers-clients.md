# NEXUS Provider/Client/Utils Redundancy Audit

## 1. PER-PROVIDER CONCERN MATRIX
- base_provider.py: defines exc types L31-48, unused max_retries L27, no retry
- online_provider.py: owns HTTP client L49-64, headers L218-232, payload L234-269, parse L271-303, stream L115-173, error map L98-113, no retry
- openai/perplexity: pure inherit
- openclaw_provider.py: dead _get_headers override L100-114 (base calls _build_headers; api_key forced "openclaw" L81 → always Bearer openclaw)
- anthropic_provider.py: only _build_headers L82-96 overridden; posts OpenAI payload to /chat/completions (wrong wire format for Anthropic); name "claude" L70 vs ProviderType.ANTHROPIC "anthropic" → rate limiter key mismatch
- github_models.py: re-implements everything L108-362; wholesale copy of online_provider L60-303; fake stream L394-409
- local_provider.py: prompt flattening L160-188 (System:/User:/Assistant:), token count via split() L79-80
- llm_service/openai_wrapper.py: ChatML prompt fmt L97-115, token count split() L220-223, own parse/stream

HIGH: github_models.py:108-362 copy of online_provider.py:60-303 → reparent to OnlineProvider, delete L108-233
HIGH: online_provider.py:111-113 & 171-173 bare except swallows ProviderAuthError/RateLimitError → reclassified as ProviderConnectionError → gateway retries 5x on invalid API key. Fix: re-raise ProviderError before catch-all.
HIGH: anthropic_provider inherits incompatible OpenAI wire protocol; needs real subclass or delete
HIGH: openclaw _get_headers dead override (rename to _build_headers)
MED: token counting duplicated (local_provider L78-81, openai_wrapper L220-223), both split()-based
MED: message→prompt flattening 4 divergent templates (local_provider, openai_wrapper ChatML, online_provider L246-251, github_models L168-173, orchestrator_service ~225)
MED: json extraction: shared/utils/json_parser.py:28-143 (3-strategy) unused in hot path; llm_gateway.py:329 bare json.loads; llm_service.py:173 bare; llm_service.py:297-334 _compute_majority_vote_fallback duplicates core/self_consistency.py:26-35
LOW: API-key/env resolution 3x: shared/providers/config.py:40-111, orchestrator/config.py:87-99, provider_router.py:363-374; base URLs duplicated in config.py + each provider __init__

## 2. GATEWAY vs CLIENT OVERLAP
HIGH: three parallel LLM-fallback implementations:
  1. llm_gateway.py:435-575 (purpose-lane routing + fallback + retry + schema + budget)
  2. provider_router.py:193-255,390-421 (complexity heuristic + FALLBACK_CHAIN L113 + health skip)
  3. llm_client.py:194-213 LLMClientPool.get_client (tier ladder)
  → collapse: gateway owns selection; ProviderRouter → complexity classifier only
MED: async→sync bridge 3x: base_provider.py:145-188 (zero call sites, per-call event loop), orchestrator_service.py:138-300 OnlineProviderWrapper (thread-local, correct), llm_gateway.py:170-208. Delete base version, share thread-local one.
MED: base_client.py:46-53 _configure_retries monkey-patches all public attrs with tenacity incl. generators; all clients swallow grpc.RpcError → retry layer inert; also grpc.enable_retries=1 L35 (3rd layer). Delete.
HIGH(bug): chroma_client.py:45,68 self.logger undefined in BaseClient → AttributeError on RpcError
MED: airllm_service.py:108-254 duplicates llm_service.py:145-295 (same 4 RPCs, lock, clamps); airllm L200-212 third majority-vote copy; hardcodes model metadata that model_registry.py:82-92 declares. → BaseLLMServicer.

## 3. RESILIENCE INVENTORY
R1 llm_gateway.py:36-70+349-433: 5 attempts, jitter yes, error-class yes; BUT blocking time.sleep at L421 inside async def; dead retry_after block L399-407
R2 github_models.py:235-362: 3 attempts, no jitter, no cap, recursive; nested with R1 → up to 15 upstream calls
R3 base_client.py:13-17 tenacity: no jitter, all-exception, inert
R4 base_client.py:35 grpc.enable_retries=1, no service config
R5 tools/circuit_breaker.py:45-47: only real breaker; wired to tools only (tools/registry.py:63,109,159)
R6 provider_router.py:91-93,423-511: 4th hand-rolled half-breaker, no HALF_OPEN, not consulted by gateway
R7 rate_limiter.py:144-163 acquire_or_wait unused
R8 core/graph.py:585-625 iteration budget
R9 shared/adapters/base.py:58-59 max_retries declared never consumed
HIGH: no circuit breaking on provider path → lift tools/circuit_breaker to shared/resilience/, wire into ProviderRegistry, delete provider_router health code
MED: registry.py:91-98 rate-limits at lookup not call time; gateway bypasses rate limiting entirely (takes pre-built dict L184)

## 4. SRP VIOLATIONS
MED: LLMGateway 6 responsibilities (routing/retry/schema+contract validation/path allowlist/budget/registry); imports GeneratorResponseContract L30 → couples transport to module-builder domain
MED: ProviderRegistry conflates class registry+instance cache+default pointer+rate limiting; RateLimiterRegistry (rate_limiter.py:196-292) is a second registry wrapping it
MED: local_provider does prompt engineering + token estimation in transport adapter
MED: rate_limiter.py 3 jobs: algorithm+registry+DEFAULT_LIMITS policy L216-222 (config data in utils; naming disagrees "anthropic" vs "claude")
LOW: json_parser _normalize_json_booleans regex rewrites True/False/None inside string literals → data corruption
LOW: OnlineProviderWrapper emits metrics inside adapter → metrics only for online path

## 5. DEAD CODE
HIGH: github_models.py unreachable via registry (no ProviderType.GITHUB_MODELS; setup.py doesn't register); 449 lines, zero prod call sites
MED: ProviderType.GEMINI/OLLAMA dead members
MED: setup.py/config.py mismatch: nvidia has config no registration (aliases OPENAI → cache collision); openclaw registered no config → provider_router.get_provider_instance L533-540 always None for openclaw
MED: 5-6 independent registry implementations (providers, rate_limiter, adapters, modules, scenarios, tools) → generic Registry[K,V]
LOW: unused API surface: base_provider generate_sync/generate_stream_sync/validate_config; registry set_default/get_default/unregister_instance/get_rate_limit_stats; llm_gateway get_routing_info/register_provider/get_job_usage/BudgetConfig.max_tokens_per_job (never enforced); rate_limiter acquire_or_wait/reset/register; json_parser extract_tool_calls; SchemaValidationError can never escape generate (except L519 continues) though docstring claims it raises
LOW: llm_gateway.py:537 attempt mislabeled as error count; query_normalization.py logger param typed Optional[object]

## TOP 6 ACTIONS
1. online_provider re-raise ProviderError before catch-all
2. Delete github_models L108-362, reparent; gateway sole retry site
3. llm_gateway asyncio.sleep; delete dead retry_after block
4. Lift circuit_breaker to shared/resilience; wire ProviderRegistry; delete router health dup
5. Delete _configure_retries; stop swallowing RpcError; fix chroma self.logger
6. Merge setup.py+config.py+orchestrator/config+provider_router env resolution into one PROVIDER_SPECS table
