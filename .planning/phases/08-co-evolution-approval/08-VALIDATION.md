---
phase: 8
slug: co-evolution-approval
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-12
updated: 2026-08-14
plans_covered: 13
tasks_covered: 32
tasks_with_automated_verify: 31
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Regenerated against the finished plan set 08-01…08-13.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend) · `tsc --noEmit` + `next lint` + `next build` (frontend) · Playwright (E2E — installed by 08-13 Task 1) |
| **Config file** | none for pytest (no `pytest.ini` / `[tool.pytest]`; run from repo root via `python -m pytest`) · `ui_service/playwright.config.ts` created by 08-13 Task 1 |
| **Quick run command** | `python -m pytest tests/unit -x -q` (backend) · `cd ui_service && npx tsc --noEmit` (frontend) |
| **Full suite command** | `make verify` (→ `scripts/verify.sh`) |
| **Estimated runtime** | ~90s backend unit · ~60s `tsc + next build` · `make verify` several minutes |

---

## Sampling Rate

- **After every task commit:** run that task's `<automated>` command (scoped to the touched test files)
- **After every plan wave:** `python -m pytest tests/unit -q` + `cd ui_service && npx tsc --noEmit` for any wave containing UI plans
- **Before `/gsd:verify-work`:** `make verify` must be green
- **Max feedback latency:** 180 seconds (every per-task command above is well under this)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-T1 | 08-01 | 2 | REQ-014 | T-08-01, T-08-03 | Install refuses any module not at `ModuleStatus.APPROVED` | unit | `python -m pytest tests/unit/modules/test_installer_approval_guard.py -x -q` | ✅ exists | ⬜ pending |
| 08-01-T2 | 08-01 | 2 | REQ-014 | T-08-02, T-08-04, T-08-05 | approve/reject behind `require_permission(WRITE_CONFIG)`, every decision audited | integration | `python -m pytest tests/integration/admin/test_approval_gate.py -x -q` | ✅ exists | ⬜ pending |
| 08-02-T1 | 08-02 | 1 | REQ-014 | T-08-06, T-08-09 | Code-only bundle hash recorded at approval time | unit | `python -m pytest tests/unit/modules/test_installer_approval_guard.py -x -q` | ✅ exists | ⬜ pending |
| 08-02-T2 | 08-02 | 1 | REQ-014 | T-08-06, T-08-08 | Install-time hash recomputation is unconditional; fails closed on missing attestation | integration | `python -m pytest tests/unit/modules/test_installer_approval_guard.py tests/integration/install/ tests/integration/cross_feature/test_hash_chain_integrity.py tests/integration/cross_feature/test_audit_completeness.py -q` | ⬜ new (`tests/integration/install/test_approval_attestation_chain.py`) | ⬜ pending |
| 08-02-T3 | 08-02 | 1 | REQ-014 | T-08-07, T-08-10 | Individual-admin attribution + ISO-8601 hygiene in the audit record | integration | `python -m pytest tests/integration/admin/test_approval_gate.py -q; python -c "from datetime import datetime; import re,pathlib; s=pathlib.Path('shared/modules/approval.py').read_text(); assert 'isoformat() + \"Z\"' not in s"` | ✅ exists | ⬜ pending |
| 08-03-T1 | 08-03 | 1 | REQ-014 | T-08-11, T-08-13 | Only safe manifest fields reach the unauthenticated SSE stream | static | `python -c "import ast,sys; s=open('dashboard_service/pipeline_stream.py').read(); ast.parse(s); assert '_build_pending_approval_list' in s"` | n/a (source assertion) | ⬜ pending |
| 08-03-T2 | 08-03 | 1 | REQ-014 | T-08-13 | Malformed manifest cannot break the stream; no duplicate module entries | unit | `python -m pytest tests/unit/test_pipeline_stream_pending.py -x -q` | ⬜ new | ⬜ pending |
| 08-03-T3 | 08-03 | 1 | REQ-014 | T-08-57, T-08-58 | Only the `stage` string leaves BuildAuditLog; audit scan is cached and skipped when idle | unit | `python -m pytest tests/unit/test_pipeline_stream_pending.py -x -q` | ⬜ new | ⬜ pending |
| 08-04-T1 | 08-04 | 2 | REQ-017 | T-08-14, T-08-16 | GC resolves paths and refuses to delete referenced/rollback-target artifacts | unit | `python -m pytest tests/unit/modules/test_artifact_gc.py -x -q` | ⬜ new | ⬜ pending |
| 08-04-T2 | 08-04 | 2 | REQ-017 | T-08-17 | Retention DELETEs are parameterized (no SQL injection via org_id) | unit | `python -m pytest tests/unit/test_retention_worker.py -x -q` | ⬜ new | ⬜ pending |
| 08-04-T3 | 08-04 | 2 | REQ-017 | T-08-15, T-08-18 | Audit DB is GC-exempt; sweep runs off the event loop | unit + static | `python -m pytest tests/unit/test_retention_worker.py -x -q; python -c "import ast; ast.parse(open('orchestrator/orchestrator_service.py').read())"` | ⬜ new | ⬜ pending |
| 08-05-T1 | 08-05 | 2 | REQ-020 | T-08-19, T-08-22, T-08-59 | 429 + Retry-After, per-key buckets, no key in logs, limiter default-ON | unit | `python -m pytest tests/unit/test_rate_limit_middleware.py -x -q` | ⬜ new | ⬜ pending |
| 08-05-T2 | 08-05 | 2 | REQ-020 | T-08-20, T-08-23 | Limiter outermost (pre-auth, pre-mutation); existing admin suites stay 429-free | integration + regression | `python -m pytest tests/unit/test_rate_limit_middleware.py tests/integration/admin/ -q` | ⬜ new (`test_inbound_rate_limit.py`) | ⬜ pending |
| 08-06-T1 | 08-06 | 2 | REQ-014 | T-08-25, T-08-26 | Only generated adapter code leaves for the provider; budget-checked, timeout-bounded | unit | `python -m pytest tests/unit/modules/test_walkthrough_generation.py -x -q` | ⬜ new | ⬜ pending |
| 08-06-T2 | 08-06 | 2 | REQ-014 | T-08-24, T-08-27 | Walkthrough is evidence-bounded and rendered without raw HTML downstream | unit | `python -m pytest tests/unit/modules/test_walkthrough_generation.py -x -q` | ⬜ new | ⬜ pending |
| 08-07-T1 | 08-07 | 2 | REQ-014 | T-08-28, T-08-30 | Client never authorizes; approve/reject calls are typed server round-trips | typecheck | `cd ui_service && npx tsc --noEmit` | n/a (compiler gate) | ⬜ pending |
| 08-07-T2 | 08-07 | 2 | REQ-014 | T-08-29, T-08-31 | `pending_approval` is display-only; EventSource is closed on actor teardown | typecheck + lint | `cd ui_service && npx tsc --noEmit && npx next lint --dir src/machines` | n/a (compiler gate) | ⬜ pending |
| 08-08-T1 | 08-08 | 3 | REQ-014 | T-08-32 | Module labels render as React text only (no `dangerouslySetInnerHTML`) | typecheck + lint | `cd ui_service && npx tsc --noEmit && npx next lint --dir src/components/pipeline` | n/a (compiler gate) | ⬜ pending |
| 08-08-T2 | 08-08 | 3 | REQ-014 | T-08-33 | Node approval state is rendered from the payload, never inferred client-side | build | `cd ui_service && npx tsc --noEmit && npm run build` | n/a (build gate) | ⬜ pending |
| 08-08-T3 | 08-08 | 3 | REQ-014 | T-08-34, T-08-35 | Exactly one SSE owner; rejected modules render before disappearing | build | `cd ui_service && npx tsc --noEmit && npm run build` | n/a (build gate) | ⬜ pending |
| 08-09-T1 | 08-09 | 4 | REQ-014 | T-08-SC | `@radix-ui/react-accordion` legitimacy verified before install | **human-verify (blocking)** | — none by design (see Manual-Only Verifications) | n/a | ⬜ pending |
| 08-09-T2 | 08-09 | 4 | REQ-014 | T-08-36 | Markdown rendered without `rehype-raw`; zero raw-HTML sinks | build | `cd ui_service && npx tsc --noEmit && npm run build` | n/a (build gate) | ⬜ pending |
| 08-09-T3 | 08-09 | 4 | REQ-014 | T-08-37, T-08-38, T-08-39 | No secret values in the credential layer; two-click destructive confirm | build + lint | `cd ui_service && npx tsc --noEmit && npm run build && npx next lint --dir src/components/pipeline` | n/a (build gate) | ⬜ pending |
| 08-10-T1 | 08-10 | 3 | REQ-014 | T-08-43, T-08-44 | gRPC session key validated via `APIKeyStore`; key never logged | unit | `python -m pytest tests/unit/test_module_admin_approval.py -x -q` | ⬜ new | ⬜ pending |
| 08-10-T2 | 08-10 | 3 | REQ-014 | T-08-40, T-08-41, T-08-42 | Chat approve/reject fails closed without an admin session; attributed to the real user | unit | `python -m pytest tests/unit/test_module_admin_approval.py -x -q` | ⬜ new | ⬜ pending |
| 08-11-T1 | 08-11 | 5 | REQ-014 | T-08-45, T-08-47 | Approval card is display-only; model strings render as text children | typecheck + lint | `cd ui_service && npx tsc --noEmit && npx next lint --dir src/components/chat` | n/a (compiler gate) | ⬜ pending |
| 08-11-T2 | 08-11 | 5 | REQ-014 | T-08-46, T-08-48 | Authorization stays server-side; rejection requires two-click confirm | build | `cd ui_service && npx tsc --noEmit && npm run build` | n/a (build gate) | ⬜ pending |
| 08-12-T1 | 08-12 | 5 | REQ-014 | T-08-49, T-08-51, T-08-53 | Run endpoint 404s for non-installed modules; canonical envelope only; timeout honoured | unit | `python -m pytest tests/unit/test_module_run_endpoint.py -x -q` | ⬜ new | ⬜ pending |
| 08-12-T2 | 08-12 | 5 | REQ-014 | T-08-52 | Third-party payload strings render as React text, never markup | typecheck + lint | `cd ui_service && npx tsc --noEmit && npx next lint --dir src/components/pipeline` | n/a (compiler gate) | ⬜ pending |
| 08-12-T3 | 08-12 | 5 | REQ-014 | T-08-50 | Run action is authenticated and surfaced only for installed modules | build | `cd ui_service && npx tsc --noEmit && npm run build` | n/a (build gate) | ⬜ pending |
| 08-13-T1 | 08-13 | 6 | REQ-018 | T-08-SC2, T-08-56 | Playwright pinned/approved; base URLs default to localhost, never production | smoke | `cd ui_service && npx playwright --version && npx tsc --noEmit -p tsconfig.json` | ⬜ new (`playwright.config.ts`) | ⬜ pending |
| 08-13-T2 | 08-13 | 6 | REQ-018 | T-08-54, T-08-55 | Disruptive specs gated behind `E2E_ALLOW_RESTART`; traces retained on failure only | e2e (collection) | `cd ui_service && npx tsc --noEmit && npx playwright test --list` | ⬜ new (`e2e/pipeline-sse.spec.ts`) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Coverage:** 32 tasks across 13 plans · 31 carry an `<automated>` command · 1 (08-09-T1) is a blocking package-legitimacy human gate that is not auto-approvable by policy.

---

## Wave 0 Requirements

**None — no separate Wave 0 is required.** Every previously-MISSING test artifact is created inside the plan that first depends on it, by a `tdd="true"` task that writes the test alongside the code:

| Previously-missing artifact | Created by | Wave |
|-----------------------------|-----------|------|
| `tests/unit/test_pipeline_stream_pending.py` | 08-03 Task 2 (extended by Task 3) | 1 |
| `tests/integration/install/test_approval_attestation_chain.py` | 08-02 Task 2 | 1 |
| `tests/unit/modules/test_artifact_gc.py` | 08-04 Task 1 | 2 |
| `tests/unit/test_retention_worker.py` | 08-04 Task 2 | 2 |
| `tests/unit/test_rate_limit_middleware.py` | 08-05 Task 1 | 2 |
| `tests/integration/admin/test_inbound_rate_limit.py` | 08-05 Task 2 | 2 |
| `tests/unit/modules/test_walkthrough_generation.py` | 08-06 Tasks 1-2 | 2 |
| `tests/unit/test_module_admin_approval.py` | 08-10 Tasks 1-2 | 3 |
| `tests/unit/test_module_run_endpoint.py` | 08-12 Task 1 | 5 |
| `ui_service/playwright.config.ts` + `@playwright/test` | 08-13 Task 1 | 6 |
| `ui_service/e2e/pipeline-sse.spec.ts` | 08-13 Task 2 | 6 |

No task's `<automated>` command references a test file that its own plan does not create or that does not already exist on disk.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `@radix-ui/react-accordion` package legitimacy (08-09 Task 1) | REQ-014 | GSD package-legitimacy policy: `[ASSUMED]` packages are never auto-approvable, `workflow.auto_advance` is ignored | Follow the checkpoint's `<how-to-verify>`: npmjs.com scope/repo/downloads/history, `npm view … version`, `slopcheck install @radix-ui/react-accordion --ecosystem npm` |
| Blueprint card visual quality / coherence | REQ-014 | Aesthetic judgment | Open `/pipeline`, trigger a build, review the pending node + blueprint expansion |
| Live build-stage colour progression on the graph (D-13) | REQ-014 | Requires a real multi-minute build to walk scaffold → implement → tests → repair | With the stack up, start a module build and watch the module node border walk blue → purple → amber (→ red on repair); the payload contract itself is unit-covered by 08-03 Task 3 |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a documented manual-only exception (31/32 automated; 08-09-T1 is a policy-mandated blocking human gate)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (the single exception is isolated between 08-08-T3 and 08-09-T2)
- [x] Wave 0 covers all MISSING references (folded into the owning plans — see table above; no standalone Wave 0 needed)
- [x] No watch-mode flags (`--watch`, `next dev`, `pytest-watch` appear in zero commands)
- [x] Feedback latency < 180s (slowest per-task command is `npm run build`)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready for execution
