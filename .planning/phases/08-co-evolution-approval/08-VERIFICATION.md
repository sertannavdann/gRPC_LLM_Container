---
phase: 08-co-evolution-approval
verified: 2026-08-22T08:45:00Z
status: passed
score: 13/13 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 6/13
  gaps_closed:
    - "Module approval gates UI (REQ-014) — full chain SSE → pipelinePageMachine → pending badges → 5-layer review surface → chat approval → generic module panel"
    - "Tiered trace retention (REQ-017) — gc_and_retention_worker: gc_pending sweep + per-org tiered usage pruning, started at orchestrator serve()"
    - "Pipeline SSE E2E tests (REQ-018) — Playwright suite: connect / reconnect / error, no EventSource mocking, fail-fast service gate"
    - "Rate limiting (REQ-020) — RateLimitMiddleware on both FastAPI services, 429 + Retry-After verified live"
    - "Done Criteria: No module installed without explicit user approval — CR-01/WR-01 fixed; attested + unattested + tampered + unapproved + legacy paths all re-verified empirically"
    - "Done Criteria: Traces auto-purge per retention policy — sweep_gc_pending + prune_expired_usage wired into daily worker with D-12 reference-safety and audit-store exemption"
    - "D-19 actor/timestamp/bundle-hash audit — actor=user.user_id (HTTP + chat), valid ISO-8601 timestamps, hash recorded, dual-write to Phase 7 AuditStore"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Live Playwright SSE E2E run: `make up`, then `cd ui_service && npm run e2e` (dashboard on :8001, UI on :3000)"
    expected: "3 tests pass: initial connect shows Live indicator; reconnect after dashboard restart returns to Live without reload; SSE failure shows explicit Disconnected state"
    why_human: "Requires the full Docker stack; Docker was down during phase execution (documented deferral) and this verifier's sandbox cannot start services. The suite itself is delivered, unmocked, and gated by a fail-fast global-setup health probe (verified statically)."
  - test: "Live admin integration suites: `python -m pytest tests/integration/admin/ -v` with the stack up (gRPC :50054)"
    expected: "Previously Docker-gated suites (test_approval_gate.py 17 tests, test_inbound_rate_limit.py, test_audit_query_api.py) pass instead of skipping"
    why_human: "294 integration tests are Docker-gated by the suite's autouse environment fixture (suite convention, not a gap); RBAC 403/200 behavior is verified at unit level and by decorator wiring, but not exercised over live HTTP here."
  - test: "Visual/UX review: pipeline page pending-approval badge, 5-layer review surface (blueprint, code diff, sandbox report, credentials, repair history), walkthrough text, chat ApprovalActionCard two-click terminal reject"
    expected: "Surfaces render per 08-UI-SPEC with Phase 6 visual language; approve/reject round-trips update node state via SSE within ~2s"
    why_human: "Visual appearance, animation coherence (D-13), and real-time SSE-driven state transitions cannot be verified by grep/compile."
---

# Phase 8: Co-Evolution & Approval — Verification Report (Re-verification)

**Phase Goal:** Module approval gates UI (REQ-014), tiered trace retention (REQ-017), Pipeline SSE E2E tests (REQ-018), rate limiting (REQ-020). Done criteria: "No module installed without explicit user approval" and "Traces auto-purge per retention policy."
**Verified:** 2026-08-22T08:45:00Z
**Status:** passed (all 13 must-haves verified against code; live-service checks listed under Human Verification Required)
**Re-verification:** Yes — after gap closure (previous: gaps_found, 6/13, 2026-08-13)

## Scope Note

Initial verification (2026-08-13) covered only plan 08-01 and scored 0/6 phase-level truths. Since then plans 08-02 through 08-13 were written, executed across 6 waves, and merged. This re-verification re-ran full 3-level (+ behavioral) verification on every previously-FAILED item and regression checks on previously-passed items. Per orchestrator instruction, status vocabulary is passed | gaps_found; items requiring live services are reported honestly under Human Verification Required rather than counted as gaps (the deliverables themselves — code, wiring, tests — are verified present and substantive).

## Goal Achievement

### Observable Truths — Phase-Level (Roadmap Done Criteria + Deliverables)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| RT1 | Module approval gates UI (REQ-014) | ✓ VERIFIED | Full chain verified (see Key Links): SSE pending-approval payload (`dashboard_service/pipeline_stream.py:_build_pending_approval_list`, `pending_approval`/`build_stage` fields) → `pipelinePageMachine` (XState v5, 282 lines, SSE actor + approve/reject invoke actors) → `pipeline/page.tsx` (useMachine, `pendingApproval` mapping, APPROVE/REJECT sends) → `ModuleNode.tsx` amber "Needs Review" badge (D-01/D-04) → `NodeDetailPanel.tsx` (778 lines: walkthrough, five literal `Accordion.Item` sections — blueprint/code-diff/validation/credentials/repair-history (D-06), sticky approve/reject footer, two-click terminal reject) → `BlueprintCard.tsx` (D-05) → chat `ApprovalActionCard.tsx` wired in `ChatContainer.tsx:437` (D-02) → generic `ModulePanel.tsx` over `AdapterRunResult` for installed modules (D-07). `npx tsc --noEmit` clean. |
| RT2 | Tiered trace retention (REQ-017) | ✓ VERIFIED | `orchestrator/retention_worker.py`: `TIER_RETENTION_DAYS = {free: 7, team: 90, enterprise: -1}` (unlimited sentinel, enterprise skipped); `prune_expired_usage()` resolves org plan via APIKeyStore and calls `usage_store.delete_before(org_id, cutoff)`; `gc_and_retention_pass()` runs both policies (D-11, one worker/two policies); `start_retention_worker()` (daemon thread, `GC_INTERVAL_SECONDS` default 86400, `GC_WORKER_ENABLED` gate) is called in `orchestrator_service.py:1956` at serve(). Prometheus-native per-tenant retention documented as RESEARCH Assumption A1 (app-level org-scoped retention; native multi-tenant Prometheus = Phase 9 Mimir/Cortex territory). `tests/unit/test_retention_worker.py` passes. |
| RT3 | Pipeline SSE E2E tests (REQ-018) | ✓ VERIFIED (delivered + gated; live run → human item) | `ui_service/e2e/pipeline-sse.spec.ts` (115 lines): 3 tests — initial connect (Live indicator), reconnect after dashboard restart (Disconnected → Live, no reload), error handling via `context.setOffline()` (explicitly NOT request mocking; native EventSource onerror path). No EventSource mocks anywhere in the suite. `global-setup.ts` probes UI + dashboard `/health` and throws (fail-fast) when unreachable. `playwright.config.ts` + `@playwright/test` dep + `npm run e2e` script present. Live execution deferred — Docker was down during execution (documented); listed under Human Verification Required, not scored as a gap. |
| RT4 | Rate limiting (REQ-020) | ✓ VERIFIED | `shared/auth/rate_limit_middleware.py`: token bucket (reuses `TokenBucketRateLimiter` registry), per-endpoint-prefix rules (longest-prefix match; `/admin/bootstrap`, `/admin/modules`, `/admin`, `/` defaults; env `RATE_LIMIT_RPS`/`RATE_LIMIT_BURST`), keyed on X-API-Key falling back to client IP, exempt health/metrics paths, `RATE_LIMIT_ENABLED` kill-switch (429-safety for tests — set to "false" by `tests/integration/admin/conftest.py` autouse). Mounted OUTERMOST on both services: `orchestrator/admin_api.py:2113` and `dashboard_service/main.py:375` (before auth so brute force is throttled pre-auth). **Live behavioral check by this verifier:** burst 2 → `[200, 200, 429, 429, 429]` with `Retry-After: 1` header and `{"error": "rate_limit_exceeded"}` body. `tests/unit/test_rate_limit_middleware.py` passes. |
| RT5 | Done: No module installed without explicit user approval | ✓ VERIFIED | See "Install Integrity Reproduction" below — CR-01 and WR-01 both empirically confirmed FIXED. `install_module()` requires APPROVED status AND unconditionally recomputes `compute_code_bundle_hash()` (adapter.py + test_adapter.py, manifest.json excluded) against `manifest.approved_bundle_sha256` recorded at approval time; modules approved before integrity binding (no hash) are rejected with a re-approval demand. Approval reachable only via RBAC-gated paths: HTTP `require_permission(WRITE_CONFIG)` (admin_api.py:931,957) and chat `_require_admin_session()` fail-closed session gate (module_admin.py:357-383, reads authenticated session user, not ambient actor). `ApprovalPolicy().auto_approve is False` re-confirmed by execution (D-18). |
| RT6 | Done: Traces auto-purge per retention policy | ✓ VERIFIED | `shared/modules/gc.py`: `sweep_gc_pending()` rglobs `.gc_pending` markers, per-marker try/except, grace period; `purge_module_artifacts()` deletes module dir + artifact bundle dir with D-12 reference-safety (skips when `version_manager.get_active_version()` returns an active pointer → `{"purged": False, "reason": "active_version_reference"}`), path-traversal guard (`_resolved_child`, T-08-14), and audit exemption (module docstring hard constraint: never opens AUDIT_DB_PATH/AUDIT_DIR; `*.jsonl` files relocated to `.gc_preserved/`, never deleted — grep confirms no AUDIT_DIR/audit_events.db reference in gc.py). Sweep + tiered pruning run daily via the worker wired at serve(). `tests/unit/modules/test_artifact_gc.py` passes. |

**Phase-level score:** 6/6 (was 0/6).

### Observable Truths — Plan 08-01 Must-Haves (regression + fix checks)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| PT1 | `install_module()` refuses non-APPROVED modules (D-16) | ✓ VERIFIED (regression) | `module_installer.py:103-113`; empirical: VALIDATED module rejected with "has not been approved for install"; `test_installer_approval_guard.py` passes (within 858-test unit run + focused 82-test run) |
| PT2 | Admin can approve VALIDATED → APPROVED (D-16/D-17) | ✓ VERIFIED (regression) | Empirically re-run: `approve_module` → `{'status': 'success', 'new_status': 'approved', 'bundle_sha256': ccbc8077…}` — now also returns the approval hash |
| PT3 | Approve/reject below admin+ returns 403 (D-17) | ✓ VERIFIED | HTTP: `Depends(require_permission(Permission.WRITE_CONFIG))` on both endpoints (admin_api.py:931,957). Chat: `_require_admin_session()` denies unauthenticated/non-WRITE_CONFIG sessions fail-closed (module_admin.py:357-383, T-08-40/T-08-41); `tests/unit/test_module_admin_approval.py` passes. Live HTTP 403 assertion remains Docker-gated (human item). |
| PT4 | Reject-with-feedback → bounded repair, back to pending (D-09) | ✓ VERIFIED (regression) | `approval.py:153-199`: VALIDATING + best-effort `repair_module()` with reviewer feedback as fix hint, audit `terminal: False` |
| PT5 | Reject-without-feedback terminal: FAILED + GC queue (D-09/D-10) | ✓ VERIFIED (regression) | `approval.py:201-225`: FAILED + `queue_for_gc(module_id, modules_dir, actor=actor)`; the marker now HAS a consumer (`sweep_gc_pending`) — the previous "marker with no consumer" partial is closed. `queue_for_gc` also no longer fabricates phantom dirs (IN-04 fix: returns None when module dir absent, gc.py:58-63) |
| PT6 | Approve/reject recorded with actor + timestamp + bundle hash (D-19) | ✓ VERIFIED (was FAILED) | **WR-02 fixed:** `actor=user.user_id` at admin_api.py:940,973 and module_admin.py:432 (chat); `org_id` passed separately into audit details. **WR-03 fixed:** `datetime.now(timezone.utc).isoformat()` with no `+ "Z"` in approval.py:92,150 and gc.py:67 — empirical audit output: `2026-08-22T08:31:16.390101+00:00` (valid ISO-8601, parseable by `datetime.fromisoformat` in the sweep). Bundle hash computed pre-mutation and stored in audit details AND `manifest.approved_bundle_sha256`. Sink: `DevModeAuditLog(sink=audit_store)` dual-writes every `log_action` into the Phase 7 SQLite `AuditStore` fail-closed (audit.py:425-441; wired at orchestrator_service.py:1039-1042 and 1913-1916 — single shared store) |
| PT7 | `ApprovalPolicy` scaffold, `auto_approve=False` default (D-18) | ✓ VERIFIED (regression) | Executed: `ApprovalPolicy().auto_approve is False` |

**Plan-level score:** 7/7 (was 6/7).

**Combined score: 13/13 must-haves verified** (was 6/13).

## Install Integrity Reproduction (CR-01/WR-01 fix, independent re-run by this verifier)

Same scenario that failed the initial verification, re-run against merged code (temp module dir, fake loader):

```
validate-time hash:            ccbc8077f803d2a5…
approve_module:                success → approved, bundle_sha256=ccbc8077f803d2a5… (same hash — manifest.json excluded)
install (with attestation):    success            (was: "Artifact integrity failure" — CR-01 FIXED)
install (no attestation):      success            (default caller path works)
tamper adapter.py, reinstall:  error "Artifact integrity failure: bundle hash mismatch"  (WR-01 FIXED — unconditional check)
install of VALIDATED module:   error "has not been approved for install"                 (D-16 guard intact)
install of APPROVED-no-hash:   error "approved before integrity binding existed … requires re-approval"  (legacy path fail-closed)
```

Root-cause fix confirmed in code: `shared/modules/artifacts.py:300` `compute_code_bundle_hash()` hashes exactly `CODE_BUNDLE_FILES = ("adapter.py", "test_adapter.py")` — "manifest.json is deliberately excluded" — and is the single source of truth for both approval-time issuance (`approval.py:86-89`, computed BEFORE the status mutation) and install-time verification (`module_installer.py:121`).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `shared/modules/artifacts.py::compute_code_bundle_hash` | manifest-exclusive code hash (CR-01 fix) | ✓ VERIFIED | Single source of truth for approval + install hashes |
| `shared/modules/manifest.py::approved_bundle_sha256` | integrity-binding field | ✓ VERIFIED | Line 85; also `walkthrough: str` field added (line 95, IN-02 fix) |
| `tools/builtin/module_installer.py` | APPROVED guard + unconditional hash check | ✓ VERIFIED | Empirically exercised, all 5 paths above |
| `shared/modules/approval.py` | approve/reject core, hash issuance, valid timestamps | ✓ VERIFIED | 225 lines, substantive, wired from HTTP + chat |
| `shared/modules/gc.py` | marker writer + sweep consumer + purge (D-10/D-12) | ✓ VERIFIED | Was PARTIAL (marker-only); consumer + reference-safety + audit exemption now present |
| `orchestrator/retention_worker.py` | tiered retention + combined daily worker | ✓ VERIFIED | Wired at serve(); GC_WORKER_ENABLED / GC_INTERVAL_SECONDS config |
| `shared/auth/rate_limit_middleware.py` | inbound token bucket, 429 + Retry-After | ✓ VERIFIED | Mounted on admin_api :8003 and dashboard :8001; live-tested |
| `tools/builtin/module_walkthrough.py` + `module_validator.py` hook | walkthrough generated once at validation (D-08) | ✓ VERIFIED | validator.py:266-275: generated only on VALIDATED reports, never overwrites non-empty with empty |
| `tools/builtin/module_admin.py` approve/reject strategies | chat approval, session RBAC (D-02/D-17) | ✓ VERIFIED | `_require_admin_session()` from `shared.auth.session_context.get_session_user()`; `actor=user.user_id` |
| `orchestrator/orchestrator_service.py` session identity | session user from API key for non-HTTP entry | ✓ VERIFIED | `_resolve_session_user` (line 818) + `session_user()`/`actor_context()` context entry at 1454-1470 |
| `dashboard_service/pipeline_stream.py` | pending_approval/status/build_stage in SSE payload | ✓ VERIFIED | `_build_pending_approval_list` + `_build_stage_index` merged into module entries; `tests/unit/test_pipeline_stream_pending.py` passes |
| `ui_service/src/lib/adminClient.ts` | approval fetchers + types | ✓ VERIFIED | `approveModule`/`rejectModule`/`getModuleReview`/`getModuleAudit` + `ModuleReview` types |
| `ui_service/src/machines/pipelinePage.ts` | XState v5 machine (D-14) | ✓ VERIFIED | SSE fromCallback actor at connection-region level; APPROVE/REJECT → approving/rejecting invoke actors → adminApi |
| `ui_service/src/app/pipeline/page.tsx` | machine-driven page, pending nodes | ✓ VERIFIED | `useMachine(pipelinePageMachine)`, `pendingApproval` mapped from SSE, sends APPROVE/REJECT |
| `ui_service/src/components/pipeline/ModuleNode.tsx` | pending badge (D-01/D-04) | ✓ VERIFIED | `pendingApproval` → amber border + pulsing "Needs Review" badge, highest-priority visual state |
| `ui_service/src/components/pipeline/NodeDetailPanel.tsx` | 5-layer review + approve/reject footer (D-05/D-06/D-09) | ✓ VERIFIED | Five literal Accordion.Items: blueprint, code-diff, validation, credentials, repair-history; walkthrough block; two-click terminal reject |
| `ui_service/src/components/pipeline/BlueprintCard.tsx` | blueprint visual (D-05) | ✓ VERIFIED | 185 lines; reused by chat card via `expandable` prop |
| `ui_service/src/components/chat/ApprovalActionCard.tsx` | chat approval card (D-02) | ✓ VERIFIED | Inline blueprint fetch, feedback textarea, two-click terminal confirm; rendered by ChatContainer for module-approval tool calls |
| `ui_service/src/components/pipeline/ModulePanel.tsx` | generic AdapterRunResult panel (D-07) | ✓ VERIFIED | Rendered by NodeDetailPanel for installed modules |
| `ui_service/e2e/` Playwright suite + config | REQ-018 tests | ✓ VERIFIED | 3 specs, unmocked, fail-fast service gate; live run = human item |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `approve_module` hash issuance | `install_module` hash verification | `compute_code_bundle_hash` + `manifest.approved_bundle_sha256` | ✓ WIRED | Previously ✗ BROKEN (CR-01); empirically round-trips now |
| admin_api approve/reject endpoints | `shared/modules/approval.py` | direct call, `actor=user.user_id`, `audit_log=_draft_manager.audit_log` | ✓ WIRED | admin_api.py:938-944, 970-977 |
| chat `ModuleAdminTool` approve/reject | `shared/modules/approval.py` | `_require_admin_session()` → `approve_module(actor=user.user_id)` | ✓ WIRED | module_admin.py:416-436; same core as HTTP (single semantics) |
| gRPC entry (chat) | session identity | API-key metadata → `_resolve_session_user` → `session_user()` context | ✓ WIRED | orchestrator_service.py:1411-1470 |
| `DevModeAuditLog.log_action` | Phase 7 `AuditStore` (SQLite) | `sink.record(...)`, fail-closed, single shared store | ✓ WIRED | audit.py:425-441; orchestrator_service.py:1039-1042, 1913-1916 |
| `reject_module` (terminal) | GC purge | `.gc_pending` marker → `sweep_gc_pending` → `purge_module_artifacts` | ✓ WIRED | Marker now has a consumer; daily worker runs the sweep |
| retention worker | serve() startup | `start_retention_worker(usage_store, api_key_store, version_manager, ...)` | ✓ WIRED | orchestrator_service.py:1956-1962 |
| SSE payload | pipeline UI | `pending_approval` field → machine context → node badge → review surface | ✓ WIRED | pipeline_stream.py:219 → page.tsx:300 → ModuleNode.tsx:80 → NodeDetailPanel showReviewSurface |
| Review surface | backend review payload | machine `getModuleReview` → GET `/admin/modules/{c}/{p}/review` (operator+) | ✓ WIRED | Payload includes real `manifest.walkthrough`, credentials, `_build_blueprint_summary` (IN-02 closed) |
| RateLimitMiddleware | both HTTP apps | `add_middleware` outermost, before auth | ✓ WIRED | admin_api.py:2113; dashboard_service/main.py:375 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Install integrity chain (5 paths) | scratchpad repro script (validate→approve→install; tamper; unapproved; legacy) | All 5 outcomes correct (see reproduction section) | ✓ PASS |
| 429 + Retry-After | TestClient, burst=2 | `[200, 200, 429, 429, 429]`, `Retry-After: 1`, JSON error body; disabled/exempt paths bypass | ✓ PASS |
| `ApprovalPolicy().auto_approve` | python -c assertion | `False` | ✓ PASS |
| Audit trail suite | `make audit-test` | 36 passed, 43 skipped (Docker-gated) | ✓ PASS |
| Full unit suite | `cd tests && pytest unit/ -q --ignore=unit/test_context_bridge.py --ignore=unit/providers/test_fallback_chain.py` | **858 passed, 0 failed** | ✓ PASS |
| Phase-8 focused suites | `pytest unit/modules/test_artifact_gc.py unit/test_retention_worker.py unit/test_rate_limit_middleware.py unit/modules/test_installer_approval_guard.py unit/test_module_admin_approval.py` | 82 passed | ✓ PASS |
| Contract suite | `pytest contract/ -q` | 21 passed | ✓ PASS |
| Integration suite | `pytest integration/ -q --ignore=…test_feature_test_gating.py` | 53 passed, 294 skipped (Docker-gated convention), 4 pre-existing failures (see debt) | ✓ PASS (phase scope) |
| UI type-check | `cd ui_service && npx tsc --noEmit` (after `npm install` — local node_modules was stale) | Clean, zero errors incl. new phase-8 surfaces + e2e specs | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist or are referenced by any Phase 8 PLAN/SUMMARY. Step 7c: SKIPPED (no declared or conventional probes for this phase).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-014 | 08-01/02/03/06/07/08/09/10/11/12 | UI review of generated code + credentials + sandbox results; approve/reject with feedback loop | ✓ SATISFIED | RT1 + PT1-PT7; both HTTP and chat surfaces; feedback loop (D-09) verified |
| REQ-017 | 08-04 | Retention flags per org; background cleanup worker prunes daily | ✓ SATISFIED | RT2/RT6; per-org tiers enforced app-level against usage_records (RESEARCH Assumption A1: native per-tenant Prometheus retention = Phase 9; documented in retention_worker.py docstring) |
| REQ-018 | 08-13 | Playwright: initial connect, reconnect after restart, error handling | ✓ SATISFIED (suite delivered + gated) | RT3; live run against Docker stack → Human Verification Required |
| REQ-020 | 08-05 | Token bucket; configurable per-endpoint; 429 + Retry-After | ✓ SATISFIED | RT4; live 429 demonstrated |

No orphaned requirements: all four phase-mapped REQ IDs are claimed by executed plans.

### Review Findings Closure (08-REVIEW.md)

| Finding | Status | Evidence |
|---------|--------|----------|
| CR-01 (approval mutates hashed manifest) | ✓ FIXED | `compute_code_bundle_hash` excludes manifest.json; empirical round-trip passes |
| WR-01 (hash check optional) | ✓ FIXED | Unconditional check vs `approved_bundle_sha256`; tamper empirically rejected on the no-attestation path |
| WR-02 (actor=org_id) | ✓ FIXED | `actor=user.user_id` at admin_api.py:940,973 and module_admin.py:432; org_id in details |
| WR-03 (malformed `+00:00Z` timestamps) | ✓ FIXED (in-scope files) | approval.py/gc.py emit plain `isoformat()`; sweep parses `rejected_at` with `fromisoformat` + graceful error path. Residual `+ "Z"` in module_installer.py:300,330 and audit.py:413 is pre-existing Phase 3 code outside WR-03's scope (see debt) |
| WR-04 (audit test mirror wrong data source) | ✓ FIXED | tests/integration/admin/conftest.py:482-500 now mirrors production: `BuildAuditLog.load` over `*_audit.json` glob |
| WR-05 (inconsistent AUDIT_DIR default) | ✓ FIXED | admin_api.py:1031 `os.getenv("AUDIT_DIR", "data/audit")` — matches installer + orchestrator |
| IN-02 (nonexistent walkthrough field) | ✓ FIXED | `walkthrough: str = ""` on ModuleManifest (manifest.py:95), populated at validation (D-08) |
| IN-04 (phantom dir on bogus GC queue) | ✓ FIXED | `queue_for_gc` returns None when module dir absent (gc.py:58-63) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX debt markers in any phase-8 file (backend, UI, e2e) | — | Scan clean |
| `tools/builtin/module_installer.py` | 300, 330 | `isoformat() + "Z"` (malformed ISO-8601) in install audit JSONL | ℹ️ Info | Pre-existing (Phase 3 commit d721baa), untouched by WR-03's scope; nothing currently parses these fields strictly |
| `shared/modules/audit.py` | 413 | `isoformat() + "Z"` in DevModeAuditLog event timestamp | ℹ️ Info | Pre-existing (Phase 3 commit 5e810f9); D-19's decision timestamp lives in `details.timestamp` (valid) and the AuditStore sink row |

### Pre-Existing Debt (excluded from phase scoring, listed per instruction)

1. `tests/unit/test_context_bridge.py` — collection error (pre-existing, excluded from unit run)
2. `tests/unit/providers/test_fallback_chain.py::test_fallback_order_matches_priority` — 1 failure (pre-existing, excluded; rest of file passes)
3. `tests/integration/cross_feature/test_feature_test_gating.py` — collection error: `ModuleNotFoundError: tools.builtin.feature_test_harness` (file last touched Phase 3)
4. ImportPolicy drift — 4 failures: `test_contract_enforcement_pipeline.py::{test_forbidden_imports_caught_at_both_boundaries, test_build_and_repair_tools_registered_in_orchestrator_source}`, `test_policy_propagation.py::{test_sandbox_import_violation_becomes_validator_fix_hint, test_different_policy_profiles_all_block_subprocess}` — root cause `shared/modules/static_analysis.py:49` `TypeError: argument of type 'ImportPolicy' is not iterable` (Phase 5 file e7757ff/5a11de9, untouched by Phase 8)
5. 294 Docker-gated integration skips — suite convention (autouse environment fixture), not gaps
6. `ui_service/node_modules` was stale relative to package.json (this verifier ran `npm install` to obtain the clean tsc result; container builds install from package.json regardless)

### Human Verification Required

#### 1. Live Playwright SSE E2E run (REQ-018)

**Test:** `make up`, then `cd ui_service && npm run e2e` (UI :3000, dashboard :8001).
**Expected:** 3/3 pass — Live indicator on connect; Disconnected → Live after `docker restart` of dashboard without page reload; explicit Disconnected (never blank/crash) on SSE failure.
**Why human:** Requires the Docker stack; execution was deferred when Docker was down during 08-13 (documented). Suite verified delivered, unmocked, and fail-fast-gated.

#### 2. Live admin integration suites

**Test:** With the stack up (gRPC :50054), `python -m pytest tests/integration/admin/ -v`.
**Expected:** Previously-skipped suites pass: approval gate RBAC (17 tests), inbound rate limit, audit query API.
**Why human:** Docker-gated by suite convention; unit-level and wiring evidence already verified.

#### 3. Visual/UX review of approval surfaces

**Test:** Build a module to VALIDATED; review on Pipeline page (badge, five layers, blueprint, walkthrough) and via chat ApprovalActionCard; approve one module and terminally reject another; watch Grafana module panels.
**Expected:** Surfaces match 08-UI-SPEC/Phase 6 visual language; SSE reflects state within ~2s; terminal reject purges artifacts on next GC pass while audit rows persist.
**Why human:** Visual appearance, animation coherence (D-13), and real-time behavior are not grep-verifiable.

### Deferred Items

Per 08-CONTEXT.md `<deferred>`: Path B (`DraftManager.promote_draft` dev-mode edits) intentionally keeps its existing admin+ RBAC gate WITHOUT the new review-panel treatment (Q1 resolved 2026-08-13, revisit Phase 9). Auto-approve activation, multi-approver chains, versioning/marketplace UI → Phase 9. None are gaps against Phase 8's roadmap contract.

## Gaps Summary

None. All 7 previously-failed must-haves are closed with code-level and behavioral evidence; the 6 previously-passing must-haves show no regressions (858 unit + 21 contract tests green, clean UI type-check). The phase's goal — "Human approval gates the self-evolution engine — nothing installs without an explicit, attributable, integrity-bound decision — and artifacts and traces clean themselves up" — is observably true in the codebase: the install path is integrity-bound to the approval decision (empirically demonstrated, including tamper rejection), decisions are attributable to individual admins in the Phase 7 audit store, and one daily worker enforces both artifact GC (reference-safe, audit-exempt) and tiered per-org retention. Remaining items are live-service exercises listed under Human Verification Required.

---

*Verified: 2026-08-22T08:45:00Z*
*Verifier: Claude (gsd-verifier)*
