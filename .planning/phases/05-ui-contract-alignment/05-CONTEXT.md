# Phase 05 — UI Contract Alignment: Context

> User decisions from planning discussion

---

## Problem Statement

The NEXUS UI is fragile. Pages hardcode assumptions about backend state, fixes create new bugs, and there is no contract between what the backend can do and what the UI renders. The UI must become **capability-driven**: the backend declares what features/modules/providers are available and in what state, and the UI renders truthfully from that contract.

## Decisions

### Locked (NON-NEGOTIABLE)

1. **Capability-driven UI**: All pages derive their rendered state from a `GET /capabilities` backend contract endpoint — not from hardcoded lists or assumptions.
2. **v0 Premium ($20/mo) for visual shell generation**: v0.dev generates Next.js 14 + shadcn/ui + Tailwind TSX pages. It does NOT wire to backend APIs.
3. **Cursor Pro ($20/mo) for repo-aware wiring**: Cursor reads the 17K-line codebase and wires v0-generated shells to real APIs, state stores, error handling, RBAC. It does NOT generate page layouts from scratch.
4. **Workflow rule**: v0 generates visual shell → paste into repo → Cursor wires to real data/APIs and refactors across files.
5. **BFF contract first**: Backend capability endpoints must exist before any UI page is rewritten. The UI must never assume feature availability.
6. **Structured error taxonomy**: NOT_AUTHORIZED, NOT_CONFIGURED, DEGRADED_PROVIDER, TOOL_SCHEMA_MISMATCH, TIMEOUT — mapped to UI toast/banner components.
7. **ETag-based polling**: Capability endpoint supports ETag for conditional fetch (If-None-Match), 30s polling interval.
8. **Per-user preferences persistence**: SQLite `user_prefs` table for dashboard layout, provider ordering, module favorites, monitoring tab, theme.

### Deferred Ideas

- Mobile-responsive overhaul (desktop-first for now)
- Drag-and-drop dashboard layout customization
- Real-time WebSocket push (SSE polling is sufficient)
- Marketplace browsing UI (Phase 7)
- Onboarding wizard for first-time users (may add in polish wave)

### Claude's Discretion

- Pydantic model naming for capability schemas
- Exact polling interval (30s suggested, adjust if needed)
- Toast library choice (sonner or similar)
- ETag generation strategy (hash of serialized state)
- SQLite table schema for user_prefs

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
- **Budget**: $20 credits/mo + $2 free daily credits on login. v0 Pro model at $1.50/$7.50 per 1M input/output tokens.
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

## Scope

This phase makes the UI truthful and resilient by:
1. Creating a backend capability contract (BFF endpoint)
2. Rewriting 5 key pages as capability-driven components
3. Adding per-user preferences persistence
4. Implementing structured error taxonomy with UI mapping
