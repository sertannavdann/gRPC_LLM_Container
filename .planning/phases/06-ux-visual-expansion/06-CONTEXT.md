# Phase 06 — UX/UI Visual Expansion: Context

> User decisions from planning discussion

---

## Problem Statement

The NEXUS UI is fragile — pages hardcode assumptions about backend state, fixes create new bugs, and there is no contract between what the backend can do and what the UI renders. The dashboard shows mock data silently when the backend is unreachable. The finance page is an iframe to a Docker-internal address that browsers cannot resolve. The chat module sends messages but cannot trigger adapter actions or refresh the dashboard. Monitoring shows basic stats without P99 latency visibility.

This phase builds a designed UX/UI for visual expansion of the stabilized multi-feature services, targeting P99 reliability across all active services. All pages render from a backend capability contract — the UI never assumes feature availability.

## Academic Anchors

### Event-Driven Microservice Orchestration Principles (EDMO)

- **T6 (CQRS)**: Capability endpoint serves as read-optimized query model, independent from service write paths
- **T1 (Saga Pattern)**: Multi-step UI operations (connect adapter → test → enable) modeled as orchestrated sagas with compensating actions
- **§6.1 (Performance Benchmarks)**: Event-driven latency 1.2s vs 10-30s traditional; 43.7% throughput improvement

### Agentic Builder-Tester Pattern for NEXUS

- **§5 (Agent Monitoring Dashboards)**: Observability patterns for agent build runs, repair attempts, validation reports
- **§9 (Monitor Agent)**: Fidelity validation between stages surfaces in pipeline viewer

## Decisions

### Locked (NON-NEGOTIABLE)

1. **Capability-driven UI**: All pages derive rendered state from `GET /capabilities` backend contract endpoint — not from hardcoded lists or assumptions.
2. **v0 Premium ($20/mo) for visual shell generation**: v0.dev generates Next.js 14 + shadcn/ui + Tailwind TSX pages. It does NOT wire to backend APIs.
3. **Cursor Pro ($20/mo) for repo-aware wiring**: Cursor reads the 17K-line codebase and wires v0-generated shells to real APIs, state stores, error handling, RBAC. It does NOT generate page layouts from scratch.
4. **Workflow rule**: v0 generates visual shell → paste into repo → Cursor wires to real data/APIs and refactors across files.
5. **Finance is a native page**: No iframe. Single API proxy + lock/unlock gating from Phase 5 adapter lock/unlock. Transaction table, category breakdown, spending trend.
6. **Chat bidirectional**: Chat can trigger adapter actions (calendar events, weather queries) via structured action responses. Dashboard refreshes immediately after tool calls.
7. **P99 target**: All active service endpoints respond < 500ms at p99. Monitoring page displays p50/p95/p99 per service.
8. **Error states visible, not silent**: DegradedBanner, data source indicator (Live/Mock/Offline), TimeoutSkeleton. No silent mock fallback.
9. **ETag-based polling**: Capability endpoint supports ETag for conditional fetch (If-None-Match), 30s polling interval.
10. **Per-user preferences persistence**: SQLite `user_prefs` table for dashboard layout, provider ordering, module favorites, monitoring tab, theme.

### Deferred Ideas

- Mobile-responsive overhaul (desktop-first for now)
- Drag-and-drop dashboard layout customization
- Real-time WebSocket push (SSE polling is sufficient)
- Marketplace browsing UI (Phase 9)
- Onboarding wizard for first-time users

### Claude's Discretion

- Pydantic model naming for capability schemas
- Exact polling interval (30s suggested, adjust if needed)
- Toast library choice (sonner or similar)
- ETag generation strategy (hash of serialized state)
- SQLite table schema for user_prefs
- Chart library for finance page (recharts or similar)

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
  2. Use Composer: "Wire this page to GET /capabilities endpoint,
     add ETag caching, handle loading/error/degraded states,
     respect RBAC permissions from auth middleware"
  3. Review staged diffs, accept file by file
  4. Run tests, commit
```

### v0 Premium ($20/mo)

- **What it does**: Generates Next.js 14 + shadcn/ui + Tailwind components from prompts. Outputs copy-pasteable TSX. Supports Figma import.
- **What it doesn't do**: Wire to gRPC clients, state stores, or backend APIs. Does not understand your codebase.
- **Budget**: $20 credits/mo + $2 free daily credits on login.
- **Best for**: Page layouts, component visual design, responsive grids, dark mode variants, empty/error state visuals.

### Cursor Pro ($20/mo)

- **What it does**: Reads entire 17K-line codebase. Composer mode edits multiple files with staged diffs. Understands imports/types.
- **What it doesn't do**: Generate page layouts from scratch as well as v0.
- **Budget**: 500 fast premium requests/mo, unlimited tab completions, Composer multi-file edits.
- **Best for**: API wiring, error handling, RBAC integration, state store updates, multi-file refactoring, adminClient.ts extension.

### Cost Control

| Item | Cost | Credits/Limits |
|------|------|---------------|
| v0 Premium | $20/mo | $20 credits/mo + $2 free daily |
| Cursor Pro | $20/mo | 500 fast requests/mo |
| **Total** | **$40/mo** | |
