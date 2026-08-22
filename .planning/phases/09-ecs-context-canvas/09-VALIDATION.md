---
phase: 9
slug: ecs-context-canvas
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-23
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Playwright ^1.62.1 (E2E, exists) + unit runner (none today — Wave 0 installs; Vitest recommended `[ASSUMED]`) |
| **Config file** | `ui_service/playwright.config.ts` (E2E); unit config — none, Wave 0 installs |
| **Quick run command** | `npx playwright test e2e/<spec>.spec.ts` (targeted) / `npx vitest run <file>` once installed |
| **Full suite command** | `npm run e2e` (requires docker-compose stack up) + `npx vitest run` |
| **Estimated runtime** | E2E ~60s (stack-dependent); unit suite <5s |

---

## Sampling Rate

- **After every task commit:** Targeted Playwright spec for tasks touching `page.tsx`/`pipelinePage.ts`; unit suite (`npx vitest run`) for pure `src/ecs/*` logic
- **After every plan wave:** `npm run e2e` (full Playwright, stack running) + full unit suite
- **Before `/gsd:verify-work`:** Full E2E suite AND unit suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

Task IDs are assigned at planning time; this map binds decisions/criteria to test signals.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | Buffered RF pattern (LOCKED, spike 001) | — | N/A | e2e | `npx playwright test e2e/pipeline-ecs-churn.spec.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | clearSelectionIfMissing + proposal re-validation (LOCKED, spikes 002/007) | T-09-02 | Stale id-refs cleared in same transition | e2e | new Playwright spec (SSE-driven removal → DOM assertion) | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Delta mirror-reconstruction (spike 006) | — | N/A | unit | `npx vitest run src/ecs/__tests__/dirty.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Canonical text stability under churn (spike 005b) | — | N/A | unit | `npx vitest run src/ecs/__tests__/verbalize.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Rewind clear-then-restore, no duplication (spike 008) | — | N/A | unit | `npx vitest run src/ecs/__tests__/history.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LLM op ownership policy (V4) | T-09-01 | LLM ops touch module entities only; services/stages refused | unit | `npx vitest run src/ecs/__tests__/mediation.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | zod op-schema validation (V5) | T-09-01 | Malformed/unknown ops rejected with structured errors | unit | same mediation suite | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | `GET /context/canvas` auth posture | T-09-04 | Route covered by dashboard auth middleware (or explicitly gated) | integration | `pytest` against dashboard route (backend side) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Unit test runner install in `ui_service` (Vitest `[ASSUMED]` — planner confirms; `npm install -D vitest`, versions verified at install time)
- [ ] `ui_service/src/ecs/__tests__/verbalize.test.ts` — canonical ordering + format stability under churn
- [ ] `ui_service/src/ecs/__tests__/dirty.test.ts` — delta mirror-reconstruction
- [ ] `ui_service/src/ecs/__tests__/history.test.ts` — rewind/replay determinism
- [ ] `ui_service/src/ecs/__tests__/mediation.test.ts` — op schema + ownership policy + 3-point re-validation
- [ ] `ui_service/e2e/pipeline-ecs-churn.spec.ts` — buffered-pattern-under-churn (follows `e2e/pipeline-sse.spec.ts` structure)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mid-drag node removal during SSE tick | Spike-flagged open question (001/CONVENTIONS) | Drag gestures + precisely-timed SSE removal are flaky to automate; one-time check | With stack up, start dragging a module node; trigger a snapshot that removes it (disable module via admin API); confirm no crash, no ghost node, drag ends cleanly |
| Delta-context prompt framing with live model | Spike 006 deferred item | Requires live orchestrator LLM; behavioral not structural | Inspect orchestrator context assembly for delta header comprehension in one real build_module conversation |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags (use `vitest run`, never bare `vitest`)
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
