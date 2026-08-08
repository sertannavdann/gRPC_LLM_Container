# Phase 7: Audit Trail - Context

**Gathered:** 2026-08-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Immutable audit log for Admin API mutations. Three deliverables per ROADMAP.md:

1. **Audit log storage** (REQ-010) — append-only SQLite `audit_events` table with fields: id, timestamp, org_id, actor_id, action, resource_type, resource_id, before_state, after_state, ip_address
2. **Audit decorator** (REQ-011) — `@audit_action(action, resource_type)` for Admin API endpoints, auto-capturing before/after state on config, module, and credential mutations
3. **Audit query API** (REQ-012) — `GET /admin/audit-logs` with date/actor/action/resource filters, `GET /admin/audit-logs/export` CSV export, Grafana audit panel in the NEXUS dashboard

This phase records mutations; it does not add new mutation capabilities, approval flows (Phase 8), or SSO/enterprise identity (Phase 9).

</domain>

<decisions>
## Implementation Decisions

### Audit Sink Unification
- **D-01: Single queryable sink.** The new SQLite audit store is THE audit log for the platform. `DevModeAuditLog` dual-writes: its append-only JSONL files are preserved (binding constraint from Phase 8 D-10 — lightweight JSONL audit records survive artifact purges), but every dev-mode event is also written to the SQLite `audit_events` table so all audit queries hit one store. `BuildAuditLog` remains a per-build artifact (attempt records, failure fingerprints) and is NOT merged — it is build telemetry, not a mutation audit.

### Immutability Enforcement
- **D-02: Triggers + hash chain.** SQLite triggers `RAISE(ABORT)` on any UPDATE or DELETE against `audit_events`. Each row additionally stores `prev_hash` — a SHA-256 over the previous row's canonical serialization — making the log tamper-evident, not just append-only by convention. Verification of the chain is exposed as a check (admin endpoint or CLI) so tampering is detectable, fitting the "Enterprise Foundation — Audit" milestone.

### Audit Write Failure Semantics
- **D-03: Fail-closed.** If the audit insert fails, the mutation is rejected (HTTP 500 with explicit error; no partial success). Auditability is the compliance guarantee this phase exists to provide — a mutation that cannot be audited must not happen. This deliberately diverges from Phase 2 metering's fail-open choice: metering is billing telemetry, audit is a correctness guarantee. SQLite local writes make the added failure risk negligible; use the established WAL pattern (user_prefs) for write reliability under load.

### Before/After State Capture
- **D-04: Full JSON snapshots with mandatory redaction.** `before_state`/`after_state` store full JSON snapshots of the resource so state at any point in time is reconstructible. A redaction registry strips secret values before persistence: credential values, API keys, and tokens are never stored — replaced with `[REDACTED]` plus a SHA-256 fingerprint of the value so change detection still works without disclosure. Redaction is enforced in the audit store layer (not per-endpoint discipline), so no code path can accidentally persist a secret.

### Coverage Scope
- **D-05: Audit at the shared store layer — all mutation paths converge.** Coverage includes:
  1. Orchestrator Admin API (:8003) — all ~30 mutation endpoints (routing config, modules, drafts, rollback, credentials, API keys, prefs, bootstrap)
  2. Dashboard admin mutations (:8001) — `/admin/credentials`, `/admin/module-credentials/*`, `/admin/disconnect`
  3. Chat-tool mutations — `ModuleAdminTool` / `ModulePipelineTool` actions that mutate state (enable/disable, promote, rollback, credential ops) write audit events directly at the operation layer, so conversational mutations cannot bypass the audit trail.

  The `@audit_action` decorator is the HTTP-endpoint convenience wrapper; the audit store's `record()` API is the underlying primitive tools call directly. Phase 8's chat approval (D-02/D-17/D-19 in 08-CONTEXT.md) depends on this: approve/reject decisions must land in this audit log with actor identity, timestamp, and artifact hash regardless of surface (UI or chat).

### Cross-Phase Contract (binding on Phase 8)
- **D-06:** The audit store API must accept Phase 8's approval events: actor identity, timestamp, artifact hash for every approve/reject decision (08-CONTEXT.md D-19). Design the `record()` signature so `details`/state fields carry artifact hashes without schema change.

### Claude's Discretion
- Exact SQLite schema DDL (index strategy for date/actor/action/resource filters), DB file location under `data/`
- Hash-chain canonical serialization format and genesis-row handling
- Redaction registry structure and which fields beyond credentials/keys/tokens it covers
- `@audit_action` decorator implementation (how before-state is read per resource type)
- CSV export streaming strategy and row limits
- Grafana audit panel layout and queries (audit event rate, mutations by actor/action)
- Whether dual-write from `DevModeAuditLog` is synchronous or via a small adapter shim
- Actor representation for tool-invoked mutations when no HTTP request context exists (e.g. `chat:{session/api-key id}`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & roadmap
- `.planning/ROADMAP.md` — Phase 7 section (lines ~370-389): deliverables, exact `audit_events` field list
- `.planning/REQUIREMENTS.md` — REQ-010, REQ-011, REQ-012 acceptance criteria

### Prior phase decisions that bind this phase
- `.planning/phases/08-co-evolution-approval/08-CONTEXT.md` — D-10 (JSONL audit records preserved after artifact purges), D-19 (approve/reject recorded with actor identity, timestamp, artifact hash in the audit log); Phase 8 executes concurrently — coordinate the audit store contract
- `.planning/phases/05-refactoring/05-CONTEXT.md` — BaseTool/CompositeTool architecture (ModuleAdminTool/ModulePipelineTool are the chat mutation surface to audit), ToolResult envelope "feeds metering and audit"
- `.planning/phases/06-ux-visual-expansion/06-CONTEXT.md` — no-silent-fallback rule, SQLite WAL user_prefs pattern

### Research anchors
- `.planning/research/Event-Driven Microservice Orchestration Principles.md` — outbox pattern for immutable artifacts (audit-and-replay rationale)

### Backend contracts this phase builds on
- `shared/modules/audit.py` — existing `AuditEvent`, `DevModeAuditLog` (JSONL, `log_action()`/`get_events()`), `BuildAuditLog`; D-01 dual-write integrates here
- `shared/auth/middleware.py` — `request.state.user` / `request.state.org_id` (actor identity source)
- `shared/auth/rbac.py` — permission matrix (audit query API needs a read permission tier)
- `shared/auth/user_prefs.py` — SQLite WAL pattern template
- `orchestrator/admin_api.py` — the ~30 mutation endpoints to decorate (FastAPI `_app`, port 8003)
- `dashboard_service/main.py` — dashboard admin mutations (`/admin/credentials`, `/admin/module-credentials/*`, `/admin/disconnect`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DevModeAuditLog` / `AuditEvent` (shared/modules/audit.py) — existing append-only JSONL audit with actor/action/details shape; the new store generalizes this pattern to SQLite + org scoping + before/after state
- Auth middleware (shared/auth/middleware.py) — already attaches `User` and `org_id` to `request.state`; `actor_id` and `ip_address` come from here, no new auth work
- `APIKeyStore` SQLite pattern (shared/auth/api_keys.py) + user_prefs WAL pattern — templates for the audit store class
- Grafana provisioning (`nexus-modules.json` dashboard) — pattern for adding the audit panel
- Prometheus `ModuleMetrics` pattern (shared/observability/metrics.py) — optional audit event counters

### Established Patterns
- SQLite for all state stores (PROJECT.md hard constraint) — audit store follows; no new infra
- Fail-open metering (Phase 2) exists as contrast — D-03 deliberately chooses fail-closed for audit; do not copy the metering error-swallowing pattern
- ToolResult envelope with metadata (Phase 5 Wave 4) — tool-layer audit hooks ride on tool execute lifecycle
- Explicit registration / no magic (Phase 5) — decorator applied explicitly per endpoint, no auto-instrumentation sweep

### Integration Points
- `orchestrator/admin_api.py` — `@audit_action` on every mutation endpoint (PUT/PATCH/POST/DELETE list at lines 108-1671)
- `dashboard_service/main.py` — same decorator on dashboard admin mutations
- `tools/builtin/` ModuleAdminTool / ModulePipelineTool — direct `record()` calls for mutating actions
- `shared/modules/audit.py` — dual-write shim from `DevModeAuditLog.log_action()` into the new store
- Grafana + Prometheus config — audit panel (REQ-012)

</code_context>

<specifics>
## Specific Ideas

- User accepted all five recommendations as presented ("continue with recommendations") — the decision set above is the full intent; no additional stylistic requirements were expressed
- Tamper-evidence (hash chain) chosen over convention-only immutability specifically because this milestone is branded "Enterprise Foundation — Audit"

</specifics>

<deferred>
## Deferred Ideas

- Audit log retention/pruning tiers — interacts with REQ-017 trace retention (Phase 8's shared cleanup worker); audit rows are exempt from GC in this phase, revisit retention policy in Phase 9 enterprise tiering
- SIEM/webhook export of audit events (beyond CSV) — Phase 9 enterprise territory
- Cryptographic signing/anchoring of the hash chain (external timestamping) — enterprise hardening, Phase 9
- Audit UI page in ui_service (beyond Grafana panel) — candidate for Phase 9; REQ-012 only requires API + Grafana

</deferred>

---

*Phase: 7-audit-trail*
*Context gathered: 2026-08-08*
