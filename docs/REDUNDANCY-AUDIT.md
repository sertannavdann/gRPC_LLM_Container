# NEXUS Codebase Redundancy & SOLID Audit

**Date:** 2026-08-13 (post-Phase 7)
**Guiding document:** *Event-Driven Microservice Architecture with Orchestration: Academic Principles and Efficiency Practices* (repo root)
**Method:** Six parallel deep audits — module lifecycle, providers/clients, orchestrator/tools, auth/billing/observability/services, UI, tests/scripts/config — each producing file:line-referenced findings, synthesized here.

This is a **detection report**: nothing has been changed. Findings are grouped into themes ordered by blast radius, each mapped to the orchestration principles it violates (saga coordination, single source of truth, idempotency, event sourcing, CQRS, bounded-retry-with-jitter, observability). A prioritized remediation plan is at the end.

---

## Executive summary

| Metric | Value |
|---|---|
| Duplicated-functionality findings | ~70 (14 HIGH) |
| SRP violations (god files/classes/functions) | ~35 (12 HIGH) |
| Confirmed-dead code | **~5,500+ LOC** deletable |
| Latent functional bugs discovered while tracing duplication | 20+ (several P0) |
| Security exposures found during SRP tracing | 3 |

The single largest architectural gap, measured against the guiding document: **the module lifecycle state machine has no declared transition table and no single source of truth** — 9 scattered guards, 15 unguarded status writers, 4 status vocabularies, state persisted redundantly in two stores that never reconcile, and one documented guard bypass. Nearly every other theme (duplicate hashing, duplicate validation types, dual audit writers, saga state discarded per call) is downstream of this.

A recurring meta-pattern across all six subsystems: **the canonical helper exists and is bypassed by its own intended callers.** `compute_bundle_hash` is imported and never called; `prompt_composer.compose` has one call site; `create_auth_middleware` has zero; `LocalToolRegistry.call_tool` (the only path that feeds the circuit breaker) has zero; `json_parser.extract_tool_json` is skipped in the hot path; the UI's `lib/errors.ts` classifiers are exported and never imported. Consolidation here is mostly *adoption*, not invention.

---

## P0 — Broken behavior discovered while tracing redundancy

These are not style issues; they are live defects that the consolidation work must fix first (or fold into its first commits).

### Orchestrator / tools
1. **23 backward-compat tool aliases raise at call time.** `orchestrator/orchestrator_service.py:1038-1061` registers old names (`build_module`, `validate_module`, …) pointing at the 8 consolidated instances; any alias for a `CompositeTool` dispatches to `__call__` without the required `action` → `ValueError`. Meanwhile `core/graph.py:30-49` (`MODULE_BUILDER_SYSTEM_PROMPT`), `orchestrator/intent_patterns.py:99-164` (`required_tools`), and the few-shot examples at `orchestrator_service.py:459-473` still *teach the LLM the broken alias vocabulary*.
2. **All 31 registered tools export a degenerate schema.** `tools/registry.py:315-356` reflects on `__call__(self, **kwargs)` → every tool's OpenAI schema is `{"properties":{"kwargs":{"type":"string"}},"required":["kwargs"]}`. `BaseTool.get_schema()`/`CompositeTool.get_schema()` (`tools/base.py:326-337,453-468`) are never consulted.
3. **The max-10 repair cap is unenforceable and `action='repair'` is uncallable.** `module_builder.py:399-445` checks `len(audit_log.attempts)` but the only production caller (`shared/modules/approval.py:177`) constructs a *fresh* `BuildAuditLog` each rejection (count always 0). `module_pipeline.py:49-56` passes LLM JSON kwargs to a signature requiring a `BuildAuditLog` object → unconditional `TypeError` from the chat surface.
4. **Circuit breakers can never trip.** `core/graph.py:437-440` (`_tools_node`) bypasses `LocalToolRegistry.call_tool` — the only code path that calls `breaker.record_success()/record_failure()` (`tools/registry.py:185-205`). `call_tool` has zero production callers.
5. **217 lines of duplicated admin endpoints with divergent RBAC.** `orchestrator/admin_api.py:1696-1913` re-registers 8 draft/version endpoints already defined at `:680-864`; FastAPI keeps the first match, so the second block is unreachable — but the duplicate `get_draft_diff` pair carries *different* auth (`require_permission(MANAGE_MODULES)` at `:745` vs bare `get_current_user` at `:1766`), and `GET /admin/modules/{module_id}/versions` (`:1886`) is shadowed by `/admin/modules/{category}/{platform}` (`:304`) and 404s.
6. **Metering identity is lost.** `orchestrator_service.py:1642-1650` calls `create_initial_state()` without `org_id`/`user_id` (computed at `:1514`) → all audit actors become `"chat_agent"`, all billing lands on `"default"`. Also `:1712` reads `duration_ms` but `ToolExecutionResult` (`core/state.py:151`) emits `latency_ms` → the tool-duration histogram never records. And `core/graph.py:492` reads `state.get("tier")` — never a state key → tiering permanently `"standard"`.

### Providers
7. **Auth errors are retried 5×.** `shared/providers/online_provider.py:111-113` (and `:171-173` for streaming): `ProviderAuthError`/`ProviderRateLimitError` raised inside the `try` are swallowed by the bare `except Exception` and re-raised as `ProviderConnectionError`, which `llm_gateway.py:393` classifies as transient. Every OnlineProvider subclass (openai, perplexity, openclaw, anthropic) retries invalid API keys.
8. **`llm_gateway` blocks the event loop.** `llm_gateway.py:421` calls `time.sleep()` inside `async def`; the `retry_after` branch at `:399-407` is dead code (hardcoded `None`).
9. **The Anthropic provider speaks the wrong wire protocol.** `anthropic_provider.py` overrides only headers; it POSTs an OpenAI payload to `{base_url}/chat/completions` and parses `choices[0].message` — not Anthropic's `/v1/messages` + `content[]`. Its `name="claude"` also mismatches `ProviderType.ANTHROPIC.value="anthropic"`, breaking rate-limiter keying (`rate_limiter.py:216-222`).
10. **`openclaw_provider._get_headers` (L100-114) is a dead override** — the base calls `_build_headers`, so every request sends `Authorization: Bearer openclaw`.
11. **`chroma_client.py:45,68` references `self.logger`, which `BaseClient` never defines** → `AttributeError` on any gRPC error.

### Data/contract correctness
12. **Invalid timestamps at 18 sites.** `datetime.now(timezone.utc).isoformat() + "Z"` produces `...+00:00Z` (not ISO-8601) across `drafts.py`, `approval.py`, `audit.py`, `versioning.py`, `artifacts.py`, `gc.py`, `validation_types.py` — and the project's own validator (`output_contract.py:55-63`) rejects it. Three formats coexist (see D5 in Theme 1).
13. **Two of five generated modules are runtime-broken.** `modules/gaming/testgame/adapter.py:44,48,53,65` and `modules/test/srccheck/adapter.py:44,48,53,66` contain double-escaped braces (`headers = {{}}` → set-of-dict `TypeError`; `f"Bearer {{api_key}}"` → literal). Nothing gates generated code on `ast.parse` + instantiation.
14. **Generated test template imports the wrong enum.** `test_template.py:120` imports `ErrorCode` from `output_contract` but the generated body references `ErrorCode.MISSING_METHOD`, which exists only in `contracts.py` → generated tests `AttributeError`.
15. **`DevModeAuditLog.get_events` returns the oldest events while claiming "most recent"** (`shared/modules/audit.py:445-485`).

### UI
16. **The `dataSource` region of `nexusAppMachine` is permanently dead.** `ENVELOPE_LOADED`/`ENVELOPE_ERROR`/`CONFIG_VERSION_CHANGED`/`PREFS_LOADED` are declared but never sent (`nexusApp.ts:38-44,102-132,262-290`) → `isLive/isMock/isOffline` always false (`useNexusApp.ts:81-84`); dashboard always renders "unknown".
17. **The monitoring topology is fabricated.** `ServiceTopology.tsx:144-151` relabels contract features to unrelated service names (providers→"Orchestrator", adapters→"ChromaDB", …), injects a hardcoded-healthy "Bridge" node, and substitutes a 7-node fake topology when features are sparse. `monitoringPage.ts:86-108` returns fabricated healthy/degraded statuses on fetch failure. `Navbar.tsx:99-104` shows a hardcoded green "Connected" dot. This directly violates the Phase 6 invariant *"the backend capability contract is the single source of truth."*
18. **Finance charts render mock data.** `SpendingChart.tsx:179-200` mock generators are the *only* source for `app/finance/page.tsx:266-267`; real transactions in context are ignored.

### Security (found while tracing auth scatter)
19. **`bridge_service` has zero authentication** on `POST /tools/execute_code` and `/rpc tools/call` (`mcp_server.py:235-250,614-621,820-841`) — an unauthenticated code-execution surface.
20. **`sandbox_service` gRPC has no identity** (`sandbox_service.py:264-303`) — no metadata inspection, no interceptors; usage attributed to `"default"`.
21. **Dashboard credential endpoints skip RBAC.** `dashboard_service/main.py:847,866,909,962` gate credential write/delete with bare `get_current_user` (any viewer), and `:878-883` has *no* auth dependency — while the orchestrator gates the same operations with `require_permission(MANAGE_CREDENTIALS)`. Also `main.py:342-353` makes `/context/*` (per-user data) fully public.

---

## Theme 1 — Module lifecycle: no declared FSM, no single source of truth

**Principles violated:** single source of truth per state; orchestration-based saga (declared transitions); event sourcing as authority.

`ModuleStatus` (`shared/modules/manifest.py:16-25`) declares 8 states; legal transitions exist only in prose.

**Guards (read+reject), 9 sites:** `approval.py:89` (doubled enum/value comparison — `status` is typed `str` but assigned enums), `module_installer.py:91,98` (same doubled comparison, copy-pasted), `loader.py:84`, `drafts.py:232,478,616` (parallel `DraftState` FSM), `versioning.py:340` (string literal, third vocabulary), `module_validator.py:280` (string literal, fourth vocabulary).

**Unguarded writes, 15 sites:** `approval.py:100,161,208`; `loader.py:163,177,216,246,272` — the *loader* (a read path) writes `INSTALLED`/`FAILED`/`PENDING`, bypassing approval entirely; `registry.py:70,109/113` (raw SQL, mutates caller's manifest as a side effect); `module_validator.py:264`; `module_installer.py:185,248`; `module_builder.py:246,386`; and `tools/nexus_dev.py:239` — a dev tool writing `VALIDATED` directly, explicitly commented as a bypass of the install guard.

**Two stores, no reconciliation:** status lives in `manifest.json` (`manifest.py:78`) *and* the `modules.status` SQLite column (`registry.py:46`). `registry._update_status` updates the DB without the manifest; `loader.py:163` updates the manifest without the DB.

**Two FSMs that can't legally connect:** `DraftState` (`drafts.py:27-34`) has no mapping to `ModuleStatus`; `promote_draft` calls `install_module`, which requires `APPROVED` — a status the draft FSM cannot produce. A validated draft can *never* install without the out-of-band manifest edit that `nexus_dev.py:239` performs. This is the exact gap the Phase 8 approval work needs closed.

**Fix (highest-leverage single change in the codebase):** declare one `TRANSITIONS: dict[ModuleStatus, set[ModuleStatus]]` plus a single `transition(module_id, to_status, actor)` function that validates, persists to **one** store, and emits the audit event. Route all 15 writers through it; delete the 9 ad-hoc guards; map `DraftState` onto `ModuleStatus` at the promote boundary.

### Supporting duplication in the same subsystem
- **Bundle hashing implemented 4×** — canonical `compute_bundle_hash` (`hashing.py:23-47`) is imported by `artifacts.py:16` and never called; inline copies at `artifacts.py:144-165,309-318`; raw `hashlib.sha256` at `drafts.py:158,251`; truncated-fingerprint idiom duplicated at `audit.py:79` and `audit/redaction.py:29`; a fourth entry point at `audit/store.py:83-84`.
- **"Collect the 3 module files → build bundle" verbatim ×3** — `approval.py:36-54`, `drafts.py:520-531`, `module_installer.py:123-140`; the file triple hardcoded in 4 places. → `ArtifactBundleBuilder.build_for_module()` + `MODULE_BUNDLE_FILES`.
- **`parse_module_id` exists (`identifiers.py:29-76`) but 8 call sites re-split inline** (`gc.py:46`, `approval.py:21,36`, `drafts.py` ×4, `loader.py:264`, `nexus_dev.py:184`), three without length checks; `Path(modules_dir)/category/platform` open-coded at 10 sites.
- **Timestamps: 3 incompatible formats at 25+ sites** (see P0-12). → one `utc_now_iso()`.
- **Four overlapping validation-result types:** legacy `ValidationResults` (`manifest.py:29-43`), dead `ValidationResult/Entry` (`validation_types.py` — zero production importers despite claiming "single source of truth"), the real `ValidationReport` (`module_validator.py:49-120`), and ad-hoc `{"valid": bool}` dicts (`contracts.py:147,297`) — with *two* manual translation layers in `module_validator.py:252-330`.
- **Three overlapping result envelopes:** `AdapterRunResult` (`output_contract.py:113-190`, claims "all adapters must return" — no adapter imports it), `AdapterResult` (`adapters/base.py:63-88`, the real one), `ToolResult` (`tools/base.py:53-92`), plus ad-hoc status dicts throughout drafts/approval/versioning/installer.
- **`manifest_schema.json` is incompatible with `ModuleManifest`** — zero overlap on required keys; every real manifest fails its own published schema; the "schema check" (`module_validator.py:381-393`) never opens the file.
- **`StaticImportChecker` emits strings; `contracts.py:49-76` string-parses them back** into structure — lossy round-trip; `sandbox_service/runner.py` is a third consumer with a fourth forbidden-import implementation (`shared/agents/confidence.py:315`).

### SRP splits needed
- **`DraftManager` (700 LOC, 6 jobs)** — FS management, hashing, diffing, validation orchestration, install orchestration, 7 inline audit blocks. `validate_draft` writes scratch state *inside the live modules tree* (`drafts.py:496`) — a crash leaves a phantom `{category}_draft_*` dir that `manifest.discover()` will load. → `DraftStore` / `DraftValidator` (tmpdir outside modules_dir) / `DraftPromoter`.
- **`reject_module` (`approval.py:120-231`)** branches repair-vs-terminal on truthiness of free-text feedback, drives an LLM repair cycle inline, swallows all exceptions with the manifest already persisted `VALIDATING` — a partial transition with no compensation. → split + emit `ModuleRejected` event.
- **`ModuleLoader.load_module`** executes arbitrary code *and* rewrites lifecycle state (`loader.py:163,177`). CQRS: the read path must not write.
- **`ModuleManifest`** is DTO + repository + discovery (`manifest.py:114-146`). → extract `ManifestRepository`.

---

## Theme 2 — Resilience: 9 retry/backoff/breaker implementations, one correct

**Principles violated:** bounded retry with jitter + per-error-class policies (guiding doc §5.2: jitter reduces P99 2600→1400ms, error rate 17%→6%); circuit breaking on the provider path.

| # | Location | Jitter | Error classes | Status |
|---|---|---|---|---|
| R1 | `llm_gateway.py:36-70,349-433` | yes | yes | The **one correct policy** — but blocks the event loop (P0-8) |
| R2 | `github_models.py:235-362` | no | yes | Recursive, uncapped; **nests inside R1 → up to 15 upstream calls** |
| R3 | `base_client.py:13-17` tenacity | no | none | **Inert**: monkey-patches all public attrs incl. generators, while every client swallows `grpc.RpcError` and returns sentinels — tenacity never sees an exception |
| R4 | `base_client.py:35` `grpc.enable_retries=1` | — | — | Third layer, no service config → no policy |
| R5 | `tools/circuit_breaker.py:45-47` | — | — | The only real breaker; wired to tools only, **and never fed** (P0-4) |
| R6 | `provider_router.py:423-511` | — | — | Hand-rolled half-breaker, no HALF_OPEN, consulted by nobody (file is dead, Theme 8) |
| R7 | `rate_limiter.py:144-163` | no | — | Unused |
| R8 | `core/graph.py:585-625` | — | — | Iteration budget masquerading as retry |
| R9 | `adapters/base.py:57-59` | — | — | `max_retries`/`retry_delay_seconds` **declared, never read**; `fetch()` has no retry despite docstring claims |

**Five independent retry counters** govern the build saga with no shared policy: `MAX_REPAIR_ATTEMPTS=10` (`module_builder.py:57`), `module_build_max_iterations=10` (`state.py:82`), `max_iterations=5` (`state.py:81`), `max_tool_iterations` (`orchestrator_service.py:338`), gateway `max_retries=5`. The repair loop itself has **no backoff, no jitter, no per-error-class delays** — while `llm_gateway._compute_backoff` implements exactly that, unused by the pipeline.

**Rate limiting is bypassed entirely:** `providers/registry.py:91-98` acquires a token at *lookup* time, then caches the instance; `llm_gateway` never calls `get_provider` at all (takes a pre-built dict at `:184`).

**Fix:** promote `_compute_backoff` → `shared/resilience/retry.py`; promote `tools/circuit_breaker.py` → `shared/resilience/`; wire the breaker into `ProviderRegistry` and consult it in `_call_provider_with_retry`; delete R2/R3/R4/R6/R7; move rate-limit acquisition into `BaseProvider.generate`; one `RetryPolicy` object threaded through graph + pipeline + gateway.

---

## Theme 3 — Three parallel "call an LLM with fallback" routers

**Principle violated:** orchestration demands one coordinator with process visibility; three routing tables = three sources of truth.

1. `shared/providers/llm_gateway.py:435-575` — purpose-lane routing + fallback + retry + schema validation + budget.
2. `orchestrator/provider_router.py:193-455` — complexity heuristic + `FALLBACK_CHAIN` + health tracking. **Entirely dead** (exported, imported nowhere) — 636 lines.
3. `shared/clients/llm_client.py:194-213` — tier ladder with its own fallback semantics.

Supporting duplication: the async→sync bridge exists 3× (`base_provider.py:145-188` zero call sites + per-call event loops; `orchestrator_service.py` `OnlineProviderWrapper` thread-local — the correct one; `module_builder.py:114-140`); message→prompt flattening exists as 4 divergent templates hitting the same model (`local_provider.py:160-188` plain-text, `openai_wrapper.py:97-115` ChatML, `online_provider.py:246-251` ≡ `github_models.py:168-173` dict-loop, `orchestrator_service.py:~225` role-collapse); token counting via `split()` twice; `github_models.py:108-233` is a wholesale copy of `online_provider.py:60-303` and is **unreachable through the registry** (no `ProviderType.GITHUB_MODELS`, not registered in `setup.py` — 449 lines, zero production call sites); `airllm_service.py:108-254` duplicates `llm_service.py:145-295` wholesale (same 4 RPCs, third majority-vote copy, hardcodes metadata `model_registry` already declares); provider config resolution exists 3× with divergent coverage (`providers/config.py`, `orchestrator/config.py:87-99`, `provider_router.py:363-374`) and `setup.py`/`config.py` disagree (`nvidia` configured-not-registered and colliding with `openai` on one cache slot; `openclaw` registered-not-configured → `get_provider_instance` always `None`).

**Fix:** gateway owns model selection; delete `provider_router.py`; `LLMClientPool` degrades to transport; one `PROVIDER_SPECS` table merging `setup.py` + both config loaders; delete or reparent `github_models.py`; extract `BaseLLMServicer` for llm_service/airllm; one `format_messages()` and one shared `AsyncBridge`.

---

## Theme 4 — Build pipeline is not a saga

**Principles violated:** orchestration-based saga with persisted state and compensations (guiding doc §7.1); idempotency (§5.3).

- **`BuildSession` is discarded on return** (`module_builder.py:143-163`, instantiated `:228`) — never persisted, never advanced past `"scaffold"`, never passed between stages. Stage ordering is emergent from LLM tool-call ordering; there is no coordinator to reject out-of-order transitions.
- **The documented `implement` and `tests` stages don't exist** — docstrings (`module_builder.py:4-8,180-185`) promise LLM-gateway generation; in practice the conversational LLM emits code into `write_module_code` and tests come from the scaffold template.
- **No compensation anywhere:** repair patches files in place (`:583-585`) — mid-loop failure leaves the module half-patched; scaffold leaves its directory behind on later failure, tripping its own "already exists" guard (`:211-216`). Three unrelated "undo" mechanisms exist (`gc.queue_for_gc`, `uninstall_module`, versioning rollback), none invoked by the pipeline. → per-stage `compensate()` table; patch to tmpdir + atomic swap.
- **No idempotency keys on any mutation** (guiding doc lists this as non-negotiable): retried approvals append duplicate audit rows; `record_version` mints `strftime`-based IDs so retries duplicate version rows.
- **The confidence gate is absent:** `Blueprint2CodeScorer` constructed at `module_builder.py:64`, never invoked; all 337 lines of `shared/agents/confidence.py` dead.
- What *is* healthy: `FailureFingerprint` / `classify_failure_type` (`shared/modules/audit.py:54-272`) are genuinely centralized — the model to follow. Move `MAX_REPAIR_ATTEMPTS` next to them.

---

## Theme 5 — Metering/billing: computed, persisted, and emitted in different files

**Principle violated:** CQRS — one write model; also observability (metrics that silently never record).

- Run-units: computed `run_units.py:33-87` (3 entry points) → computed+persisted inline in the graph's tool node (`core/graph.py:490-513`, fail-open, inside a LangGraph node writing SQLite) → re-read and emitted as metrics in `orchestrator_service.py:1705-1739` (where the `duration_ms`/`latency_ms` drift kills the histogram, P0-6) → independently re-normalized in `otc_reward.py:78` → stored in a second disjoint table by `otc_policy_store`.
- **Three `UsageStore` instances** against one DB (`graph.py:101`, `orchestrator_service.py:1113`, `admin_api.py:2069`).
- **Quota:** `QuotaManager` resolves plan by reaching into the *auth* store (`quota_manager.py:45-53`), issues 2 connections + 4 queries per check (`get_period_total` fully subsumed by `get_usage_summary`), and enforcement lives in two other files with different semantics (`orchestrator_service.py:1536-1555` fail-open; `admin_api.py:1282` hardcodes org `"default"`).
- Metering is fail-open (`graph.py:510-511`) while audit is fail-closed — opposite failure contracts for the two ledgers with no stated policy.

**Fix:** one `MeteringService.meter(tool_result, ctx)` (compute → record → emit) called from a `MeteringHook` on the graph node; one injected `UsageStore`; split `QuotaPolicy` (pure decision) from enforcement (one place, one message); introduce an `OrgDirectory` port to break billing→auth.

---

## Theme 6 — Audit: two writers, two shapes, three failure semantics

**Principle violated:** event sourcing — one append-only authority (Phase 7's whole point).

- `shared/audit/store.py` (hash chain, append-only triggers, fail-closed) is correct and well-built — but it is a *side-log*: state changes commit first, events after; nothing replays; `iter_events` has no caller.
- `DevModeAuditLog.log_action` (`shared/modules/audit.py:384-443`) dual-writes JSONL then a *differently-shaped* record to `AuditStore` with lossy field remapping — no atomicity, and the two rows can record **different actors** for the same action. The JSONL side has no hash chain.
- Two `AuditEvent` schemas (`audit.py:317-345` vs `store.py:139-153`); `_client_ip` copy-pasted (`context.py:62-68` ≡ `decorator.py:28-34`); `audit_action` couples audit to FastAPI (`HTTPException` at `decorator.py:135`) — which is *why* the parallel dev-mode path exists; three failure semantics (fail-closed / 500-after-mutation / JSONL-committed-then-raise).
- Same mutation, two audit mechanisms: REST enable/disable uses `@audit_action` (`admin_api.py:337-392`) while chat enable/disable uses `_record_mutation` (`module_admin.py:111-161`).

**Fix:** one `AuditEvent` type; `AuditStore` the sole writer; JSONL becomes an export of `iter_events()`; a transport-agnostic decorator; both surfaces call one `ModuleLifecycleService` that owns mutation + audit (this is also where Theme 1's `transition()` lives).

---

## Theme 7 — Cross-service boilerplate & persistence copy-paste

**Principle violated:** don't re-implement the platform per service; observability from day one.

- **Nine near-identical SQLite `_connect()` implementations with divergent pragmas** — 3 byte-identical, 3 missing WAL entirely, docstrings openly chaining four generations of "follows the SQLite pattern from …" (`api_keys.py`, `usage_store.py`, `otc_policy_store.py`, `audit/store.py`, `user_prefs.py`, `modules/registry.py`, `credentials.py`, `versioning.py`, `core/checkpointing.py`). **No migration mechanism anywhere** (no `PRAGMA user_version`); ad-hoc `ALTER TABLE org_id` try/excepts per store; `org_id`-branch SQL duplicated 9×; JSON-column rehydration duplicated 3× within `versioning.py`. → `shared/storage/sqlite_base.py` (connect + pragmas + migrations + `_row_to_dict` + filter builder).
- **App wiring copy-pasted:** dashboard re-implements `setup_observability` (divergent fork, `main.py:67-101`); auth+audit+CORS middleware block byte-identical between `main.py:331-367` and `admin_api.py:2064-2100` (comment included) and copied into test fixtures; `create_auth_middleware` has zero callers; every service calls `logging.basicConfig` instead of `configure_logging` (no correlation/trace IDs anywhere); gRPC bootstrap duplicated 5× and only the orchestrator attaches the observability interceptor (`create_server_interceptors` has no callers; the streaming wrapper is a documented no-op). → one `create_nexus_app()` / `serve_grpc()` factory.
- **Metrics:** dashboard runs a parallel raw-Prometheus system (6 instruments, 4 never written — permanently-zero series) beside shared OTel; bridge hand-rolls counters in dicts; latency measured 5+ independent ways (including wall-clock `time.time()` and a black-box HTTP percentile prober duplicating server-side histograms); `metrics.py` is 8 near-identical factories + 5 module-level gauge globals. → shared instruments, declarative `MetricSpec`.
- **God files:** `dashboard_service/main.py` (1105 ln, 9 jobs), `MCPServer` (routing + 270-line inline schema literal + 8 tool impls + lifecycle; rebuilds handler/validator dicts **on every call**), `sandbox_service.py` (56-line code-template f-string inline), `orchestrator_service.py` (1873 ln, 3 unrelated classes, 300-line `__init__` service locator), `admin_api.py` (2287 ln, all routers + uvicorn bootstrap), `_process_query` (250 ln). → routers/composition roots.
- **Two sandbox engines:** the gRPC servicer uses subprocess `execute_in_sandbox` while `runner.py` (405 ln, in-process `exec()`) serves only `module_validator` — with **duplicated and divergent import allowlists** (15 vs 22 modules), duplicated resource clamps, and `policy.py` (357 ln) never guarding real gRPC traffic. `runner.py` imports `StaticImportChecker` and hand-rolls its own AST walk instead; its network-violation plumbing is never populated.
- **Presentation rules drifted:** HRV alert threshold is `<40` in `formatters.py:92,251` but `<30` in `relevance.py:198`; four summary builders; `tools/builtin/user_context.py:118` imports `dashboard_service.formatters` **across the service boundary** with a silent fallback. → one `alert_rules.py`.
- `bank_service` filter chain copy-pasted 3× (search matches different fields per copy).

---

## Theme 8 — Dead code inventory (~5,500+ LOC)

Safe-delete candidates (verified zero production call sites by the audits; re-verify locally before deleting):

| Area | Item | LOC |
|---|---|---|
| Providers | `github_models.py` (unreachable) | 449 |
| Providers | `provider_router.py` (imported nowhere) | 636 |
| Orchestrator | `admin_api.py:1696-1913` duplicate endpoints | 217 |
| Orchestrator | `orchestrator/rl/` (nothing imports; hard torch dep not in requirements) | 705 |
| Orchestrator | `worker_adapter.py` (mesh removed) | 103 |
| Orchestrator | `core/self_consistency.py` (constructed, never called) | 210 |
| Agents | `shared/agents/confidence.py` (never invoked) | 337 |
| Tools | `web_search.py`, `web_loader.py`, `finance_query.py`, `module_manager.py` (minus 3 setters), `decorators.py`, `BaseToolLegacy`, idempotency machinery | ~1,300 |
| Modules | `validation_types.py`, `scenarios/**`, `policy.py` scaffold, `manifest_schema.json`, dead artifact methods, `SAFE_BUILTINS` | ~450 |
| Billing | `otc_reward.py` + `otc_policy_store.py` (zero callers, not exported) + `latency_snapshot.py` | ~608 |
| Sandbox | `runner.py` orphan engine (pick one) + dead symbols | ~420 |
| Scripts/tests | `scripts/track_*.sh`, `test_inference_speed.py`, `tests/evals/` (mock-only runner), UI duplicate contract test, `CONTRACT_TEST_TEMPLATE` | ~1,400 |
| UI | `SettingsPanel.tsx` (superseded), `ModuleNode.tsx`, dead machine surface, unused lib exports | ~600 |

Note the pattern: several "dead" items are the *designed* mechanism that was never wired (`confidence.py` gate, `self_consistency`, `should_continue_tool_loop`, `policy.py` auto_approve, idempotency cache, `create_auth_middleware`, `create_server_interceptors`). For each, decide **wire it or delete it** — do not leave aspirational code in place.

---

## Theme 9 — UI: duplication + contract bypass

Beyond P0-16/17/18:

- **Types:** `NexusErrorType` declared twice with different members; `Transaction` ≡ `FinancialTransaction`; settings/provider types redeclared per page (`ConnectionTestResult` ×3); adapter response types redeclared in `IntegrationsPanel`; backend status enums mirrored 5× as raw string maps. → one contract types module.
- **API clients:** `adminFetch` bypassed by its own module for ETag calls; **five base-URL derivations with conflicting defaults** (incl. `useUserPrefs` bypassing the `/api/admin` proxy entirely, and server routes defaulting to `orchestrator:8003` vs `localhost:8003`); ~20 copies of `catch(err){setError(err.message)}` with `classifyError` unused; two adapter API routes with two hardcoded registries and **two incompatible POST payload contracts on one endpoint**; three orchestrator-restart client variants. → `lib/http.ts` + `lib/endpoints.ts` + `lib/capability-selectors.ts`.
- **Machines:** health/latency polling regions structurally identical (→ `createPollingRegion` factory); three independent fetch actors; dead guards/actions in all three machines; hardcoded timing literals beside an unused `runtime-params.ts`; API DTOs declared inside machine files and imported by components; the pipeline page skips XState entirely (Zustand + a 140-line layout `useEffect`) — inconsistent with the machine-driven pages.
- **Components:** two `ServiceNode`s (same name, incompatible props); three adapter-management UIs on one endpoint (one literally redirects to the other for credentials); four status-badge implementations; six widgets duplicating identical shell chrome; two Zustand stores both named `nexusStore` in `store/` vs `stores/` (runtime `import()` to dodge the resulting cycle); duplicated Recharts theme config; 6-8 mutually inconsistent date/relative-time formatters.
- **SRP:** `settings/page.tsx` 700 ln / 20 useState; `IntegrationsPanel` 473 ln; `ChatContainer` 444 ln / 6 jobs; `Dashboard.tsx` twin 6-branch switches (→ widget registry); layout algorithm inside the pipeline page (→ pure `pipelineToFlow()`).

---

## Theme 10 — Tests, scripts, config

- **The admin test double:** `tests/integration/admin/conftest.py:43-599` hand-rewrites ~26 production endpoints (because `admin_api.py` can't be imported standalone — itself a symptom of Theme 7's missing app factory); two more hand-rolled copies in `tests/auth/`. Tests also re-implement prod logic (ETag, audit CSV escaping) so prod fixes aren't covered. → `create_admin_app(deps)` factory kills ~700 lines of drift-prone doubles.
- **~40 fixture redeclarations** across conftest islands (mock_loader ×4, module factory ×5, tmp-db/store ×8, installer-deps reload dance ×3, docker/agent harness ×4, 22 copies of an 8-line httpx mock…); two fixtures named `modules_dir` with *different contracts*; no `pytest.ini` (markers registered in one sub-conftest); `__init__.py` convention inconsistent. → `tests/helpers/` + root conftest + `pytest.ini`.
- **A whole feature-test tier asserts nothing:** `tests/feature/test_{auth_api_key,rate_limit_429,oauth_refresh,pagination_cursor}.py` assert on their own mocks' configured values; no production code executes.
- **Config truth scattered:** Makefile defines `PORT_*` vars then hardcodes the same numbers 50+ times; `PORT_UI` means 3000 and 5001 in the same file; compose sets `BRIDGE_PORT` which nothing reads (reader wants `MCP_PORT`); **default model name declared 4+ ways, two contradictory inside `orchestrator/config.py` itself** (`:54` 3b vs `:153` 0.5b) and `core/state.py:88` says Mistral-24B; `AUDIT_DIR` defaults differ between builder (`/app/data/audit`) and installer (`data/audit`) so they write to different dirs when unset; `MODULES_DIR` global declared 4×; model catalogue duplicated (and internally inconsistent) in `routing_config.json`; test-tier orchestration in 3 places (Makefile ×2, verify.sh); Makefile health probes ×4; 484 lines of orphaned `track_*.sh`.
- **Template drift:** all 5 on-disk modules predate the current template (none has the `get_schema()` the template now emits); per-module boilerplate (~35 ln `__init__`/`transform`, `get_capabilities`, 90-ln test file) belongs in a shared `HttpJsonAdapter` + `testkit.assert_adapter_contract`; generated tests are never collected by any harness; template emits deprecated `asyncio.get_event_loop()`; two runtime-broken modules (P0-13) prove the missing `ast.parse` gate.

---

## Remediation plan (phased, for local CLI execution)

Ordered so each phase makes the next cheaper. Rough sizes assume focused sessions.

### Phase R0 — Correctness triage (no refactoring; small diffs)
1. Providers: re-raise `ProviderError` before the catch-all (`online_provider.py:111,171`); `asyncio.sleep` in gateway `:421` + delete dead `retry_after` block; rename openclaw `_get_headers`→`_build_headers`; fix `chroma_client` logger; quarantine or fix `anthropic_provider`.
2. Orchestrator: delete alias block `:1038-1061` (or wrap with action-injecting lambdas); make registry use `tool.get_schema()`; rewrite `MODULE_BUILDER_SYSTEM_PROMPT` + `intent_patterns.required_tools` + few-shot examples to the 8-tool vocabulary; route `_tools_node` through `registry.call_tool`; pass `org_id`/`user_id` into `create_initial_state`; fix `latency_ms` field name; delete `admin_api.py:1696-1913` keeping stricter RBAC.
3. Repair saga: load-or-create `BuildAuditLog` by `job_id` inside `repair_module`; drop it from the signature (makes `action='repair'` callable and the cap real).
4. Data: `utc_now_iso()` helper, fix 18 `+00:00Z` sites; fix test-template `ErrorCode` import; regenerate/delete the two broken generated modules; add `ast.parse` + instantiation gate to the validator.
5. Security: API-key middleware on bridge; gRPC auth interceptor on sandbox; `require_permission(MANAGE_CREDENTIALS)` on dashboard credential endpoints; remove `/context` from public paths.
6. UI: wire or delete the `dataSource` region (raise events from `pollCapabilities.onDone`); remove fabricated topology/mock-on-failure/hardcoded Connected dot; render real transactions in finance charts.

### Phase R1 — The FSM (Theme 1)
Declare the `ModuleStatus` transition table + single `transition()` writer with one persistence authority; route all 15 writers; delete 9 guards; map `DraftState`→`ModuleStatus` at promote; make `ModuleLifecycleService` the shared surface for REST + chat (folds in Theme 6's single audit path). This unblocks Phase 8 approval cleanly.

### Phase R2 — Shared platform primitives (Themes 2, 7)
`shared/storage/sqlite_base.py` (9 stores); `shared/resilience/{retry,circuit_breaker}.py` wired into `ProviderRegistry`; `create_nexus_app()` / `serve_grpc()` factories (dashboard, admin API, bridge, sandbox, llm, chroma); `configure_logging` everywhere; one metrics surface; `PROVIDER_SPECS` table; `alert_rules.py`.

### Phase R3 — Single owners (Themes 3, 4, 5)
Gateway as sole router (delete `provider_router.py`); persisted `BuildSession` saga with compensation table + idempotency keys; `MeteringService` + `QuotaPolicy`/enforcement split; one `UsageStore`; `BaseLLMServicer`; shared `format_messages` + `AsyncBridge`; one `QueryClassifier` replacing the four keyword classifiers.

### Phase R4 — Dead-code sweep (Theme 8)
Wire-or-delete decisions first (confidence gate, self-consistency, loop gating, idempotency cache), then delete the ~5,500 LOC inventory. Repoint the tests keeping the superseded tools alive.

### Phase R5 — UI consolidation (Theme 9)
Contract types module; `lib/http.ts`/`endpoints.ts`/`capability-selectors.ts`/`status.ts`/`format.ts`; `createPollingRegion`; delete superseded components; merge the twin `nexusStore`s; `pipelineToFlow()`; split the god pages.

### Phase R6 — Tests & config (Theme 10)
`create_admin_app(deps)` factory + delete test doubles; `tests/helpers/` + root `pytest.ini`; `tests/endpoints.py`; Makefile port vars + health-probe recipe; `config/models.json`; `shared/modules/paths.py`; `HttpJsonAdapter` + `testkit`; fix or delete the tautological feature tier.

---

*Detailed per-subsystem raw findings (with every file:line) are preserved in the audit working notes; this document is the synthesized single source. Verify each "zero call sites" claim with a grep before deleting — the audits were thorough but the codebase moves.*
