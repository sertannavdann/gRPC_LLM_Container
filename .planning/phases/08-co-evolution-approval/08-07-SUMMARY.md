---
phase: 08-co-evolution-approval
plan: 07
subsystem: ui
tags: [xstate, typescript, sse, admin-api, approval-workflow]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: "08-03's extended SSE payload (pending-approval modules with status/pending_approval/build_stage) and 08-01's approve/reject/review/audit admin API endpoints"
provides:
  - "Typed adminClient additions (ModuleReview, ModuleAuditAttempt, ApprovalResult, approveModule/rejectModule/getModuleReview/getModuleAudit) for consumption by plan 08-08"
  - "pipelinePageMachine (XState v5) with connection/selection/reviewPanel parallel regions, ready to be wired into the pipeline page in plan 08-08"
affects: [08-08, 08-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fromCallback actor wrapping a long-lived EventSource, invoked at the parallel-region level so it survives internal substate transitions (first fromCallback usage in ui_service/src)"
    - "Guarded parallel-region entry: a shared event (SELECT_NODE) drives two independent regions differently via a named guard (hasModuleId)"

key-files:
  created:
    - ui_service/src/machines/pipelinePage.ts
  modified:
    - ui_service/src/lib/adminClient.ts

key-decisions:
  - "Used xstate's assign() for all context mutation (named actions in setup.actions), diverging from monitoringPage.ts/financePage.ts's older direct-context-mutation-in-action-function style, per the plan's explicit instruction to use assign"
  - "sseConnection invoked at the connection region's top level (not inside the connecting child state) so the EventSource is not recreated on connecting->connected->reconnecting transitions"
  - "ModuleAuditAttempt.failure_fingerprint/failure_type typed as string|null, matching shared/modules/audit.py's actual Optional[str] dataclass fields (not the FailureFingerprint class), read directly from source rather than inferred from UI-SPEC prose"

patterns-established:
  - "Approval action actors (approveAction/rejectAction) take { moduleId, feedback? } as fromPromise input, splitting category/platform from the `category/platform` module id at the actor boundary, keeping adminApi calls two-argument"

requirements-completed: ["REQ-014"]

duration: 20min
completed: 2026-08-14
---

# Phase 08 Plan 07: Client Contract Layer for Approval UI Summary

**Typed adminClient approval fetchers (approve/reject/review/audit) plus a parallel-region pipelinePageMachine (XState v5) wrapping the existing SSE transport — no page or component rewired yet.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-08-14T04:36:39Z
- **Tasks:** 2 completed
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `ui_service/src/lib/adminClient.ts` now types the full approval surface: `ModuleState.status/pending_approval/build_stage`, `ModuleReview`, `ModuleBlueprint`, `ModuleAuditAttempt`, `ModuleAuditLog`, `ApprovalResult`, and four `adminApi` fetchers (`approveModule`, `rejectModule`, `getModuleReview`, `getModuleAudit`) matching the `{category}/{platform}` backend route shape shipped in 08-01.
- `ui_service/src/machines/pipelinePage.ts` created with `pipelinePageMachine`: a `type: 'parallel'` machine with `connection` (SSE lifecycle via a leak-free `fromCallback` actor), `selection` (active graph node), and `reviewPanel` (`closed -> loading -> open -> approving/rejecting -> error`) regions — the interface contract every downstream approval-UI plan (08-08+) will consume.
- `rejectModule` always sends `{"feedback": null}` when no feedback is supplied (never omits the key), matching D-09's terminal-rejection contract.

## Task Commits

1. **Task 1: Approval types and fetchers in adminClient** - `f1271c3` (feat)
2. **Task 2: pipelinePageMachine (XState v5, parallel regions)** - `8a8b302` (feat)

**Plan metadata:** committed via SDK metadata step after this SUMMARY.

_Note: no TDD tasks in this plan; both were type/lint-verified `auto` tasks._

## Files Created/Modified
- `ui_service/src/lib/adminClient.ts` - Added approval types (ModuleReview, ModuleBlueprint, ModuleAuditAttempt, ModuleAuditLog, ApprovalResult) and four adminApi fetchers; widened ModuleState with optional status/pending_approval/build_stage fields
- `ui_service/src/machines/pipelinePage.ts` - New XState v5 parallel machine (connection/selection/reviewPanel regions) wrapping connectPipelineSSE and the new adminApi approval fetchers

## Decisions Made
- Followed the plan's explicit instruction to build actions via `assign()` (named entries in `setup({ actions })`) rather than mirroring monitoringPage.ts/financePage.ts's older direct-context-mutation style — this is the more idiomatic XState v5 pattern and the plan called it out explicitly.
- `loadReview`/`approveAction`/`rejectAction` are all module-scope `fromPromise(...)` values (matching `financePage.ts`'s `testConnection`/`fetchFinanceData` top-level-function style) rather than inline actor definitions, for readability and testability.
- Typed `ModuleAuditAttempt.failure_fingerprint`/`failure_type` as `string | null` by reading `shared/modules/audit.py`'s `AttemptRecord` dataclass directly (`Optional[str]` / `Optional[FailureType]` serialized via `.to_dict()`), rather than the `.hash` object shape implied in passing by UI-SPEC.md's prose — the plan's `<read_first>` explicitly directs typing from the dataclass, which takes precedence as the source of truth.

## Deviations from Plan

None - plan executed exactly as written. `ui_service/node_modules` and `package-lock.json`-driven `npm ci` were run locally to make `tsc`/`next lint` executable (dependencies were not yet installed in this worktree); no `package.json` or lockfile changes were made, so this was not a Rule-3-excluded new-package install — it reproduced existing declared dependencies to satisfy the plan's own `<verify>` commands.

## Issues Encountered
- This worktree's HEAD was initially on an unrelated, much older commit (`6b2027b "Cohesion (#14)"`, with no `.planning/` directory at all) despite being on the correct `worktree-agent-*` branch. Per the mandatory `<worktree_branch_check>` step, `git merge-base` against the expected base (`750b290e...`) did not match, so a `git reset --hard 750b290e...` was performed (working tree was already clean, so this was non-destructive) before any plan file could be read. This is standard setup-time base correction, not a plan deviation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 08-08 (page/component rewiring) can now consume `pipelinePageMachine` via `useMachine()` and the four new `adminApi` approval fetchers directly — no further contract work needed on the client side.
- No component or page behavior changed in this plan, matching the plan's own success criteria; manual/browser verification is deferred to 08-08 where the machine is actually wired to `useMachine()`.

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-14*
