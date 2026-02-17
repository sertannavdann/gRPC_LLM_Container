---
phase: 06-ux-visual-expansion
plan: 01
subsystem: api, ui
tags: [pydantic, xstate, etag, capability-contract, zustand, recharts, framer-motion]

requires:
  - phase: 05-refactoring
    provides: Adapter lock/unlock base class, adapter registry, deduplication
provides:
  - CapabilityEnvelope Pydantic model (tools, modules, providers, adapters, features)
  - Three BFF endpoints (GET /capabilities, /feature-health, /config/version) with ETag
  - XState v5 nexusAppMachine with parallel regions (capability, dataSource, auth)
  - useNexusApp React hook bridging XState to components
  - Zustand store bridge for cross-page XState event dispatch
  - TypeScript type documentation for frontend consumption
  - npm packages installed (xstate, @xstate/react, recharts, framer-motion)
affects: [06-02, 06-03, 06-04]

tech-stack:
  added: [xstate@5.28.0, "@xstate/react@4.1.3", recharts@2.15.4, framer-motion@11.18.2]
  patterns: [capability-contract, etag-polling, xstate-parallel-regions, zustand-xstate-bridge]

key-files:
  created:
    - shared/contracts/ui_capability_schema.py
    - tests/unit/test_capability_contract.py
    - docs/ui_contract.md
    - ui_service/src/machines/nexusApp.ts
    - ui_service/src/hooks/useNexusApp.ts
    - ui_service/src/stores/nexusStore.ts
  modified:
    - orchestrator/admin_api.py
    - ui_service/src/lib/adminClient.ts
    - ui_service/package.json

key-decisions:
  - "XState v5 setup() API for full TypeScript typing of machine context, events, guards"
  - "ETag as SHA-256 of serialized envelope JSON for conditional polling"
  - "Zustand bridge pattern: xstateSend registered by useNexusApp, called by chat/other pages"

patterns-established:
  - "Capability-driven UI: all pages derive state from GET /capabilities envelope"
  - "XState parallel regions: independent concerns (capability, dataSource, auth) without combinatorial explosion"
  - "Invoked actors for async operations: ETag polling managed by XState, not setInterval"
  - "Zustand-XState bridge: imperative triggers dispatch events into statechart"

duration: ~25min
completed: 2026-02-16
---

# Phase 06 Plan 01: Capability Contract + XState Infrastructure Summary

**Pydantic CapabilityEnvelope with ETag BFF endpoints, XState v5 root machine with parallel capability/dataSource/auth regions, and visualization toolkit npm packages**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-02-16
- **Tasks:** 4
- **Files modified:** 10

## Accomplishments
- CapabilityEnvelope Pydantic model covering tools, modules, providers, adapters, features with typed serialization
- Three admin BFF endpoints (GET /capabilities, /feature-health, /config/version) with ETag conditional responses and 304 Not Modified support
- 13 contract tests for schema models, ETag determinism, and feature health derivation
- TypeScript interface documentation with endpoint specs, polling patterns, and XState integration notes
- XState v5 nexusAppMachine with 3 parallel regions: capability polling (30s via invoked actor), dataSource (live/mock/offline), auth
- useNexusApp hook providing typed state access via @xstate/react useMachine
- Zustand store bridge enabling cross-page XState event dispatch (CAPABILITY_REFRESH_REQUESTED)
- npm packages installed: xstate, @xstate/react, recharts, framer-motion

## Task Commits

1. **Task 1: Pydantic capability schema** - `fa26e2f` (feat)
2. **Task 2: Three BFF endpoints with ETag support** - `45e6e71` (feat)
3. **Task 3: Contract tests + TypeScript documentation** - `ae4ec0e` (feat)
4. **Task 4: XState root machine + useNexusApp hook + Zustand bridge** - `64a840c` (feat)

## Files Created/Modified
- `shared/contracts/ui_capability_schema.py` - Pydantic models for CapabilityEnvelope and sub-models
- `shared/contracts/__init__.py` - Package marker
- `orchestrator/admin_api.py` - Three BFF endpoints with ETag conditional responses
- `tests/unit/test_capability_contract.py` - 13 contract tests for schemas and health derivation
- `docs/ui_contract.md` - TypeScript interface documentation with endpoint specs
- `ui_service/src/machines/nexusApp.ts` - XState v5 root application statechart
- `ui_service/src/hooks/useNexusApp.ts` - React hook bridging XState to components
- `ui_service/src/stores/nexusStore.ts` - Zustand store with XState event bridge
- `ui_service/src/lib/adminClient.ts` - Extended with capability, health, config methods
- `ui_service/package.json` - Added xstate, @xstate/react, recharts, framer-motion

## Decisions Made
- Used XState v5 setup() API for full TypeScript typing of machine context, events, and guards
- ETag computed as SHA-256 of serialized envelope JSON for deterministic conditional polling
- Zustand bridge pattern: useNexusApp registers xstateSend on mount, chat/other pages dispatch via store

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
- Test file (tests/unit/test_capability_contract.py) was committed but missing from working directory post-execution; restored from git object store

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 06-02, 06-03, 06-04 dependencies satisfied
- useNexusApp hook ready for dashboard/finance/monitoring pages
- Zustand bridge ready for chat -> XState event dispatch
- npm packages ready for Recharts charts, Framer Motion animations, React Flow topology

---
*Phase: 06-ux-visual-expansion*
*Completed: 2026-02-16*
