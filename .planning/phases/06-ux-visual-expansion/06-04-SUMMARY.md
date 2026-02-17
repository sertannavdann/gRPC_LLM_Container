---
phase: 06-ux-visual-expansion
plan: 04
subsystem: ui, machines, monitoring, errors, auth
tags: [xstate, react-flow, recharts, framer-motion, error-taxonomy, user-prefs, monitoring-dashboard]

requires:
  - phase: 06-ux-visual-expansion
    plan: 01
    provides: useNexusApp hook, XState nexusAppMachine, Zustand bridge
  - phase: 06-ux-visual-expansion
    plan: 02
    provides: Dashboard page, AdapterCard, DataSourceIndicator
  - phase: 06-ux-visual-expansion
    plan: 03
    provides: financePageMachine, SpendingChart, TransactionTable, ActionCard

provides:
  - XState monitoringPageMachine with parallel regions (health, latency, activeTab)
  - React Flow v12 ServiceTopology with custom ServiceNode (status dots, P99 badges, pulse animation)
  - React Flow PipelineStageFlow with custom PipelineStageNode (animated borders per stage)
  - Recharts BarChart for P99/P95/P50 latency with 500ms target ReferenceLine
  - Error taxonomy (5 types) with classifyError, isRetryable, errorMessage
  - Framer Motion error state components (DegradedBanner, EmptyState, TimeoutSkeleton)
  - SQLite user preferences backend with optimistic concurrency
  - GET/PUT /admin/user/prefs endpoints with 409 conflict handling
  - useUserPrefs hook with optimistic updates
  - Navigation with 6 page routes and Framer Motion active indicator

affects: [dashboard, finance, chat, monitoring, pipeline, settings]

tech-stack:
  added: []
  patterns: [xstate-parallel-regions, react-flow-custom-nodes, recharts-barchart, framer-motion-layout-animation, error-taxonomy, optimistic-concurrency, dynamic-imports]

key-files:
  created:
    - ui_service/src/machines/monitoringPage.ts
    - ui_service/src/components/monitoring/ServiceTopology.tsx
    - ui_service/src/components/monitoring/LatencyChart.tsx
    - ui_service/src/components/monitoring/PipelineStageFlow.tsx
    - ui_service/src/lib/errors.ts
    - ui_service/src/components/ui/error-states.tsx
    - shared/auth/user_prefs.py
    - ui_service/src/hooks/useUserPrefs.ts
  modified:
    - ui_service/src/app/monitoring/page.tsx
    - ui_service/src/components/nav/Navbar.tsx
    - ui_service/src/app/layout.tsx
    - orchestrator/admin_api.py
    - ui_service/src/machines/financePage.ts

key-decisions:
  - "XState parallel regions for health (30s) + latency (60s) + activeTab — independent polling cycles"
  - "React Flow custom ServiceNode embeds shadcn/ui patterns with Framer Motion pulse on DEGRADED"
  - "Error taxonomy drives XState isRetryableError guard — TIMEOUT and DEGRADED_PROVIDER are retryable"
  - "User prefs stored in SQLite with WAL mode and optimistic concurrency versioning"
  - "Navbar uses Framer Motion layoutId for spring-animated active indicator"
  - "Dynamic imports (next/dynamic ssr:false) for React Flow and Recharts — only XState in initial load"

patterns-established:
  - "XState parallel regions: health || latency || activeTab for independent regional state"
  - "React Flow v12 custom nodes: ServiceNode and PipelineStageNode with Handle-based wiring"
  - "Error taxonomy: classifyError -> NexusErrorType -> isRetryable -> XState guard"
  - "Optimistic concurrency: version field in SQLite, 409 on conflict, client re-fetch and merge"
  - "Framer Motion layoutId: spring-based active indicator animation in Navbar"

duration: ~21min
completed: 2026-02-17
---

# Phase 06 Plan 04: Monitoring + Error Taxonomy + Preferences Summary

**XState monitoring page with React Flow topology + Recharts latency, standardized error taxonomy, user preferences persistence, and navigation update**

## Performance

- **Duration:** ~21 min
- **Completed:** 2026-02-17
- **Tasks:** 3
- **Files created:** 8
- **Files modified:** 5

## Accomplishments

- XState monitoringPageMachine with 3 parallel regions: health (30s auto-refresh), latency (60s auto-refresh), activeTab (overview/modules/alerts)
- React Flow v12 ServiceTopology with custom ServiceNode showing status dots (green/amber/red), P99 badges with destructive variant > 500ms, Framer Motion pulse animation on DEGRADED status
- envelopeToTopology() transforms CapabilityEnvelope features into React Flow nodes/edges with 3-row layout (orchestrator top, services middle, UI bottom)
- Recharts BarChart for P99/P95/P50 latency per service with grouped bars and 500ms ReferenceLine target
- React Flow PipelineStageFlow with custom PipelineStageNode — stage-specific border colors (scaffold blue, implement purple, test amber, repair red) + animated borders for in-progress stages
- Agent runs table with Build ID, Module, Stage, Status, Duration, Attempts columns
- Grafana dashboard tabs driven by XState activeTab region (overview/modules/alerts)
- Monitoring page uses dynamic imports (next/dynamic ssr:false) for React Flow and Recharts
- Error taxonomy with 5 NexusErrorType values: NOT_AUTHORIZED, NOT_CONFIGURED, DEGRADED_PROVIDER, TOOL_SCHEMA_MISMATCH, TIMEOUT
- classifyError maps HTTP status codes, error names, and message patterns to error types
- isRetryable maps to XState isRetryableError guard (TIMEOUT and DEGRADED_PROVIDER are retryable)
- DegradedBanner with Framer Motion entry/exit (opacity + y) — amber warning with retry button
- EmptyState with Framer Motion scale-in animation — centered placeholder with action button
- TimeoutSkeleton with delayed overlay — "Taking longer than usual..." after 5s
- UserPrefsStore SQLite backend with WAL mode, user_prefs table (user_id PK, prefs_json, version, updated_at)
- Optimistic concurrency via version field — set_prefs raises ConflictError on version mismatch
- GET/PUT /admin/user/prefs endpoints with 409 conflict handling
- useUserPrefs hook with optimistic local updates, version tracking in ref, re-fetch on 409
- Navbar updated with 6 page routes (Dashboard, Modules, Finance, Monitoring, Pipeline, Settings)
- Framer Motion layoutId spring animation on active page indicator
- Responsive hamburger menu on mobile with motion.div dropdown
- Build passes all 6 pages with zero errors

## Task Commits

1. **Task 1: XState monitoring machine + React Flow topology + Recharts latency** - `c44e76f` (feat)
2. **Task 2: Error taxonomy + Framer Motion error states + user preferences** - `1dad40f` (feat)
3. **Task 3: Navigation update + full QA pass** - `0121c53` (feat)

## Files Created/Modified

### Created
- `ui_service/src/machines/monitoringPage.ts` - 237 lines, XState v5 parallel state machine
- `ui_service/src/components/monitoring/ServiceTopology.tsx` - 307 lines, React Flow v12 custom topology
- `ui_service/src/components/monitoring/LatencyChart.tsx` - 110 lines, Recharts BarChart with P99 target
- `ui_service/src/components/monitoring/PipelineStageFlow.tsx` - 217 lines, React Flow pipeline stages
- `ui_service/src/lib/errors.ts` - 119 lines, error taxonomy with 5 types
- `ui_service/src/components/ui/error-states.tsx` - 141 lines, 3 Framer Motion error components
- `shared/auth/user_prefs.py` - 171 lines, SQLite user prefs store with optimistic concurrency
- `ui_service/src/hooks/useUserPrefs.ts` - 126 lines, optimistic update hook

### Modified
- `ui_service/src/app/monitoring/page.tsx` - 387 lines (was 92), XState-driven monitoring dashboard
- `ui_service/src/components/nav/Navbar.tsx` - 146 lines (was 77), 6 routes + Framer Motion
- `ui_service/src/app/layout.tsx` - 25 lines, NEXUS branding
- `orchestrator/admin_api.py` - Added ~95 lines for user prefs endpoints
- `ui_service/src/machines/financePage.ts` - Fixed type error in storeFinanceData action

## Decisions Made

- **XState parallel regions**: health (30s) + latency (60s) + activeTab run independently — no combinatorial explosion
- **React Flow custom nodes embed shadcn/ui patterns**: ServiceNode uses Card-like styling with Badges and color-mapped status dots
- **Error taxonomy drives XState guards**: isRetryable returns true for TIMEOUT and DEGRADED_PROVIDER, enabling auto-retry in state machines
- **SQLite WAL mode for user prefs**: Concurrent reads during optimistic writes, version field for conflict detection
- **Framer Motion layoutId for nav indicator**: Spring animation (bounce: 0.2, duration: 0.4) smoothly transitions between route changes
- **Dynamic imports for heavy libraries**: React Flow (~60KB) and Recharts (~40KB) loaded on-demand per page via next/dynamic

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed pre-existing type error in financePage.ts**
- **Found during:** Task 1 (build verification)
- **Issue:** `storeFinanceData` action compared event.type to `'xstate.done.actor.fetchFinanceData'` which XState v5 types don't allow in setup() registered actions
- **Fix:** Cast event to `any` for output access since the action is only called from onDone handler
- **Files modified:** `ui_service/src/machines/financePage.ts`
- **Commit:** `c44e76f` (included in Task 1 commit)

### Out-of-Scope Discoveries

**1. Pre-existing test failure: `test_fallback_order_matches_priority`**
- **Location:** `tests/unit/providers/test_fallback_chain.py`
- **Origin:** Phase 3 (commit 3954eb3)
- **Impact:** 1 test fails out of 702. Unrelated to Phase 6 UI changes. 701 tests pass.
- **Action:** Logged for future investigation. Not fixed (out of scope).

## Verification Results

- Monitoring page line count: 387 (>= 100 required)
- monitoringPage.ts line count: 237 (>= 60 required)
- ServiceTopology.tsx line count: 307 (>= 80 required)
- LatencyChart.tsx line count: 110 (>= 40 required)
- PipelineStageFlow.tsx line count: 217 (>= 50 required)
- useMachine(monitoringPageMachine) in monitoring page: 1 occurrence
- ReactFlow/xyflow in ServiceTopology: 5 occurrences
- BarChart/ReferenceLine in LatencyChart: 7 occurrences
- motion/framer in ServiceTopology: 3 occurrences
- Python user_prefs import: OK
- NOT_AUTHORIZED/DEGRADED_PROVIDER/TIMEOUT in errors.ts: 20 occurrences
- DegradedBanner/EmptyState/TimeoutSkeleton in error-states.tsx: 12 occurrences
- motion/framer in error-states.tsx: 7 occurrences
- isRetryable in errors.ts: 3 occurrences
- Dashboard/Modules/Finance/Monitoring/Pipeline/Settings in Navbar: 14 occurrences
- `npx next build`: All 6 pages compile successfully
- `make verify`: 701 passed, 1 pre-existing failure (unrelated)

## Issues Encountered

None caused by this plan. Pre-existing `financePage.ts` type error was auto-fixed (Rule 3).

## Next Phase Readiness

- Monitoring dashboard ready for real-time data when backend services are running
- Error taxonomy available for all pages to adopt via `classifyError()` + error state components
- User preferences backend ready for all pages to persist user settings
- Navigation complete for all 6 page routes
- Phase 6 UX/UI Visual Expansion complete (4/4 plans executed)

## Self-Check: PASSED

- monitoringPage.ts: FOUND
- ServiceTopology.tsx: FOUND
- LatencyChart.tsx: FOUND
- PipelineStageFlow.tsx: FOUND
- errors.ts: FOUND
- error-states.tsx: FOUND
- user_prefs.py: FOUND
- useUserPrefs.ts: FOUND
- Commit c44e76f: FOUND
- Commit 1dad40f: FOUND
- Commit 0121c53: FOUND

---
*Phase: 06-ux-visual-expansion*
*Completed: 2026-02-17*
