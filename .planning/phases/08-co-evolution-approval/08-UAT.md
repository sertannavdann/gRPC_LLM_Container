---
status: testing
phase: 08-co-evolution-approval
source: 08-01-SUMMARY.md .. 08-13-SUMMARY.md (13 plans)
started: 2026-08-22T00:00:00Z
updated: 2026-08-22T00:00:00Z
---

## Current Test

number: 1
name: Cold Start Smoke Test
expected: |
  From a stopped stack: `make up` (or `docker compose up -d`). All services boot without
  errors — orchestrator (gRPC 50054 + admin :8003), dashboard (:8001), ui (:3000/:5001),
  llm, chroma, bridge, sandbox, prometheus, grafana, cadvisor, otel-collector, tempo.
  Orchestrator log shows the retention worker started. `curl http://localhost:8003/admin/health`
  and `curl http://localhost:8001/health` (or /) return OK. UI loads in browser.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: From stopped stack, `make up` boots all services cleanly; admin :8003 health OK, dashboard :8001 OK, UI loads; orchestrator log shows retention worker started (no startup errors from new middleware/worker wiring).
result: [pending]

### 2. Pending Module Appears on Pipeline Page
expected: With the stack up, a module in VALIDATED state appears on the Pipeline page as a node with a "Needs Review" badge within ~2s (SSE stream), without page refresh. If no validated module exists, build one via chat ("build me a ...") or validate a draft first.
result: [pending]

### 3. Review Panel — Five Layers + Walkthrough + Blueprint
expected: Clicking the pending module opens the detail panel with five collapsible sections (blueprint, code, validation report, credentials, repair history), the BlueprintCard expands into the module structure view, and a plain-language LLM walkthrough is displayed.
result: [pending]

### 4. Approve Flow + Audit Record
expected: Approve (with an admin key) transitions the module to APPROVED — node state updates live. `GET :8003/admin/audit-logs` (admin key) shows a module_approved event carrying YOUR user id (not the org id) and a bundle hash. `GET /admin/audit-logs/verify` returns valid: true.
result: [pending]

### 5. Install Gate Enforcement
expected: Attempting to install a module that is NOT approved (via chat "install ..." or the API) is refused with a "not been approved" error. Installing an APPROVED module succeeds.
result: [pending]

### 6. Reject Semantics
expected: Reject WITH feedback sends the module back through a repair cycle (status returns to validating, then pending again). Reject WITHOUT feedback is terminal — status FAILED, and the module is queued for artifact GC.
result: [pending]

### 7. Chat Approval Card
expected: In chat, asking to review/approve a pending module renders an ApprovalActionCard (blueprint summary, optional feedback box, approve + two-click confirm-reject buttons). Actions enforce the same RBAC as the UI — a viewer-role key cannot approve.
result: [pending]

### 8. Generic Module Panel (D-07)
expected: For an INSTALLED module, the detail panel offers a Run action; running shows the module's data as key/value rows and declared chart artifacts rendered from the canonical envelope. Non-installed modules do not expose Run.
result: [pending]

### 9. Rate Limiting
expected: Rapid-fire requests to an admin endpoint (e.g. 5+ quick `curl` calls to :8003/admin/health with a key, or the bootstrap endpoint) eventually return HTTP 429 with a Retry-After header. Normal usage is unaffected.
result: [pending]

### 10. Playwright SSE E2E (REQ-018)
expected: With the stack up: `make ui-e2e` runs 3 specs (connect / reconnect / error handling) against the real SSE stream — all pass.
result: [pending]

### 11. Grafana Observability
expected: Grafana (:3000 of grafana service) shows the NEXUS Module System dashboard including the "Audit Trail" row (events-by-action timeseries + 24h stats, write-failures stat at 0), and module/approval activity is visible after the actions above.
result: [pending]

## Summary

total: 11
passed: 0
issues: 0
pending: 11
skipped: 0
blocked: 0

## Gaps

[none yet]
