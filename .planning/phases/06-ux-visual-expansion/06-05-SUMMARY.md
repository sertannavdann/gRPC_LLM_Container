---
phase: 06-ux-visual-expansion
plan: 05
subsystem: ui
tags: [nextjs, xstate, contract, fallback, resilience, testing]
requires:
  - phase: 06-04
    provides: monitoring machine, error taxonomy, dashboard state scaffolding
provides:
  - centralized runtime parameters consumed by admin client and machine
  - reason-coded capability fallback contract for auth/unavailable paths
  - deterministic dashboard rendering for auth/degraded/network/empty states
  - synchronization guard tests for contract and machine drift
affects: [phase-07-audit-trail, ui-runtime-stability, admin-api-contract]
tech-stack:
  added: [none]
  patterns: [same-origin-bff-admin-reads, contract-driven-ui-state, centralized-runtime-params]
key-files:
  created: [ui_service/src/lib/runtime-params.ts, tests/unit/ui/test_nexus_app_machine.ts, ui_service/src/app/api/monitoring/latency/route.ts]
  modified: [ui_service/src/lib/adminClient.ts, ui_service/src/app/api/admin/[...path]/route.ts, ui_service/src/machines/nexusApp.ts, ui_service/src/app/dashboard/page.tsx, ui_service/src/lib/errors.ts, shared/contracts/ui_capability_schema.py, orchestrator/admin_api.py, tests/unit/test_capability_contract.py]
key-decisions:
  - "Keep browser admin reads same-origin only via /api/admin and preserve auth scope boundaries"
  - "Represent fallback provenance explicitly in CapabilityEnvelope via snapshot_source and fallback_reason"
  - "Map capability faults in machine layer and keep dashboard page render-only"
patterns-established:
  - "Single source runtime params: polling/timeout/retry values in one module"
  - "Reason-coded fallback contract: degraded/auth paths remain contract-valid and diagnosable"
duration: 8min
completed: 2026-02-17
---

# Phase 6 Plan 05: Runtime Stability Hardening Summary

**Contract-driven capability fallback with same-origin admin reads and deterministic auth/degraded/network/empty dashboard states**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-17T08:31:44Z
- **Completed:** 2026-02-17T08:39:40Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- Centralized runtime parameters and removed browser-side direct admin calls to port 8003.
- Extended capability contract and admin envelope with `snapshot_source` and `fallback_reason` metadata.
- Hardened XState + dashboard rendering so auth/degraded/network/empty states are explicit and deterministic.
- Added drift guard tests for capability contract, machine mapping, and monitoring latency shape.

## Task Commits

Each task was committed atomically:

1. **Task 1: Consolidate admin read path and runtime parameters into single-source configuration** - `e3a9141` (feat)
2. **Task 2: Make lock/degraded/empty rendering deterministic from contract + XState** - `6261da9` (feat)
3. **Task 3: Add synchronization guard tests for frontend/backend parametric drift** - `8e791d1` (fix)

## Files Created/Modified
- `ui_service/src/lib/runtime-params.ts` - canonical polling/timeout/retry/fallback parameters.
- `ui_service/src/lib/adminClient.ts` - same-origin admin reads and timeout alignment with shared params.
- `ui_service/src/app/api/admin/[...path]/route.ts` - constrained read-only fallback with reason-coded metadata.
- `shared/contracts/ui_capability_schema.py` - envelope metadata fields for fallback provenance.
- `orchestrator/admin_api.py` - live envelope emits contract-compatible metadata.
- `ui_service/src/machines/nexusApp.ts` - explicit capability-state mapping and polling transition fix.
- `ui_service/src/app/dashboard/page.tsx` - deterministic degraded/auth/empty rendering policy.
- `ui_service/src/lib/errors.ts` - error taxonomy alignment for state transitions.
- `ui_service/src/app/api/monitoring/latency/route.ts` - stable monitoring latency response shape.
- `tests/unit/test_capability_contract.py` - fallback metadata and envelope guard coverage.
- `tests/unit/ui/test_nexus_app_machine.ts` - runtime-param and machine-state synchronization guard.

## Decisions Made
- Fallback payloads stay contract-valid and include explicit reason codes instead of silent empty arrays.
- Machine owns capability fault interpretation; page only renders declared UI states.
- Kept implementation minimal: no additional abstractions beyond shared runtime params and existing proxy/client boundaries.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Frontend test command mismatch and missing local deps**
- **Found during:** Task 3 verification
- **Issue:** `npm test` script does not exist in `ui_service`; TypeScript guard test could not run on host without local dependencies.
- **Fix:** Executed test via `tsx` and installed `ui_service` dependencies to satisfy runtime imports.
- **Verification:** `NODE_PATH=./ui_service/node_modules npx --yes tsx tests/unit/ui/test_nexus_app_machine.ts` exits successfully.
- **Committed in:** `8e791d1` (task commit)

**2. [Rule 1 - Bug] Duplicate computed transition key in capability poll state**
- **Found during:** Task 3 full build verification
- **Issue:** Duplicate computed object key in `nexusApp.ts` `after` transition caused TypeScript compile failure.
- **Fix:** Removed duplicated interval key and kept single deterministic transition.
- **Files modified:** `ui_service/src/machines/nexusApp.ts`
- **Verification:** `make build && make up` completed successfully.
- **Committed in:** `8e791d1` (task commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes were required for correctness and verification completion, with no scope creep.

## Issues Encountered
- Local verification required a host-side dependency install for `ui_service` since the test runner path was not predefined.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Dashboard runtime remains usable under auth/network degradation with explicit reason-coded states.
- Contract, machine, and rendering layers are synchronized and guarded by regression checks.
- Ready to proceed to Phase 7 planning/execution.

## Self-Check: PASSED

- FOUND: `.planning/phases/06-ux-visual-expansion/06-05-SUMMARY.md`
- FOUND: `e3a9141`
- FOUND: `6261da9`
- FOUND: `8e791d1`
