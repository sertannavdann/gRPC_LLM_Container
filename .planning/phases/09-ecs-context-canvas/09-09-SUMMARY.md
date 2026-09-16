---
phase: 09-ecs-context-canvas
plan: 09
subsystem: ui
tags: [xstate, react-flow, ecs, mediation, playwright, canvas-ops]

# Dependency graph
requires:
  - phase: 09-ecs-context-canvas (plan 05)
    provides: canvasMediation (propose/approve/reject/OWNERSHIP), canvasHistory (approveWithHistory/rejectWithRewind)
  - phase: 09-ecs-context-canvas (plan 08)
    provides: pending-confirmation registry (preview.ts), page.tsx's buffered React Flow patch effect, ModuleNode proposal overlay
provides:
  - submitCanvasOps() — the single documented ingress seam for LLM-authored ops into the browser mediation layer
  - canvasOpApproval branch of the existing reviewPanel region (approvingChange/rejectingChange substates)
  - NodeDetailPanel's Proposed Change section + RewindToast component
  - page.tsx wiring: CANVAS_PROPOSAL on node click, APPROVE_CHANGE/REJECT_CHANGE, rewind toast trigger
  - e2e/pipeline-canvas-ops.spec.ts — automated proof of propose->preview->approve/reject->rewind
affects: [phase-10, any-future-orchestrator-canvas-tool-transport]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dev-seam browser handle (window.__nexusCanvas) gated by NODE_ENV + a build-time NEXT_PUBLIC_* flag inlined via Dockerfile ARG/ENV + docker-compose build.args, so a hardened image ships without it by default"
    - "ECS mutation choke points must call touch() themselves if they need to notify React on a timeline shorter than the next real SSE tick — mediation.ts's propose/approve/reject now do this explicitly"
    - "Per-node 'last proposal id' tracking in a ref so a proposal that has moved from staged to approved (and is no longer annotated by proposalAnnotations()) can still be re-opened for reject-after-approve"

key-files:
  created:
    - ui_service/src/ecs/ingress.ts
    - ui_service/src/components/pipeline/RewindToast.tsx
    - ui_service/e2e/pipeline-canvas-ops.spec.ts
  modified:
    - ui_service/src/machines/pipelinePage.ts
    - ui_service/src/machines/__tests__/pipelinePage.test.ts
    - ui_service/src/components/pipeline/NodeDetailPanel.tsx
    - ui_service/src/app/pipeline/page.tsx
    - ui_service/src/ecs/mediation.ts
    - ui_service/Dockerfile
    - docker-compose.yaml

key-decisions:
  - "submitCanvasOps() adds no logic — it forwards straight to canvasMediation.propose(); all validation/ownership stays in mediation.ts (T-09-01 mitigation)"
  - "No orchestrator-side transport that calls submitCanvasOps was built this phase — deferred follow-up, flagged explicitly below"
  - "mediation.ts's propose()/approve()/reject() now call touch() directly — a bug fix discovered while writing the E2E spec: without it the canvas silently lagged proposal/approval/rejection state by up to one real SSE tick"
  - "RewindToast's 3s auto-dismiss timer is keyed only on `message`, using a ref for onDismiss — depending on onDismiss directly restarted the timer on every one of page.tsx's SSE-tick re-renders and the toast never dismissed"
  - "page.tsx remembers the last canvas-op proposal id per node (a ref, not machine context) so a reject-after-approve is reachable from the UI even though proposalAnnotations() stops badging a proposal once its status leaves 'staged'"
  - "E2E rewind byte-identity assertion is scoped to the target entity's own compact-DSL line (a new entityLine() dev-seam helper), not the whole live cState() — the real docker-compose stack's SSE tick mutates unrelated services' latency_ms independently of the rewind under test, which would make a whole-world comparison flaky for reasons unrelated to this feature"

patterns-established:
  - "Canvas-op proposal lifecycle: propose (stage) -> annotate (violet badge, live via touch()) -> open panel (canvasOpApproval) -> approve (mediation.approve + history recordable) or reject (staged reject, or rewind if already applied) -> toast only on true rewind"

requirements-completed: [D9-08, D9-09, D9-11, D9-12, T-09-01, T-09-02]

# Metrics
duration: 90min
completed: 2026-09-16
---

# Phase 09 Plan 09: Canvas-Op Proposal Lifecycle (Ingress -> Review -> Approve/Reject -> Rewind) Summary

**Closed the LLM write path end-to-end in the UI: a `submitCanvasOps()` dev-seam stages ops through the existing mediation layer, the reviewPanel region's `open` substate now branches into a `canvasOpApproval` view, and approve/reject drives `canvasHistory` with a rewind toast — proven by three new Playwright tests against the real docker-compose stack.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-09-16T00:15:00Z (approx, first read)
- **Completed:** 2026-09-16T00:55:42Z
- **Tasks:** 3/3 completed
- **Files modified:** 10 (3 created, 7 modified)

## Accomplishments

- `submitCanvasOps()` is now the single documented entry point for LLM-authored canvas ops, exposed as `window.__nexusCanvas` only when `NODE_ENV !== 'production'` or the build-time `NEXT_PUBLIC_CANVAS_DEV_SEAM=1` flag is set (wired through `ui_service/Dockerfile`'s ARG/ENV and `docker-compose.yaml`'s `build.args`, defaulting OFF for any build path other than the local compose stack).
- `pipelinePageMachine`'s existing `reviewPanel` region was extended (not replaced) with `canvasProposalId`/`canvasRewound` context, `CANVAS_PROPOSAL`/`APPROVE_CHANGE`/`REJECT_CHANGE` events, and `approvingChange`/`rejectingChange` substates — the machine still has exactly three parallel regions.
- `NodeDetailPanel` gained a compact, non-accordion "Proposed Change" section (rows, invalidated empty state, error state via `DegradedBanner`) and an "Approve Change"/"Reject Change" sticky footer reusing the module-approval button styling verbatim; the Phase 8 module-review surface is untouched.
- `RewindToast` is a new small hand-rolled Framer-Motion component (no new toast dependency) that fires only when a rejection actually rewound applied state.
- `page.tsx` routes an annotated module's click straight into `canvasOpApproval`, derives the panel's rows from the same `"{field} → {value}"` format `preview.ts` already exports, and remembers a node's last proposal id so reject-after-approve is reachable even after the annotation disappears.
- `e2e/pipeline-canvas-ops.spec.ts` proves the full loop against the real, running docker-compose stack (via the worktree's own `next dev -p 3101` pointed at the shared dashboard on 8001, per 09-07/09-08's documented pattern) — all 3 tests pass, plus a full regression pass of `pipeline-ecs-churn.spec.ts` (4 passed, 1 skipped without `E2E_ALLOW_RESTART`) and the full `vitest` suite (62/62).

## Task Commits

1. **Task 1: Ingress seam + canvasOpApproval branch in the reviewPanel region** - `f5cc747` (feat)
2. **Task 2: NodeDetailPanel — the Proposed Change section and its footer** - `bfbf801` (feat)
3. **Task 3: Page wiring + the canvas-ops end-to-end Playwright spec** - `c68ef00` (feat)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified

- `ui_service/src/ecs/ingress.ts` (created) - `submitCanvasOps()` seam + `window.__nexusCanvas` dev handle (`submitCanvasOps`, `delta`, `cState`, `entityLine`)
- `ui_service/src/components/pipeline/RewindToast.tsx` (created) - transient rewind confirmation banner, 3000ms auto-dismiss
- `ui_service/e2e/pipeline-canvas-ops.spec.ts` (created) - 3 Playwright tests proving the full proposal lifecycle
- `ui_service/src/machines/pipelinePage.ts` (modified) - `canvasProposalId`/`canvasRewound` context, `CANVAS_PROPOSAL`/`APPROVE_CHANGE`/`REJECT_CHANGE` events, `approvingChange`/`rejectingChange` substates
- `ui_service/src/machines/__tests__/pipelinePage.test.ts` (modified) - 5 new tests (11 total, up from 6)
- `ui_service/src/components/pipeline/NodeDetailPanel.tsx` (modified) - `canvasProposal`/`onApproveChange`/`onRejectChange` props, Proposed Change section + footer
- `ui_service/src/app/pipeline/page.tsx` (modified) - canvas-op wiring, `opRow()` derivation, rewind toast trigger, per-node last-proposal-id tracking
- `ui_service/src/ecs/mediation.ts` (modified) - `propose()`/`approve()`/`reject()` now call `touch()` (bug fix, see Deviations)
- `ui_service/Dockerfile` (modified) - `ARG`/`ENV NEXT_PUBLIC_CANVAS_DEV_SEAM` before `RUN npm run build`
- `docker-compose.yaml` (modified) - `ui_service.build.args.NEXT_PUBLIC_CANVAS_DEV_SEAM` defaulting to `1` locally

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `mediation.ts`'s `propose()`/`approve()`/`reject()` did not call `touch()`**
- **Found during:** Task 3, writing `e2e/pipeline-canvas-ops.spec.ts` — a freshly staged proposal's violet badge only appeared after the next real SSE tick (up to 2s), and an approved mutation's canvas-visible effect similarly lagged.
- **Issue:** The ECS `touch()` reactivity bridge was only ever called from `sync.ts`'s `syncRecords()` and `history.ts`'s `restoreSnapshot()`. Staging/approving/rejecting a proposal marks entities dirty via the world's choke points but never notified React, so `page.tsx`'s `version`-keyed patch effect and `proposalAnnotations()`-driven badges were silently stale until the next unrelated SSE tick happened to fire.
- **Fix:** Added `touch()` calls at the end of `propose()`, `approve()`, and `reject()` in `mediation.ts`. Never touches the live world itself — pure reactivity notification, consistent with D9-08 (preview is a pure overlay).
- **Files modified:** `ui_service/src/ecs/mediation.ts`
- **Commit:** `c68ef00`

**2. [Rule 1 - Bug] `RewindToast`'s auto-dismiss timer restarted on every parent re-render**
- **Found during:** Task 3, writing the "reject after approve" E2E test — the toast appeared but never disappeared within the expected 3-4s window.
- **Issue:** The component's `useEffect` depended on `[message, onDismiss]`, but `page.tsx` passes `onDismiss` as a fresh inline arrow function on every render — and `page.tsx` re-renders on every 2s SSE tick. Each re-render restarted the `setTimeout`, so the toast's timer never actually elapsed.
- **Fix:** `onDismiss` is now held in a `useRef` updated every render; the effect depends only on `message`, so the 3000ms timer runs to completion regardless of unrelated parent re-renders.
- **Files modified:** `ui_service/src/components/pipeline/RewindToast.tsx`
- **Commit:** `c68ef00`

### Claude's-Discretion additions (documented, not silent)

- Added a `lastProposalByNodeRef` map in `page.tsx` so a click on a node whose proposal has moved from `staged` to `approved` (and therefore no longer carries a `proposalAnnotations()` badge, per D9-08) still re-opens `canvasOpApproval` for that same proposal — without this, "reject an already-applied proposal" (a locked must-have truth in the plan) would have been unreachable from the UI a second time.
- Added `entityLine(id)` to the `window.__nexusCanvas` dev-seam handle (alongside the plan-specified `submitCanvasOps`) so `delta()`/`cState()` — needed by the E2E spec per the plan's own Task 3 assertions — and a scoped single-entity comparison are all available. The plan's Task 1 code sample only showed `{ submitCanvasOps }`; `delta`/`cState`/`entityLine` were added as the natural, minimal surface the plan's own Task 3 acceptance criteria require.
- Test 2's rewind byte-identity assertion compares `entityLine(id)` (the target entity's own compact-DSL line) rather than the whole-world `cState()`, because the real docker-compose stack's other services' `latency_ms` fluctuate independently of this feature on every real SSE tick — a whole-world comparison would be flaky for reasons unrelated to the rewind mechanism being tested.

## Deferred Follow-up (explicitly flagged per plan's `<output>` instruction)

**No orchestrator-side tool that emits canvas ops into `submitCanvasOps()` was built in Phase 9.** `ingress.ts` is the documented seam a future chat/ActionCard transport should call, and the dev-seam `window.__nexusCanvas` handle exists so the flow is exercisable and testable today — but there is currently no code path from an LLM/orchestrator response into `submitCanvasOps()`. This is a known, explicit gap for a future phase, not an oversight.

## Verification

- `cd ui_service && npx vitest run src/machines/__tests__/pipelinePage.test.ts` — 11/11 passed (plan 06's 6 + this plan's 5 new).
- `cd ui_service && npx vitest run` (full suite) — 62/62 passed.
- `cd ui_service && npx tsc --noEmit` — clean, after each task.
- `cd ui_service && npm run build` — clean, after each task.
- `cd ui_service && npx playwright test e2e/pipeline-canvas-ops.spec.ts` — 3/3 passed, run against the worktree's own `next dev -p 3101` pointed at the shared docker-compose dashboard (`http://localhost:8001`), `NEXT_PUBLIC_CANVAS_DEV_SEAM=1`.
- `cd ui_service && npx playwright test e2e/pipeline-ecs-churn.spec.ts` — 4 passed, 1 skipped (`E2E_ALLOW_RESTART` not set) — no regression from this plan's changes.
- `python3 -c "import yaml; yaml.safe_load(open('docker-compose.yaml'))"` — YAML syntax valid (per parallel_execution guidance, `docker compose build`/`up --build` was not run against this worktree; the Dockerfile/compose changes were verified via the dev-server + build-flag path above, matching how the actual image would receive the flag).

## Known Stubs

None — the propose/preview/approve/reject/rewind loop is fully wired and exercised end-to-end; no hardcoded placeholder data was introduced.

## Threat Flags

None beyond the plan's own threat model (T-09-01, T-09-02, T-09-22, T-09-23, T-09-03), all of which are addressed as specified: `submitCanvasOps` adds no logic and cannot bypass `OWNERSHIP`/zod validation; the panel's "Proposal no longer valid" state handles the invalidated-between-open-and-approve race; the dev-seam guard requires both a non-production build AND the explicit opt-in flag.

## Self-Check: PASSED

- FOUND: `ui_service/src/ecs/ingress.ts`
- FOUND: `ui_service/src/components/pipeline/RewindToast.tsx`
- FOUND: `ui_service/e2e/pipeline-canvas-ops.spec.ts`
- FOUND commit `f5cc747`
- FOUND commit `bfbf801`
- FOUND commit `c68ef00`
