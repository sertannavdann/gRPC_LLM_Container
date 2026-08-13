# NEXUS orchestrator/agents/tools/core — Redundancy & SRP Audit

## 1. TOOL CONSOLIDATION LEFTOVERS (27→8)
HIGH orchestrator_service.py:1038-1061 — 23 backward-compat aliases point same 8 instances at old names; aliases for CompositeTools BROKEN at call time (dispatch to __call__ requiring action → ValueError). Delete or wrap with action-injecting lambdas.
HIGH tools/registry.py:315-356 — _extract_schema inspects __call__(**kwargs) → ALL 31 tools export schema {"properties":{"kwargs":{"type":"string"}},"required":["kwargs"]}. BaseTool.get_schema()/CompositeTool.get_schema() (base.py:326-337,453-468) never consulted. → register should call tool.get_schema().
HIGH web_search.py (149 ln) fully re-implemented in web_tools.py:59-123; zero prod importers → delete.
HIGH web_loader.py (231 ln) dup of web_tools:127-209,251-264; extract_metadata same name INCOMPATIBLE signatures (url vs html) → delete.
HIGH finance_query.py (212 ln) dup of user_context.py:300-362; _format_transactions byte-identical; zero prod importers → delete.
HIGH module_manager.py:36-138 bodies duplicated verbatim into module_admin strategies; only 3 set_* globals still consumed (orchestrator_service.py:83-85,973-975) → move setters, delete rest.
HIGH core/graph.py:30-49 MODULE_BUILDER_SYSTEM_PROMPT instructs LLM to call pre-refactor names (= broken aliases) → rewrite against module_pipeline(action=…).
HIGH intent_patterns.py:99-164 required_tools list old names, injected into prompt + drives loop gating → update to 8 canonical names.
MED orchestrator_service.py:459-473 few-shot examples hardcode old names (3rd survival of old vocabulary) → generate from registry.to_openai_tools().
MED module_pipeline.py:33-95 all 5 strategies pure delegation shims; constructor DI cosmetic (injected deps stored-and-ignored; real deps via module globals).
MED module_validator.py:49-131 re-implements validation_types.py:12-100 (which has zero prod importers).
MED module_validator.py:395-405 _check_path_allowlist + _check_syntax :326 re-implement checks in module_builder:356 / AdapterContractSpec.
MED contracts.py vs output_contract.py two ErrorCode enums same name disjoint members.
MED tools/base.py:131-176 BaseToolLegacy zero subclasses → delete.
MED tools/decorators.py (288 ln) entirely dead; @tool error wrapper is 3rd copy of status/error normalization (BaseTool.execute base.py:294-320, registry.call_tool :171-212) → delete.
LOW tools/base.py:474-681 idempotency machinery (compute_idempotency_key/IdempotencyCache/@idempotent) zero call sites → delete or wire into _tools_node.
LOW knowledge_search.py:27-38 ≡ knowledge_store.py:27-38 _get_client dup; split AGAINST consolidation direction → merge KnowledgeTool(action=…).

## 2. DUPLICATED ORCHESTRATION LOGIC
HIGH orchestrator_service.py:422-542 vs core/graph.py:384-522 — TWO independent tool-calling loops; wrapper bails after iteration 1 "for the graph" leaving ~40 unreachable loop lines (:502-541) → make wrapper stateless single-shot; graph owns iteration.
HIGH core/graph.py:437-440 _tools_node bypasses registry.call_tool → breaker.record_success/failure NEVER invoked in production; circuit breakers can never trip; call_tool zero prod callers → route through call_tool.
HIGH THREE UsageStore instances same DB: graph.py:101-103, orchestrator_service.py:1113-1115, admin_api.py:2069; metering written in _tools_node (graph:490-513) and re-read/re-emitted in _process_query (:1705-1738) → one injected instance.
HIGH orchestrator_service.py:1712 reads tr.get("duration_ms") but ToolExecutionResult (core/state.py:151) emits latency_ms → tool_duration_ms histogram always skipped. Field-name drift.
HIGH orchestrator_service.py:1642-1650 create_initial_state called WITHOUT org_id/user_id (computed at :1514; AgentState declares both) → all audit actors "chat_agent", all billing lands on "default".
MED core/graph.py:492 state.get("tier","standard") — tier never a key in AgentState → tiering permanently standard.
MED prompt assembly spread across 5 sites (graph.py:30, intent_patterns:295, orchestrator_service:459,567, delegation_manager:226-378, module_builder:73,551); prompt_composer.compose() used by exactly ONE site; REPAIR_SYSTEM_PROMPT defined never used → route all through compose.
MED FOUR independent keyword/intent classifiers: graph._should_use_tools (~90 keywords :113-210), intent_patterns INTENT_PATTERNS :96-170, provider_router._estimate_complexity :257-314, delegation_manager._classify_query :332-371 → one QueryClassifier.
MED graph.py:222 vs :474 module-tool-name sets differ (module_pipeline missing from retry-budget injector) → retry-budget notice never appended to actual tool output while prompt tells LLM to respect it.
MED admin_api.py:337-392 vs module_admin.py:111-161 enable/disable dup with TWO different audit mechanisms (@audit_action vs _record_mutation) → ModuleLifecycleService owns mutation+audit.
MED checkpointing.py:391-537 RecoveryManager pure delegation wrapper over CheckpointManager → fold in.
MED shared/adapters/base.py:191-232 vs tools/base.py:259-320 two parallel template-method lifecycles with incompatible envelopes (AdapterResult success-bool vs ToolResult status-str) → unify envelope.
LOW adapters/base.py:246-256 normalize_for_tools vs normalize_category_for_tools both pass-throughs → keep classmethod.

## 3. BUILD PIPELINE (SAGA)
Stage map: scaffold real (module_builder:234-321); implement stage MISSING (docstrings promise LLM generation; actually conversational LLM + write_module_code); tests stage MISSING (template at scaffold time); validate real; repair real but single-attempt-per-call.
HIGH module_builder.py:143-163 BuildSession instantiated :228, mutated :295-296, DISCARDED on return; never persisted/reloaded/passed on; current_stage never advanced. NO saga coordinator — stage transitions emergent from LLM tool-call ordering → persist keyed by job_id, reject out-of-order.
HIGH module_builder.py:399-445 max-10 cap checks len(audit_log.attempts) but only prod caller approval.py:177 constructs FRESH BuildAuditLog per rejection → always 0 → cap unenforceable across attempts → load-or-create by job_id inside repair_module.
HIGH module_pipeline.py:49-56 RepairStrategy passes LLM JSON kwargs but signature requires BuildAuditLog object → action='repair' raises TypeError unconditionally; repair unreachable from chat surface.
HIGH retry counters in 4 files, five independent: MAX_REPAIR_ATTEMPTS=10 (module_builder:57); module_build_max_iterations=10 (state.py:82-85 → graph:226-230,591); max_iterations=5 (state.py:81); max_tool_iterations (orchestrator_service:338,455); gateway max_retries=5 → one RetryPolicy.
HIGH repair loop: NO backoff, no per-error-class policy; FailureType binary; llm_gateway._compute_backoff (exp+jitter+cap) exists but transport-scoped only → reuse.
MED 4 competing backoff impls (gateway :36-67 correct; github_models no jitter; base_client tenacity; adapters/base declared-never-read) → shared/utils/retry.py.
MED module_builder:583-585 patches applied file-by-file, NO compensation/rollback — mid-loop failure leaves dir half-patched; scaffold leaves dir behind on later failure, tripping own "already exists" guard :211-216 → temp dir + atomic swap; compensate(stage) hook.
MED three different "undo" mechanisms (gc.queue_for_gc, uninstall_module, versioning rollback), none invoked by pipeline → saga compensation table.
MED module_builder:64 Blueprint2CodeScorer constructed never called; shared/agents/confidence.py (337 ln) zero prod call sites; confidence gate absent → wire or delete.
LOW GOOD: shared/modules/audit.py FailureFingerprint/classify_failure_type genuinely centralized → keep; move MAX_REPAIR_ATTEMPTS next to it.
LOW nexus_dev.py:176-250 third sequencing of scaffold→validate→install with importlib.reload + MagicMock wiring.

## 4. SRP VIOLATIONS
HIGH orchestrator_service.py 1873 ln, 3 unrelated classes (OnlineProviderWrapper :140-320; LLMEngineWrapper :322-812; OrchestratorService :814-1780) → split 4 files.
HIGH __init__ :822-1122 = 300-line service locator → build_orchestrator() composition root.
HIGH admin_api.py 2287 ln: all routers + uvicorn bootstrap in one module → split routers.
HIGH _process_query :1498-1747 (250 ln): guard/intent/metrics/clarification/quota/LIDM/prompt/state/invoke/gauges/extraction/metrics → extract QuotaGate/DelegationRouter/MetricsEmitter.
HIGH core/graph.py:384-522 _tools_node: dispatch+execution+error+latency+result construction+LLM formatting+retry-budget injection+run-unit calc+SQLite persistence → MeteringHook + presenter.
HIGH user_context.py:25-362 fetch+transform+present+route; _build_fallback_summary duplicates dashboard formatters (cross-service import :118); :267,279 read request["search_category"] which validate_input never produces → LLM category filter silently dropped.
HIGH module_validator.py 579 ln: result types+orchestration+4 static checkers+sandbox exec+artifact persistence+fix hints; import sys mid-file :426 → split.
HIGH module_builder.py 669 ln: scaffold+manifest+bundling+audit+gateway+async bridge (:114-140, dup of orchestrator_service:184-200)+patch+prompt → split stages + shared AsyncBridge.
MED checkpointing.py 623 ln: checkpointer factory+SQL+WAL admin+thread status+recovery policy+maintenance → split.
MED module_installer.py:48-216 install_module: gating+hash+hot-load+registry+manifest+audit+UX text; dead double-guard :162,:167 → InstallPolicy/InstallExecutor.
MED provider_router.py ProviderRouter conflates 5 concerns AND is dead (see §5).

## 5. DEAD / REDUNDANT / DUPLICATE ENTRY POINTS
HIGH admin_api.py:1696-1913 copy-pasted endpoint block: 3 request models + 8 endpoints registered TWICE; 5 exact-duplicate paths unreachable (first-match wins); duplicate get_draft_diff has DIVERGENT RBAC (require_permission(MANAGE_MODULES) :745 vs get_current_user :1766); RollbackRequest conflicting schemas (target_version vs target_version_id) → delete 1696-1913, keep stricter RBAC.
HIGH admin_api.py:1886 GET /admin/modules/{module_id}/versions shadowed by /admin/modules/{category}/{platform} :304 → routes to get_module(category="foo",platform="versions"), 404s.
HIGH provider_router.py (636 ln) exported in __init__ but imported NOWHERE in production; duplicates ProviderRegistry+gateway retry+delegation tier routing → delete.
HIGH shared/agents/confidence.py (337 ln) zero prod callers; _find_forbidden_imports 4th copy of forbidden-import detection → wire or delete.
HIGH core/self_consistency.py (210 ln) constructed orchestrator_service:900, never called → wire or delete.
MED worker_adapter.py (103 ln) test-only; comments confirm mesh removed → delete.
MED orchestrator/rl/ (705 ln) nothing imports it; docstring uses pre-refactor tool names; hard torch dep not in requirements → move or delete.
MED orchestrator_service.py:52-58 unused intent_patterns imports; should_continue_tool_loop (the whole point) never called.
MED ~1300 ln superseded tool code kept alive only by never-repointed tests (web_search, web_loader, finance_query, module_manager, decorators, BaseToolLegacy, idempotency) → delete + rewrite tests.
MED adapters/base.py:52-58 AdapterConfig retry/timeout/rate-limit fields declared never read; fetch() has none despite docstring claim → implement or delete.
LOW empty stub packages adapters/health, adapters/navigation pre-seeded in registry + enum; user_context._handle_commute bypasses adapter layer reading raw JSON.
LOW adapters/registry.py:86-89 _register_default_adapters empty pass.
LOW GetMetrics gRPC handler returns hardcoded "unavailable"/0 stub :1478-1497.
LOW 5-6 parallel registry implementations → generic Registry[K,V].
LOW five entry points independently wire module subsystem; nexus_dev mutates os.environ + importlib.reloads → bootstrap_module_system().

## Top 8 by impact
1. 23 alias registrations raise on invocation (orchestrator_service:1038-1061)
2. All 31 tool schemas degenerate to kwargs-string (registry:315-356)
3. Max-10 repair cap unenforceable; action='repair' uncallable (module_builder:440, module_pipeline:55)
4. Circuit breakers never record outcomes (graph:437-440 bypasses call_tool)
5. 217 lines duplicated endpoints, divergent RBAC (admin_api:1696-1913)
6. No persisted saga state; stages LLM-ordered (module_builder:143-163)
7. Prompts still teach pre-refactor tool vocabulary (graph:30-49, intent_patterns:99-164)
8. Repair loop lacks backoff/jitter/error-class policy while gateway has it (llm_gateway:36-67)
