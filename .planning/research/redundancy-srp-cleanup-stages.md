# NEXUS Redundancy & SRP Cleanup — Staged Sub-Tasks

> Source: user-provided auth/billing/observability/services audit (2026-08-13).
> Nature: cleaning / refactoring / integrating / verifying. NO new features, NO change requests.
> Prime directive: zero functional regression — every stage exits through a test gate.
> Sequencing constraint: Stages 2-3 touch files that Phase 8 gap plans (08-02+) are anchored to
> (admin_api.py, dashboard main.py, middleware, stores, gc/retention). They execute AFTER Phase 8
> gap execution completes. Stage 0 (read-only) and Stage 1 (dead code + mechanical fixes) may run before.

## Stage 0 — VERIFY CLAIMS (read-only, runs now)

Confirm liveness/deadness before any deletion. Output: confirmed kill-list with evidence.

- [ ] 6.1 OTC pair: `otc_reward.py` (86 ln) + `otc_policy_store.py` (378 ln) claimed zero prod callers.
      CAUTION: Phase 4 deliverable was "bridge run-unit metering to OTC reward signal" — deletion may
      undo a shipped requirement. Verify call graph + Phase 4 SUMMARYs before verdict (delete vs wire).
- [ ] 6.2 `sandbox_service/runner.py` (405 ln): audit itself notes module_validator.py:421-422 calls it →
      NOT dead; verdict is re-route module_validator to gRPC sandbox then delete, or keep. Verify.
- [ ] 6.1 `latency_snapshot.py`: claimed __main__-only. CAUTION: Phase 4 REQ-028 perf snapshot may invoke
      it via make verify / scripts. Grep Makefile + scripts/ before verdict.
- [ ] 6.1 remainder (create_auth_middleware, interceptors, quota get_remaining/would_exceed,
      estimate_request_cost, aggregator probe_all_adapters, LogContext, delete_prefs, execute_with_timeout,
      relevance get_context_summary_for_llm) — grep-verify zero callers incl. tests.
- [ ] 5.8 HRV threshold drift (<40 formatters vs <30 relevance) — confirm which is clinically intended
      (check git history / CONTEXT docs) before unifying.
- [ ] Existing test debt baseline (6 known failures) — re-confirm list so Stage 1 gates are honest.

## Stage 1 — CLEAN (safe subset, may run before Phase 8 gaps execute)

Only items with confirmed zero callers and no Phase 8 file overlap:

- [ ] Delete confirmed-dead symbols/files from Stage 0 verdicts (NOT runner.py/OTC unless confirmed).
- [ ] 6.3 sandbox_service.py dead imports/classes (multiprocessing, StringIO, signal, TimeoutError/
      MemoryExceededError, module-level restricted_import).
- [ ] 6.6 `datetime.utcnow()` → `datetime.now(timezone.utc)` (api_keys 5 sites, bridge 2 sites).
- [ ] 4.6 dashboard permanently-zero instruments (AGGREGATOR_FETCH_DURATION, CACHE_HITS/MISSES,
      CONTEXT_ITEMS) — delete or wire; do not leave zombie series.
- [ ] 6.5 bridge `except: pass` :854-855 and `if "body" in dir()` JSON-RPC id bug; sandbox except:pass ×2.
- [ ] Test debt repair: test_context_bridge.py stale import; test_feature_test_gating.py deleted-module
      import; ImportPolicy signature drift (3); fallback_chain retry count (1).
- GATE: `cd tests && pytest unit/ -q` fully green (741+ and the 6 repaired), `make audit-test`, `make auth-test`.

## Stage 2 — REFACTOR (after Phase 8 gap execution)

- [ ] P1 `shared/storage/sqlite_base.py`: one `_connect()` (WAL + busy_timeout=10000 + row_factory +
      foreign_keys opt-in), constructor boilerplate, `PRAGMA user_version` migrations, shared dynamic-filter
      builder. Migrate all 9 stores (api_keys, usage, otc_policy*, audit, user_prefs, registry, credentials,
      versioning, checkpointing). Audit store keeps BEGIN IMMEDIATE + triggers + hash chain semantics —
      regression test: verify_chain() on migrated store.
- [ ] 3.6/3.7 usage_store aggregation consolidation (one query path for check_quota); validate_key single
      connection on hot path.
- [ ] 4.4 metrics.py declarative MetricSpec (kills ~85% of 615 ln); 4.5 bridge dicts → create_tool_metrics.
- [ ] 5.1 dashboard app_factory + routers split (1105 ln → modules); 5.7 handler dedup + one
      HTTPException(500) wrapper; 5.9 bank_service filter chain single impl; 5.10 aggregator health-mutation
      helper.
- [ ] 5.5 sandbox template extraction (source template out of f-string, one unlink helper).
- GATE: full unit + integration (Docker up) + `make verify` + audit chain verification.

## Stage 3 — INTEGRATE (after Stage 2; security-sensitive items reviewed one-by-one)

- [ ] P2 `create_nexus_app()` factory: auth+audit+CORS+public-paths+metrics middleware in ONE place
      (kills 1.1, 1.3, 1.5, 2.4); shared `serve_grpc()` with ObservabilityServerInterceptor everywhere
      (1.6); shared configure_logging w/ correlation IDs in all services (1.2); config package adoption (1.7).
- [ ] SECURITY 2.1 bridge auth on /tools/execute_code + /rpc (integrate APIKeyAuthMiddleware — existing
      component, not new feature). Audit events for code execution ride the existing store.
- [ ] SECURITY 2.2 sandbox identity: propagate org/actor metadata over gRPC; kill "default"-org attribution
      in core/graph.py:491-511.
- [ ] SECURITY 2.3 dashboard credential endpoints: get_current_user → require_permission(MANAGE_CREDENTIALS);
      add missing dependency on check_module_credentials. (Phase 7 added authN; this closes authZ.)
- [ ] 2.5 `Depends(org_scope)` extraction (~10 admin_api sites + OWNER cross-org rule single source).
- [ ] 2.6 OrgDirectory port between billing and auth.
- [ ] P3 MeteringService.meter() single owner (4.2) + QuotaPolicy/QuotaReader split w/ one enforcement
      helper (5.3 — incl. the hardcoded "default" org at admin_api quota site) + graph.py tool node uses
      injected MeteringService, one UsageStore instance (5.4).
- [ ] 5.8 `alert_rules.py`: one threshold table (resolve HRV 30/40 from Stage 0 verdict); remove
      tools/builtin/user_context.py cross-service import of dashboard formatters.
- [ ] 1.4 single health servicer impl + one probe aggregator; 6.4 duplicate endpoint aliases retired with
      deprecation shims if UI references them.
- [ ] 6.2 sandbox policy unification: ONE import allowlist source of truth (policy.py vs sandbox_service
      divergence), clamps deduplicated; wire or delete NetworkViolation plumbing; runner.py per Stage 0 verdict.
- NON-CHANGE (documented policy, do NOT "fix"): metering fail-open vs audit fail-closed is an intentional
  contract divergence (07-CONTEXT D-03). Add a failure-policy note in shared/ docs instead.
- GATE: full suites + showroom + RBAC matrix tests (viewer/operator/admin/owner on changed endpoints)
  + bridge/sandbox auth tests (new callers rejected without key).

## Stage 4 — FINAL VERIFY

- [ ] `make verify` (integration + showroom + perf snapshot) with services up.
- [ ] Audit chain verify endpoint valid; metering totals unchanged for a scripted request sequence
      (before/after comparison — regression sentinel for MeteringService refactor).
- [ ] Grafana dashboards render (metric names unchanged or dashboards updated in same commit).
- [ ] /gsd:code-review on the cleanup diff.

## Non-negotiables

- Every deletion cites Stage 0 evidence in its commit message.
- Behavior-preserving refactors only; any endpoint path/auth change is listed above explicitly (2.1/2.2/2.3)
  and gets its own commit + tests.
- No `--no-verify` commits; suites green before each stage merge.
