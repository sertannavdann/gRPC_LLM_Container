---
phase: 9
slug: ecs-context-canvas
status: approved
nyquist_compliant: true
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
| 09-07-T3 | 09-07 | 4 | Buffered RF pattern under churn (LOCKED, spike 001) | T-09-16 | N/A | e2e | `npx playwright test e2e/pipeline-ecs-churn.spec.ts` (Test 1) | ❌ W0→built in 09-07 | ⬜ pending |
| 09-07-T3 | 09-07 | 4 | Drag verified via Playwright — drag-stop write-back persists across an SSE tick (Done Criterion wording) | T-09-17 | N/A | e2e | `npx playwright test e2e/pipeline-ecs-churn.spec.ts` (Test 2, real `page.mouse.down/move/up`) | ❌ built in 09-07 | ⬜ pending |
| 09-07-T3 | 09-07 | 4 | Hover verified via Playwright — stability under churn, no page errors (UI-SPEC locks hover visually unchanged) | — | N/A | e2e | `npx playwright test e2e/pipeline-ecs-churn.spec.ts` (Test 3) | ❌ built in 09-07 | ⬜ pending |
| 09-06-T2 | 09-06 | 2 | clearSelectionIfMissing transition logic (LOCKED, spike 002) | T-09-02 | Stale id-refs cleared in the same transition | unit | `npx vitest run src/machines/__tests__/pipelinePage.test.ts` | ❌ built in 09-06 | ⬜ pending |
| 09-07-T3 | 09-07 | 4 | Stale selection clears in the PRODUCTION PAGE (Done Criterion: "reproduced in production page") | T-09-02 | Detail panel closes when the selected module leaves the snapshot | e2e | `npx playwright test e2e/pipeline-ecs-churn.spec.ts` (Test 4, throwaway `modules/e2e_probe` manifest created then deleted) | ❌ built in 09-07 | ⬜ pending |
| 09-03-T3 | 09-03 | 2 | Delta mirror-reconstruction (spike 006) | — | N/A | unit | `npx vitest run src/ecs/__tests__/dirty.test.ts` | ❌ built in 09-03 | ⬜ pending |
| 09-03-T3 | 09-03 | 2 | Canonical text stability under churn (spike 005b) | — | N/A | unit | `npx vitest run src/ecs/__tests__/verbalize.test.ts` | ❌ built in 09-03 | ⬜ pending |
| 09-05-T2 | 09-05 | 4 | Rewind clear-then-restore, no duplication (spike 008) | T-09-12 | N/A | unit | `npx vitest run src/ecs/__tests__/history.test.ts` | ❌ built in 09-05 | ⬜ pending |
| 09-04-T3 | 09-04 | 3 | LLM op ownership policy (V4) | T-09-01 | LLM ops touch module entities only; services/stages refused | unit | `npx vitest run src/ecs/__tests__/mediation.test.ts` | ❌ built in 09-04 | ⬜ pending |
| 09-04-T3 | 09-04 | 3 | zod op-schema validation (V5) | T-09-05 | Malformed/unknown ops rejected with structured errors | unit | same mediation suite | ❌ built in 09-04 | ⬜ pending |
| 09-08-T1 | 09-08 | 5 | Preview is a pure overlay; optimistic-add grace (LOCKED) | T-09-03, T-09-20 | Preview never mutates the world; no credential names in badges | unit | `npx vitest run src/ecs/__tests__/preview.test.ts` | ❌ built in 09-08 | ⬜ pending |
| 09-09-T3 | 09-09 | 6 | LLM proposal → preview → approve/reject end-to-end; rejection rewinds cleanly; approved ops appear in next delta (Done Criterion) | T-09-01, T-09-02, T-09-22 | Approve re-validates against the live world; reject rewinds to a byte-identical c_state | e2e | `npx playwright test e2e/pipeline-canvas-ops.spec.ts` (3 tests, driven through the `window.__nexusCanvas` build-flagged dev seam) | ❌ built in 09-09 | ⬜ pending |
| 09-02-T3 | 09-02 | 2 | `GET /context/canvas` auth posture + payload safety | T-09-04 | Route PUBLIC by explicit decision (inherits `/context` prefix); no credential material in the payload | integration | `cd tests && python -m pytest unit/test_canvas_context.py -v` | ❌ built in 09-02 | ⬜ pending |
| 09-10-T3 | 09-10 | 7 | Undo/redo via the snapshot ring (Done Criterion) + assumptions A3/A4 | T-09-10, T-09-17, T-09-24 | StrictMode does not double-append history; shortcuts inert in text fields | manual (checkpoint) | MISSING — blocking `checkpoint:human-verify`; automated neighbours are `npm run test` + `npx playwright test e2e/` | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Unit test runner install in `ui_service` (Vitest `[ASSUMED]` — planner confirms; `npm install -D vitest`, versions verified at install time)
- [ ] `ui_service/src/ecs/__tests__/verbalize.test.ts` — canonical ordering + format stability under churn
- [ ] `ui_service/src/ecs/__tests__/dirty.test.ts` — delta mirror-reconstruction
- [ ] `ui_service/src/ecs/__tests__/history.test.ts` — rewind/replay determinism
- [ ] `ui_service/src/ecs/__tests__/mediation.test.ts` — op schema + ownership policy + 3-point re-validation
- [ ] `ui_service/src/machines/__tests__/pipelinePage.test.ts` — clearSelectionIfMissing transition logic (plan 09-06)
- [ ] `ui_service/e2e/pipeline-ecs-churn.spec.ts` — churn stability + real drag with position persistence + hover stability + DOM-level stale-selection clearing (plan 09-07; follows `e2e/pipeline-sse.spec.ts` structure)
- [ ] `ui_service/e2e/pipeline-canvas-ops.spec.ts` — propose → overlay → approve → delta, and approve → reject → rewind toast → byte-identical c_state (plan 09-09; requires the `NEXT_PUBLIC_CANVAS_DEV_SEAM=1` build flag in the compose image)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mid-drag node removal during SSE tick | Spike-flagged open question (001/CONVENTIONS) | Drag gestures + precisely-timed SSE removal are flaky to automate; one-time check | With stack up, start dragging a module node; trigger a snapshot that removes it (disable module via admin API); confirm no crash, no ghost node, drag ends cleanly |
| Delta-context prompt framing with live model | Spike 006 deferred item | Requires live orchestrator LLM; behavioral not structural | Inspect orchestrator context assembly for delta header comprehension in one real build_module conversation |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags (use `vitest run`, never bare `vitest`)
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-05 (plan-checker iteration 2: VERIFICATION PASSED)
