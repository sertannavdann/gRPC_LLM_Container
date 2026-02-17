---
phase: 05-refactoring
plan: 04
subsystem: service-dependencies
tags: [refactoring, dependencies, dashboard, sse, credential-store]
dependency_graph:
  requires:
    - phase-05-plan-03
  provides:
    - optional-otel-boot-path
    - no-orchestrator-dashboard-credential-cycle
    - deduplicated-sse-collection
    - unknown-service-state-ui
  affects:
    - dashboard_service/main.py
    - dashboard_service/pipeline_stream.py
    - orchestrator/admin_api.py
    - ui_service/src/components/pipeline/ServiceNode.tsx
tech_stack:
  added: []
  patterns:
    - optional dependency guard
    - direct local dependency over cross-service proxy
    - single-pass polling per SSE cycle
key_files:
  modified:
    - dashboard_service/main.py
    - dashboard_service/requirements.txt
    - dashboard_service/pipeline_stream.py
    - orchestrator/admin_api.py
    - ui_service/src/components/pipeline/ServiceNode.tsx
decisions:
  - decision: "Treat FastAPI OpenTelemetry instrumentation as optional at runtime"
    rationale: "Missing package must not crash dashboard startup"
  - decision: "Use local CredentialStore in orchestrator instead of dashboard proxy endpoints"
    rationale: "Break circular dependency and reduce network hop failure modes"
  - decision: "Remove dashboard self-probe and deduplicate list_all_flat/list_modules calls"
    rationale: "Reduce steady-state SSE polling overhead and avoid self-health noise"
  - decision: "Use unknown as default gRPC service state"
    rationale: "Idle implied certainty; unknown more accurately reflects undiscovered runtime state"
metrics:
  tasks_completed: 4
  files_modified: 5
  major_dependency_cycles_removed: 1
  sse_collection_calls_reduced_percent: 50
  completed_at: "2026-02-17"
---

# Phase 05 Plan 04: Service Dependency Cleanup Summary

## Summary

Completed the Phase 05-04 cleanup wave to remove service dependency anti-patterns introduced during prior UI integration work. The changes focused on runtime resilience (optional OpenTelemetry import), architectural decoupling (local credential store calls), and lower polling cost in dashboard SSE updates.

## What Changed

1. **Dashboard startup resilience**
   - `dashboard_service/main.py` now wraps `FastAPIInstrumentor` import in `try/except` and gates instrumentation behind `_HAS_FASTAPI_INSTRUMENTOR`.
   - Dashboard boots whether or not `opentelemetry-instrumentation-fastapi` is installed.

2. **Circular credential proxy removal**
   - `orchestrator/admin_api.py` now uses `_credential_store.has_credentials/store/delete` directly.
   - Removed orchestrator credential HTTP proxy path to dashboard module-credential endpoints.
   - Best-effort uninstall credential cleanup also uses local store.

3. **SSE data flow deduplication**
   - `dashboard_service/pipeline_stream.py` removes dashboard self-probe.
   - Per-cycle reads are deduplicated: adapter registry and module list are each fetched once and reused.
   - gRPC-discovered services now default to `unknown` rather than `idle`.

4. **Unknown state UI support**
   - `ui_service/src/components/pipeline/ServiceNode.tsx` adds explicit `unknown` rendering (type + color + icon).

## Verification

Executed and passed:
- `grep -c "_HAS_FASTAPI_INSTRUMENTOR" dashboard_service/main.py` → `3`
- `grep -c "dashboard.*module-credentials" orchestrator/admin_api.py` → `0`
- `grep -c "_credential_store\\." orchestrator/admin_api.py` → `4`
- `grep -c "localhost:8001" dashboard_service/pipeline_stream.py` → `0`
- `grep -c "list_all_flat" dashboard_service/pipeline_stream.py` → `1`
- `grep -c '"idle"' dashboard_service/pipeline_stream.py` → `0`
- `grep -c "unknown" dashboard_service/pipeline_stream.py` → `2`
- `npx --yes next build` (from `ui_service/`) → success

## Outcome

- Dashboard no longer fails fast on missing optional instrumentation package.
- Orchestrator credential APIs no longer require dashboard availability.
- Dashboard SSE loop performs fewer repetitive operations and avoids self-probe noise.
- Unknown service state is represented consistently from backend stream to frontend node rendering.

## Self-Check

PASSED — all 05-04 must-haves and verification checks are satisfied.
