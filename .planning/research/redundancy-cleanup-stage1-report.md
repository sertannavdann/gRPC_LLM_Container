# Redundancy/SRP Cleanup — Stage 1 Report

> Executed 2026-08-22 on worktree branch (base 1b7e886b). Spec:
> `.planning/research/redundancy-srp-cleanup-stages.md` (Stage 0 verdicts = evidence base).
> Net: **26 files changed, +70 / −1698 lines** across 7 atomic commits.

## Commits

### 1. `bd30ef4` — Delete dead OTC pair (−996)
- Deleted `shared/billing/otc_reward.py`, `shared/billing/otc_policy_store.py`,
  `tests/unit/test_otc_policy_store.py`, `tests/unit/test_otc_reward.py`.
- Re-verified in worktree: zero prod importers, not exported from `shared/billing/__init__.py`.
- Orphans `.planning/research/nexus_otc_policy_schema.sql` (noted in commit message).
- Gate: unit suite green (821 passed, 2 pre-existing-failure files ignored).

### 2. `2a22007` — Delete dead symbols (−363, 11 files)
Each symbol's zero-caller status re-verified by grep before deletion:
- `grpc_interceptor.py`: `ObservabilityClientInterceptor`, `create_server_interceptors`,
  `create_client_interceptors` + now-unused `ClientInterceptor`/`inject_context` imports.
  Kept `ObservabilityServerInterceptor` + `_wrap_streaming_handler` (live).
- `shared/auth`: `create_auth_middleware` + `__init__` export/`__all__` entry.
- `dashboard_service/aggregator.py`: `probe_all_adapters`, module-level `get_user_context`
  wrapper (live `tools/builtin` one untouched).
- `dashboard_service/relevance.py`: `get_context_summary_for_llm`.
- `logging_config.py`: `LogContext` + `clear_context` (+ `clear_contextvars` import);
  kept `bind_context` (public export).
- `shared/auth/user_prefs.py`: `delete_prefs`.
- `sandbox_service/runner.py`: `execute_with_timeout` method only (file is LIVE, kept).
- `shared/billing`: `QuotaManager.get_remaining`/`would_exceed`,
  `RunUnitCalculator.estimate_request_cost`; surgical `test_billing.py` edit removed the
  6 tests using them (file kept; `test_multi_tool_request_flow` reworked onto live API).
- Gate: unit suite green (815 passed, same ignores).

### 3. `30ec905` — `datetime.utcnow()` → `datetime.now(timezone.utc)` (7 sites)
- `shared/auth/api_keys.py` (5), `bridge_service/mcp_server.py` (2).
- Format note: new isoformat strings carry `+00:00`. Verified no consumer parses or
  compares these fields (`grace_until` written but never read back; `ORDER BY created_at`
  lexicographic, unaffected; bridge timestamps response-only).
- Gate: `tests/unit/test_auth.py` + `tests/auth/` green (67 passed).

### 4. `3eedc7c` — Delete 4 zombie dashboard instruments (−140)
- `AGGREGATOR_FETCH_DURATION`, `AGGREGATOR_CACHE_HITS`, `AGGREGATOR_CACHE_MISSES`,
  `CONTEXT_ITEMS` in `dashboard_service/main.py` — declared, never observed/incremented.
- Pre-check found references: grafana `service-health.json` panels 19 (Cache Hit Rate)
  and 20 (Aggregator Fetch Time) queried ONLY dead series — removed same commit
  (panel 18 Active Users kept — its series is live). No prometheus rule references.
- Also removed print-only `test_dashboard_cache_metrics` from
  `tests/observability/test_metrics_e2e.py` (exercised only deleted series, no assertions).
- Gate: `import dashboard_service.main` ok, grafana JSON validates, unit suite green.

### 5. `196640f` — Swallowed-exception fixes (behavior-affecting, spec-listed)
- `mcp_server.py` `_tool_list_tools`: bare `except: pass` → warning log with
  orchestrator address before static fallback.
- `mcp_server.py` `handle_jsonrpc`: `body.get("id") if "body" in dir() else None` →
  `req_id` initialized before try, set after parse; error responses now reliably carry
  the JSON-RPC request id (old form also crashed when body parsed to a non-dict).
- `sandbox_service.py`: both temp-file cleanup `except: pass` sites → `except OSError`
  + warning log with temp file path.
- Gate: py_compile both files; `sandbox_service.sandbox_service` imports; unit suite
  green. (`bridge_service.mcp_server` not importable locally — `aiolimiter` not
  installed in dev env, pre-existing condition, unrelated to change.)

### 6. `ece27bb` — HRV threshold unification
- `relevance.py:198` `< 30` → `< 40` with comment citing canonical threshold
  (formatters.py + HealthWidget.tsx). Fixes live inconsistency: HRV 30–39 alerted in
  prose but wasn't classified high-priority.
- Gate: unit suite green; grep confirms no remaining HRV comparison against 30.

### 7. `0eec404` — Test-debt repair (6 failures → green)
- `test_context_bridge.py`: rewritten to current `ContextBridge.normalize()` API
  (Phase 5 05-05 commit `46ccd2a` deleted `_normalize_context_for_tools`).
- `test_feature_test_gating.py`: **deleted** — imports `feature_test_harness` +
  `chart_validator`, both deleted as dead code in Phase 5 Wave 4 (commit `14e6d7a`);
  feature no longer exists, nothing to port.
- ImportPolicy drift (3 failures): tests now call
  `sandbox_service.runner._check_imports_with_policy(source, policy)` (the current
  policy-aware path returning `ImportViolation` objects). Production untouched. Also
  fixed a 4th drift in the same files: build/repair registration source-grep updated to
  the `_module_pipeline_tool` + `name="build_module"` form.
- `test_fallback_chain.py`: expectation derives from `gateway.max_retries` (retry-then-
  fallback is current behavior; constructed with `max_retries=2` to keep backoff short).

## Final gates
- `cd tests && python -m pytest unit/ -q` (no ignores): **824 passed**. Math from the
  858-passing baseline (which ignored 2 broken files): −37 OTC tests, −6 dead-billing
  tests, +2 rewritten context_bridge tests, +7 fallback_chain tests now green = 824.
- `integration/cross_feature/test_policy_propagation.py` +
  `test_contract_enforcement_pipeline.py`: **11 passed**.
- `make audit-test`: **36 passed, 43 skipped** (skips are Docker-dependent, pre-existing).
- `make auth-test`: **61 passed**.

## Skipped / notes
- Spec Stage 1 bullet "6.3 sandbox_service.py dead imports/classes (multiprocessing,
  StringIO, signal, TimeoutError/MemoryExceededError, module-level restricted_import)"
  was NOT in the executor task list and was left untouched — flagged for a Stage 1
  follow-up or Stage 2.
- Worktree was created 265 commits behind the specified base; fast-forwarded to
  `1b7e886b` before starting. Protobuf stubs regenerated locally via `make proto-gen`
  (gitignored artifacts, required for the test suite).
- Stage 2/3 items untouched (sqlite_base, app factory, metering, security integrations).
