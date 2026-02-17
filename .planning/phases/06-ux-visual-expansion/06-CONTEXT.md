# Phase 06 — UX/UI Visual Expansion: Context

> User decisions from planning discussion

---

## Problem Statement

The NEXUS UI is fragile — pages hardcode assumptions about backend state, fixes create new bugs, and there is no contract between what the backend can do and what the UI renders. The dashboard shows mock data silently when the backend is unreachable. The finance page is an iframe to a Docker-internal address that browsers cannot resolve. The chat module sends messages but cannot trigger adapter actions or refresh the dashboard. Monitoring shows basic stats without P99 latency visibility.

This phase builds a designed UX/UI for visual expansion of the stabilized multi-feature services, targeting P99 reliability across all active services. All pages render from a backend capability contract — the UI never assumes feature availability. State management uses XState v5 statecharts for deterministic, visualizable page state control.

## Academic Anchors

### Event-Driven Microservice Orchestration Principles (EDMO)

- **T6 (CQRS)**: Capability endpoint serves as read-optimized query model, independent from service write paths
- **T1 (Saga Pattern)**: Multi-step UI operations (connect adapter -> test -> enable) modeled as orchestrated sagas with compensating actions
- **T4 (Retry with Jitter)**: XState invoked actors manage retry with exponential backoff for transient failures
- **§6.1 (Performance Benchmarks)**: Event-driven latency 1.2s vs 10-30s traditional; 43.7% throughput improvement

### Agentic Builder-Tester Pattern for NEXUS

- **§5 (Agent Monitoring Dashboards)**: Observability patterns for agent build runs, repair attempts, validation reports
- **§9 (Monitor Agent)**: Fidelity validation between stages surfaces in pipeline viewer

### Harel Statecharts (XState v5 Foundation)

- **Parallel (orthogonal) state regions**: Model independent concerns (data source status, auth state, capability freshness) without combinatorial explosion
- **Guards**: Conditional transitions based on CapabilityEnvelope data (adapter locked? provider degraded?)
- **Invoked actors**: Manage async operations (ETag polling, connection tests) as first-class citizens within the state machine
- **Actor model**: Each page's state machine is an independent actor that communicates via events, matching microservice event-driven architecture

## Visualization Toolkit

Four libraries cover every visualization requirement in Phase 6 while remaining entirely within the Next.js + TypeScript ecosystem. Each library handles a distinct concern with no overlap:

| Library | Version | Role | Bundle (gzip) | Phase 6 Plans |
|---|---|---|---|---|
| **XState** | v5 | Statechart state management (Harel formalism) | ~12 KB | All pages — state control |
| **React Flow** | v12 (xyflow) | Node-based interactive graphs | ~60 KB | 06-04 Monitoring topology, Pipeline |
| **Recharts** | v2.15+ | SVG charts (line, bar, donut, area) | ~40 KB | 06-03 Finance charts, 06-04 Latency |
| **Framer Motion** | v11+ | State transition animations | ~32 KB | All pages — animated transitions |

**Total additional bundle: ~144 KB gzip** — React Flow is already a NEXUS dependency, so the effective new addition is ~84 KB.

### npm Package Manifest

```json
{
  "dependencies": {
    "@xyflow/react": "^12.0.0",
    "xstate": "^5.18.0",
    "@xstate/react": "^4.1.0",
    "recharts": "^2.15.0",
    "framer-motion": "^11.15.0"
  }
}
```

### Bundle Impact

| Package | Raw Size | Gzip | Tree-Shakeable | SSR Compatible |
|---|---|---|---|---|
| xstate | 45 KB | ~12 KB | Yes (setup API) | Yes |
| @xstate/react | 8 KB | ~3 KB | Yes | Yes |
| @xyflow/react | 180 KB | ~60 KB | Partial | Yes (v12) |
| recharts | 120 KB | ~40 KB | Partial | Yes (with initialDimension) |
| framer-motion | 100 KB | ~32 KB | Yes | Yes |

With `next/dynamic`, the actual initial page load adds only XState (~15 KB) since React Flow, Recharts, and Framer Motion load on-demand per page.

## Integration Architecture

### State Flow

```
CapabilityEnvelope (Backend REST)
        |
        v
+----------------------+
|  XState Root Machine  | <- CAPABILITY_REFRESH_REQUESTED (from chat tool calls)
|  (nexusAppMachine)    |
|  +-- capability       | -> polls every 30s via invoked actor
|  +-- dataSource       | -> derives Live/Mock/Offline from envelope
|  +-- auth             | -> tracks auth expiry
+----------+-----------+
           | state snapshots
           v
+----------------------+
|  Page-Level Machines  |
|  +-- financePageM.    | -> locked/unlocked hierarchy
|  +-- monitoringPageM. | -> parallel: health || latency || tabs
|  +-- dashboardPageM.  | -> adapter actions, card grid state
+----------+-----------+
           | state.matches('...')
           v
+--------------------------------------+
|  React Components (Next.js 14)       |
|  +-- React Flow    -> topology/pipe  |
|  +-- Recharts      -> charts         |
|  +-- Framer Motion -> transitions    |
|  +-- shadcn/ui     -> cards/tables   |
+--------------------------------------+
```

### Hook Integration Pattern

```typescript
// hooks/useNexusApp.ts — bridges XState to React components
import { useMachine } from '@xstate/react';
import { nexusAppMachine } from '@/machines/nexusApp';

export function useNexusApp() {
  const [state, send] = useMachine(nexusAppMachine);

  return {
    envelope: state.context.envelope,
    isLoading: state.matches('capability.loading'),
    isError: state.matches('capability.error'),
    error: state.context.error,
    isLive: state.matches('dataSource.live'),
    isMock: state.matches('dataSource.mock'),
    isOffline: state.matches('dataSource.offline'),
    isAuthenticated: state.matches('auth.authenticated'),
    refresh: () => send({ type: 'CAPABILITY_REFRESH_REQUESTED' }),
  };
}
```

### Zustand Bridge for Cross-Page Events

```typescript
// stores/nexusStore.ts — bridges imperative triggers into XState events
export const useNexusStore = create((set) => ({
  xstateSend: null as ((event: any) => void) | null,
  setXStateSend: (send: (event: any) => void) => set({ xstateSend: send }),
  triggerCapabilityRefresh: () => {
    const { xstateSend } = useNexusStore.getState();
    xstateSend?.({ type: 'CAPABILITY_REFRESH_REQUESTED' });
  },
}));
```

## Decisions

### Locked (NON-NEGOTIABLE)

1. **Capability-driven UI**: All pages derive rendered state from `GET /capabilities` backend contract endpoint — not from hardcoded lists or assumptions.
2. **v0 Premium ($20/mo) for visual shell generation**: v0.dev generates Next.js 14 + shadcn/ui + Tailwind TSX pages. It does NOT wire to backend APIs.
3. **Cursor Pro ($20/mo) for repo-aware wiring**: Cursor reads the 17K-line codebase and wires v0-generated shells to real APIs, state stores, error handling, RBAC. It does NOT generate page layouts from scratch.
4. **Workflow rule**: v0 generates visual shell -> paste into repo -> Cursor wires to real data/APIs and refactors across files.
5. **Finance is a native page**: No iframe. Single API proxy + lock/unlock gating from Phase 5 adapter lock/unlock. Transaction table, category breakdown, spending trend.
6. **Chat bidirectional**: Chat can trigger adapter actions (calendar events, weather queries) via structured action responses. Dashboard refreshes immediately after tool calls.
7. **P99 target**: All active service endpoints respond < 500ms at p99. Monitoring page displays p50/p95/p99 per service.
8. **Error states visible, not silent**: DegradedBanner, data source indicator (Live/Mock/Offline), TimeoutSkeleton. No silent mock fallback.
9. **ETag-based polling**: Capability endpoint supports ETag for conditional fetch (If-None-Match). XState invoked actor manages 30s polling interval.
10. **Per-user preferences persistence**: SQLite `user_prefs` table for dashboard layout, provider ordering, module favorites, monitoring tab, theme.
11. **XState v5 for statechart state management**: Root application machine (nexusAppMachine) with parallel regions for capability, dataSource, and auth. Page-level machines for finance, monitoring, and dashboard. Replaces scattered `useState` + `useEffect` patterns with deterministic, visualizable state models.
12. **React Flow v12 for topology visualization**: Service topology graph on monitoring page, pipeline stage flow for build runs. Custom nodes embed shadcn/ui components. Already a NEXUS dependency.
13. **Recharts v2.15+ for data charts**: Finance spending trend (LineChart), category breakdown (PieChart/donut), monitoring latency (BarChart with ReferenceLine). SSR compatible via `initialDimension`.
14. **Framer Motion v11+ for state transitions**: AnimatePresence for page content transitions driven by XState state changes. Animated indicators for data source status. Layout animations for adapter cards.

### Deferred Ideas

- Mobile-responsive overhaul (desktop-first for now)
- Drag-and-drop dashboard layout customization
- Real-time WebSocket push (SSE polling is sufficient)
- Marketplace browsing UI (Phase 9)
- Onboarding wizard for first-time users
- Stately Studio visual debugger integration (future developer experience enhancement)

### Claude's Discretion

- Pydantic model naming for capability schemas
- Exact polling interval (30s suggested, adjust if needed)
- Toast library choice (sonner or similar)
- ETag generation strategy (hash of serialized state)
- SQLite table schema for user_prefs
- XState machine file organization (single `machines/` directory vs co-located)
- Framer Motion animation durations and easing curves
- React Flow node layout algorithm (manual positions vs auto-layout)
- Recharts color palette for charts (as long as it supports dark mode via CSS variables)

## Tool Usage Guide (v0 + Cursor)

### Daily Workflow

```
Morning (v0.dev — visual generation):
  1. Open v0.dev in browser
  2. Prompt for the page/component (use prompts from plan tasks)
  3. Iterate 2-3 times until visual layout is right
  4. Copy TSX into your repo under ui_service/src/

Afternoon (Cursor — repo-aware wiring):
  1. Open repo in Cursor
  2. Use Composer: "Wire this page to XState machine,
     add ETag caching via invoked actor, handle loading/error/degraded states
     with Framer Motion transitions, respect RBAC permissions from auth middleware"
  3. Review staged diffs, accept file by file
  4. Run tests, commit
```

### v0 Premium ($20/mo)

- **What it does**: Generates Next.js 14 + shadcn/ui + Tailwind components from prompts. Outputs copy-pasteable TSX. Supports Figma import.
- **What it doesn't do**: Wire to XState machines, gRPC clients, state stores, or backend APIs. Does not understand your codebase.
- **Budget**: $20 credits/mo + $2 free daily credits on login.
- **Best for**: Page layouts, component visual design, responsive grids, dark mode variants, empty/error state visuals.

### Cursor Pro ($20/mo)

- **What it does**: Reads entire 17K-line codebase. Composer mode edits multiple files with staged diffs. Understands imports/types.
- **What it doesn't do**: Generate page layouts from scratch as well as v0.
- **Budget**: 500 fast premium requests/mo, unlimited tab completions, Composer multi-file edits.
- **Best for**: XState machine definitions, API wiring, error handling, RBAC integration, state store updates, multi-file refactoring, adminClient.ts extension.

### Cost Control

| Item | Cost | Credits/Limits |
|------|------|---------------|
| v0 Premium | $20/mo | $20 credits/mo + $2 free daily |
| Cursor Pro | $20/mo | 500 fast requests/mo |
| **Total** | **$40/mo** | |
