# Phase 8: Co-Evolution & Approval - Research

**Researched:** 2026-07-12
**Domain:** Human-in-the-loop approval gates for a self-evolving agent module system (React Flow/XState UI + FastAPI backend + SSE transport), plus three hardening deliverables (trace retention, SSE E2E tests, HTTP rate limiting)
**Confidence:** MEDIUM-HIGH — backend contracts and UI patterns are HIGH confidence (read directly from the codebase); the two observability-related deliverables (REQ-017 retention, REQ-018 Playwright/SSE) carry MEDIUM confidence because they depend on ecosystem-level tooling behavior verified only via web search, not Context7 (unavailable this session).

## Summary

Phase 8 is a wiring-and-UI phase, not a green-field build. Every backend primitive the approval gate needs already exists: `ModuleManifest.status` already defines `VALIDATED` and `APPROVED` as adjacent lifecycle states (`shared/modules/manifest.py`), the SSE pipeline stream already runs a 2-second `while True` loop (`dashboard_service/pipeline_stream.py`), `DraftManager`/`VersionManager`/`BuildAuditLog` already provide diff/validate/promote/audit primitives, and RBAC (`admin+` via `Permission.ADMIN_ALL`) already gates the equivalent `validate_draft`/`promote_draft` endpoints. The actual gap is narrow: (1) two new endpoints (`approve`/`reject`) plus a status-guard change in `install_module()` from `!= VALIDATED` to `!= APPROVED`, (2) extending the SSE payload to surface build-in-progress and pending-approval modules (which today are invisible to the stream — it only reports *loaded* modules, not `VALIDATED`-but-uninstalled ones), (3) a new `pipelinePageMachine` XState v5 machine to formalize state that today lives ad hoc in a Zustand store, and (4) three independent hardening tasks (retention worker, Playwright harness, rate-limit middleware) that have zero existing scaffolding in this repo and need Wave 0 setup.

The most consequential non-obvious finding: **this codebase has two parallel module lifecycles that both need governance, and they are asymmetric.** Path A (chat-driven `build_module()` → `validate_module()` → `install_module()`) tracks lifecycle purely via `ModuleManifest.status` on disk and never records a version row. Path B (`DraftManager` dev-mode edit of an *already-installed* module) tracks lifecycle via `DraftState` in `data/drafts/{id}/metadata.json` and *does* call `VersionManager.record_version()` on promotion. D-01 through D-19 in `08-CONTEXT.md` describe the approval gate in terms that map cleanly onto Path A's `VALIDATED`→`APPROVED` transition (the states already exist for this exact purpose), while D-12's reference-safety rule is more relevant to garbage-collecting Path B's promoted-then-later-rolled-back versions. The plan should build the approve/reject gate against Path A primarily, and treat Path B's existing `promote_draft` (already `admin+`-gated) as an already-compliant secondary path that doesn't need its own approve/reject endpoint — only its GC-on-discard behavior needs strengthening per D-10.

The second consequential finding: **REQ-017's acceptance criterion ("Prometheus retention flags per org") does not match the current infra.** Prometheus (`config/prometheus.yaml`, single instance, no `--storage.tsdb.retention.time` flag set) and Tempo (`config/tempo.yaml`, global `block_retention: 24h`) are both single-tenant OSS deployments with no per-org retention capability without adding Mimir/Cortex or enabling Tempo's `X-Scope-OrgID` multi-tenancy — a materially larger infra lift than this phase's stated scope. The pragmatic, already-supported path is to implement tiered retention against the **application-level org-scoped SQLite tables** that already exist (`usage_records` in `shared/billing/usage_store.py`, indexed on `(org_id, created_at)`) using the exact tier-key convention already established by `QuotaManager.TIER_QUOTAS` (`{"free": 100.0, "team": 5000.0, "enterprise": -1.0}`). This is flagged as `[ASSUMED]` scope reinterpretation in the Assumptions Log — the planner and user should confirm this framing before locking Wave boundaries.

**Primary recommendation:** Build the approval gate as two new `admin+`-gated endpoints (`POST /admin/modules/{module_id}/approve`, `/reject`) that operate on `ModuleManifest.status`, guard `install_module()` on `APPROVED` instead of `VALIDATED`, extend `_build_pipeline_state()` to scan `MODULES_DIR` manifests for `VALIDATED`/`APPROVED` status (not just loaded modules), add a `pipelinePageMachine` XState v5 machine wrapping the existing SSE/Zustand logic, and treat retention + rate-limiting + GC as three independent Wave-0-heavy tracks that each need scaffolding from zero (no existing test/middleware/worker infra to extend).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Module approval gate (approve/reject decision + install guard) | API / Backend | — | `install_module()` attestation guard is the enforcement point (D-16 requires backend enforcement, not UI-only) |
| Pending-approval node + build-stage live state | API / Backend (SSE producer) | Browser / Client (React Flow consumer) | `_build_pipeline_state()` is single source of truth; UI renders only from SSE payload (Phase 6 no-silent-fallback rule) |
| Review panel (blueprint, diff, sandbox report, credentials, repair history) | Browser / Client | API / Backend (data source: `DraftManager.get_diff`, `BuildAuditLog`) | Rendering logic in `NodeDetailPanel`; data already served by existing admin endpoints |
| Chat approval (conversational approve/reject + blueprint) | API / Backend (orchestrator tool + RBAC) | Browser / Client (ActionCard rendering) | Same RBAC path as UI approval (D-17); tool dispatch lives in `ModuleAdminTool` |
| Generic module UI surface (D-07) | Browser / Client | API / Backend (`AdapterRunResult` envelope) | Renderer is generic; envelope is the only backend contract needed, already exists (Phase 3) |
| LLM walkthrough generation (D-08) | API / Backend | — | Hooked into `validate_module()` / draft validation via `LLMGateway.generate(purpose=CRITIC)`; stored with draft/manifest, not client-generated |
| Artifact GC + reject cleanup (D-10/D-11/D-12) | API / Backend | Database / Storage (SQLite `active_versions` reference check) | Filesystem + SQLite mutation; must run server-side with reference-safety check |
| Tiered trace retention (REQ-017) | Database / Storage (SQLite `usage_records`, future `audit_events`) | API / Backend (cleanup worker) | Per-org tiering is only achievable today at the app-data layer, not the Prometheus/Tempo layer (see Summary) |
| Rate limiting (REQ-020) | API / Backend (middleware on :8001 and :8003) | — | Must intercept before route handlers; keyed by API key header, not `request.state.user` (see Pitfall 3) |
| Pipeline SSE E2E tests (REQ-018) | Browser / Client (Playwright drives real browser) | API / Backend (real dashboard SSE endpoint, no mocking) | Known Playwright limitation with mocked `EventSource` — must test against live services (see Pitfall 4) |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-014 | Module approval gates — UI review of generated code + required credentials + sandbox test results; approve/reject with feedback loop | Architecture Patterns (approve/reject endpoint design), Code Examples (install guard change, SSE payload extension), Don't Hand-Roll (reuse `DraftManager`/`BuildAuditLog`) |
| REQ-017 | Tiered trace retention (Free 7d / Team 90d / Enterprise unlimited); Prometheus retention flags per org; background cleanup worker prunes expired data daily | Summary (infra vs. app-layer reinterpretation), Assumptions Log (A1), Code Examples (retention worker against `usage_records`), Common Pitfalls (Pitfall 2) |
| REQ-018 | E2E tests for Pipeline SSE reconnection — Playwright verifies initial connect, reconnect after dashboard restart, error handling on SSE failure | Environment Availability (no Playwright infra exists), Validation Architecture (Wave 0 gaps), Common Pitfalls (Pitfall 4) |
| REQ-020 | Rate limiting on all HTTP endpoints — token bucket, 429 + Retry-After, configurable per-endpoint | Don't Hand-Roll (reuse `shared/utils/rate_limiter.py`), Code Examples (middleware pattern), Common Pitfalls (Pitfall 3) |

</phase_requirements>

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Approval Surface & Placement**
- D-01: Review lives on the Pipeline page. A module reaching `VALIDATED` surfaces as a pending-approval node in the React Flow graph; clicking opens the review inside the existing `NodeDetailPanel` (extended). No separate approvals page.
- D-02: Chat approval is enabled. The chat agent can present a module ready for approval and accept approve/reject conversationally, with optional inputs (e.g., feedback text, config values) and interactive drawn blueprints rendered in chat — extends the Phase 6 ActionCard structured-action pattern.
- D-03: Pipeline SSE (2s stream) is the transport for pending-approval and build state on the pipeline page. Not the 30s CapabilityEnvelope poll.
- D-04: The graph is the notification. On `VALIDATED`, the module is injected into the available-services graph as a node carrying a pending-approval badge. No toast/nav-badge dependency.

**Review Content Depth & Module HMI**
- D-05: Progressive blueprint (both layers). A designed "blueprint card" summary (technical-drawing aesthetic) that expands into an interactive React Flow mini-graph of the module structure: adapter → schema → outputs → required credentials as nodes.
- D-06: All five review layers, each a collapsible dropdown section: (1) blueprint visual, (2) code diff viewer, (3) sandbox validation report, (4) requested credentials list, (5) repair-history timeline from `BuildAuditLog`.
- D-07: Every installed module gets a standard, auto-generated UI surface — a simple panel rendering its data/charts from the canonical `AdapterRunResult` envelope. Generic renderer; modules do not hand-build UI.
- D-08: LLM-generated plain-language walkthrough of what the module code does — generated once at validation time, stored with the draft, displayed in the review panel (instructional review per PROJECT.md developer-mode vision).

**Rejection & Artifact Cleanup (user-flagged as essential: artifact memory management)**
- D-09: Reject-with-feedback triggers one bounded repair cycle — feedback flows into `gateway.generate(purpose=REPAIR)` as repair hints, then the module returns to pending approval. Reject-without-feedback is terminal.
- D-10: Terminal rejection purges heavyweight artifacts. Draft directory, artifact bundles, and overlay/version directories are deleted. Lightweight append-only audit records (JSONL) are preserved for the audit trail.
- D-11: One background GC/reaper worker sweeps orphaned and rejected artifacts on a schedule — shared with the REQ-017 trace-retention cleanup worker (one scheduled worker, two policies: trace expiry + artifact GC).
- D-12: Reference-safety rule: GC must never delete artifacts referenced by `active_versions` rollback pointers. Reference check before every delete.

**Live Build Visual Coherence**
- D-13: Build stages (scaffold → implement → tests → repair) render as live StageNode progression on the pipeline graph, driven by SSE, using the same status colors, error taxonomy, and design tokens established in Phase 6. Building, validating, pending-approval, approved, rejected are all visually distinct node states.
- D-14: New `pipelinePageMachine` (XState v5) following the financePage/monitoringPage patterns — SSE connection state, node selection, review panel state as machine regions. Framer Motion animates stage/state transitions.
- D-15: Per-attempt timeline in `NodeDetailPanel` sourced from `BuildAuditLog` (attempt records, failure fingerprints, repair outcomes).

**Approval Policy & RBAC**
- D-16: Always-manual approval in this phase. No auto-approve path. Enforced at the install attestation guard level (backend), not just UI.
- D-17: Approve/reject requires admin+ role — consistent with existing validate/promote/rollback RBAC. Chat approval enforces the same RBAC via the session's API key role.
- D-18: Policy config object scaffolded with `auto_approve: false` as a hard default — future relaxation (trusted categories, all-tests-pass auto-approve) becomes a config change, not a schema change.
- D-19: Every approve/reject decision recorded with actor identity, timestamp, and artifact hash in the audit log.

### Claude's Discretion
- Non-UI deliverable implementation details: trace-retention tier mechanics (REQ-017), token-bucket rate limiter implementation and per-endpoint config (REQ-020), Playwright E2E test scope for SSE reconnection (REQ-018)
- Blueprint card visual design, layout algorithm for the module structure mini-graph
- GC worker schedule and batch sizes
- Walkthrough generation prompt design and storage format
- Generic module panel layout and chart-type inference from `AdapterRunResult`
- Whether chat blueprint rendering reuses the React Flow mini-graph component or a lighter SVG variant

### Deferred Ideas (OUT OF SCOPE)
- Module versioning/rollback UI beyond what approval requires — Phase 9 (REQ-015)
- Marketplace publishing & browsing UI — Phase 9 (REQ-025/026)
- Auto-approve policies (trusted categories, test-based) — config scaffold ships now (D-18), activation deferred
- Multi-approver / approval-chain workflows — enterprise territory, Phase 9
</user_constraints>

## Standard Stack

### Core (already in repo — no new backend packages required)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.6 [VERIFIED: orchestrator/requirements.txt] | Admin API (:8003) + Dashboard API (:8001) hosts | Already the framework for both target services |
| `shared/utils/rate_limiter.py` (`TokenBucketRateLimiter`, `RateLimiterRegistry`) | in-repo | Token bucket primitive for REQ-020 | Already implements async + sync `acquire()`, `retry_after()`, Prometheus-ready; currently used only for outbound provider calls — reusable as-is for inbound HTTP rate limiting |
| `shared.auth.middleware.APIKeyAuthMiddleware` pattern (`BaseHTTPMiddleware`) | in-repo | Template for new `RateLimitMiddleware` | Both target services already wire this exact middleware shape; a new middleware following the same constructor/dispatch shape slots in with zero new concepts |
| XState v5 | 5.28.0 [VERIFIED: ui_service/package.json] | `pipelinePageMachine` (D-14) | Matches `financePageMachine`/`monitoringPageMachine` precedent exactly |
| `@xyflow/react` (React Flow v12) | 12.10.0 [VERIFIED: ui_service/package.json] | Pending-approval nodes, blueprint mini-graph (D-05) | Already the pipeline page's rendering engine |
| Framer Motion | 11.18.2 [VERIFIED: ui_service/package.json] | State-transition animation (D-13) | Already used in `NodeDetailPanel`, `ActionCard`, `StageNode` |
| Zustand | 5.0.11 [VERIFIED: ui_service/package.json] | Current pipeline SSE store (`nexusStore.ts`) — migrate/wrap, don't discard | D-14 asks for an XState machine layer; the existing SSE `EventSource` wiring in Zustand can remain the transport and be driven into the new machine rather than rewritten |

### Supporting (new for this phase)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@playwright/test` | 1.61.1 [VERIFIED: npm registry, 2026-07-12] | REQ-018 E2E harness | No test framework exists in `ui_service/` today (no jest/vitest/playwright in `package.json`) — full Wave 0 setup required |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-memory `TokenBucketRateLimiter` (per-process) | `slowapi` (Redis or in-memory) | `slowapi` gives per-endpoint decorator syntax out of the box, but adds a new dependency for something the repo already implements; no Redis service exists in `docker-compose.yaml` today, so a Redis-backed limiter would also require new infra. Recommend reusing the in-repo primitive — flagged as Claude's Discretion in CONTEXT.md, not a locked decision. |
| App-level org-scoped SQLite retention (`usage_records`) | Tempo multi-tenancy (`X-Scope-OrgID` + `overrides.yaml`) + Mimir/Cortex for Prometheus | True per-org retention at the observability-backend layer is the "correct" enterprise answer but requires: (1) every OTel-emitting service to propagate an org header, (2) a new `overrides.yaml` where Tempo docs explicitly warn "omitting a field can lead to unexpected behavior, such as a 0s retention" [CITED: grafana.com/docs/tempo/latest/operations/manage-advanced-systems/multitenancy/], (3) Mimir/Cortex for Prometheus (no native per-tenant retention in vanilla Prometheus). This is Phase 9 "Enterprise" scale, not Phase 8. |
| Playwright against real docker-compose services | Playwright with mocked `EventSource` via `page.route()` | Community reports indicate Playwright's request interception does not reliably deliver events to mocked `EventSource` connections, causing tests to hang [CITED: web search, GitHub issue reports on EventSource+Playwright]. Testing against a real running dashboard service (matches existing `make test-monkey` "requires services up" precedent) avoids this entirely. |

**Installation:**
```bash
# Backend: no new packages (reuse shared/utils/rate_limiter.py, stdlib for GC/retention worker)

# Frontend (ui_service/):
npm install --save-dev @playwright/test
npx playwright install --with-deps chromium   # at minimum; add firefox/webkit only if cross-browser is in scope
```

**Version verification:** `npm view @playwright/test version` → `1.61.1` confirmed live against the npm registry on 2026-07-12; official repo `github.com/microsoft/playwright`, ~45M weekly downloads. No Python packages require verification — this phase adds zero new PyPI dependencies.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `@playwright/test` | npm | Years (Microsoft-maintained) | ~45.2M/week | github.com/microsoft/playwright | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

slopcheck 0.6.1 was installed and run successfully this session (`pip install slopcheck`, then `slopcheck install @playwright/test --ecosystem npm`) — verdict `[OK]`. No Python packages are being added by this phase, so no `pip`/PyPI audit rows apply.

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────┐
                         │  Chat (orchestrator)                     │
                         │  ModuleAdminTool.approve/reject (new)    │
                         │  RBAC: admin+ via session API key role   │
                         └──────────────┬────────────────────────────┘
                                        │ same code path as UI
                                        ▼
┌──────────────────┐   POST /admin/modules/{id}/approve   ┌────────────────────────────┐
│  Pipeline UI      │──────────────────────────────────────▶│ orchestrator/admin_api.py │
│  (React Flow +    │   POST /admin/modules/{id}/reject     │  (:8003, admin+)          │
│   pipelinePageMachine)│◀─────────────────────────────────│  new endpoints            │
└─────────┬─────────┘        RBAC 403 if < admin            └──────────┬─────────────────┘
          │ EventSource                                                 │ manifest.status
          │ /stream/pipeline-state (2s)                                 │ VALIDATED → APPROVED
          ▼                                                             │      or → terminal/repair
┌────────────────────────────┐   scans MODULES_DIR manifests   ┌───────▼─────────────────┐
│ dashboard_service/         │◀─────────────────────────────────│ ModuleManifest (disk)   │
│ pipeline_stream.py         │   (extended: PENDING/VALIDATING/ │ shared/modules/         │
│ _build_pipeline_state()    │    VALIDATED/APPROVED/INSTALLED) │ manifest.py              │
└──────────┬──────────────────┘                                └──────────────────────────┘
           │ SSE payload: modules[] gains
           │ {status, pending_approval, build_stage}
           ▼
┌────────────────────────────┐
│ NodeDetailPanel (extended)  │  reads on-demand from:
│  5 collapsible sections     │──▶ GET /admin/modules/drafts/{id}/diff      (code diff)
│  (D-06)                     │──▶ sandbox validation report (from manifest.validation_results)
│                              │──▶ GET credentials list (module manifest)
│                              │──▶ BuildAuditLog attempts (D-15, new read endpoint)
└──────────────────────────────┘

Reject flow:
  reject(no feedback) ──▶ install_module() never called ──▶ GC worker deletes
                            MODULES_DIR/{cat}/{plat}/ (D-10), keeps JSONL audit trail
  reject(with feedback) ──▶ repair_module() bounded cycle (existing MAX_REPAIR_ATTEMPTS=10)
                            ──▶ back to VALIDATED ──▶ pending-approval again (D-09)

Shared background worker (new, D-11):
  asyncio while-True loop (same shape as pipeline_event_generator)
  ├─ Policy 1: artifact GC — sweep rejected/orphaned module dirs + draft workspaces,
  │            cross-check against VersionManager.active_versions before delete (D-12)
  └─ Policy 2: trace/usage retention — DELETE FROM usage_records WHERE org_id=? AND
               created_at < tier_cutoff(org.plan)  [tier map mirrors QuotaManager.TIER_QUOTAS]
```

### Recommended Project Structure
```
orchestrator/
├── admin_api.py                    # add approve/reject endpoints (extend, don't rewrite)
├── retention_worker.py             # NEW — shared GC + trace retention scheduled task
shared/
├── modules/
│   ├── manifest.py                 # no schema change — APPROVED already exists
│   ├── audit.py                    # no change — BuildAuditLog already append-only JSONL
│   └── policy.py                   # NEW — ApprovalPolicy Pydantic model (D-18 scaffold)
├── auth/
│   └── rate_limit_middleware.py    # NEW — BaseHTTPMiddleware, mirrors middleware.py shape
├── billing/
│   └── usage_store.py              # extend — add prune_older_than(org_id, cutoff) method
tools/builtin/
├── module_admin.py                 # add ApproveStrategy, RejectStrategy (action_name="approve"/"reject")
dashboard_service/
├── pipeline_stream.py              # extend _build_pipeline_state(): scan manifests, not just loaded modules
ui_service/src/
├── machines/
│   └── pipelinePageMachine.ts      # NEW — SSE region, selection region, review-panel region
├── components/pipeline/
│   ├── NodeDetailPanel.tsx         # extend with 5 collapsible sections (D-06)
│   └── BlueprintCard.tsx           # NEW — progressive disclosure card → mini React Flow graph (D-05)
├── components/chat/
│   └── ApprovalActionCard.tsx      # NEW — extends ActionCard.tsx pattern for approve/reject + blueprint
tests/
├── e2e/                            # NEW — Playwright root (does not exist)
│   ├── pipeline-sse-reconnect.spec.ts
│   └── playwright.config.ts
├── integration/
│   ├── admin/test_approval_gate.py      # NEW
│   └── admin/test_rate_limit_429.py     # NEW (distinct from existing tests/feature/test_rate_limit_429.py — see Pitfall 1)
├── unit/
│   └── test_retention_worker.py         # NEW
```

### Pattern 1: Status-guard change, not a new state machine
**What:** `ModuleStatus.APPROVED` already exists in the enum (`shared/modules/manifest.py:21`). The only backend change required is `tools/builtin/module_installer.py`'s pre-install check, currently `if manifest.status != ModuleStatus.VALIDATED and manifest.status != ModuleStatus.VALIDATED.value:` — change the compared value to `ModuleStatus.APPROVED`.
**When to use:** This is the enforcement point for D-16 ("Enforced at the install attestation guard level (backend), not just UI").
**Example:**
```python
# Source: tools/builtin/module_installer.py (existing, lines ~99-108) — modify in place
if manifest.status != ModuleStatus.APPROVED and manifest.status != ModuleStatus.APPROVED.value:
    _log_install_rejection(
        module_id, "not_approved", f"Status: {manifest.status}"
    )
    return {
        "status": "error",
        "error": (
            f"Module {module_id} has not been approved for install (status: {manifest.status}). "
            f"An admin must call approve_module('{module_id}') first."
        ),
    }
```

### Pattern 2: New approve/reject endpoints follow the existing draft-endpoint RBAC shape exactly
**What:** `orchestrator/admin_api.py` already has 7 module-lifecycle endpoints gated by `Depends(require_permission(Permission.ADMIN_ALL))` (validate_draft, promote_draft, rollback_module). New approve/reject endpoints are structurally identical.
**When to use:** Any new admin+ mutation on module lifecycle.
**Example:**
```python
# Source: orchestrator/admin_api.py — new endpoints, modeled on existing promote_draft (line 1481)
class RejectModuleRequest(BaseModel):
    feedback: Optional[str] = None  # None = terminal rejection (D-09)

@_app.post("/admin/modules/{module_id}/approve")
def approve_module(
    module_id: str,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),  # D-17
):
    """Approve a VALIDATED module for install. RBAC: admin+ role required."""
    manifest = _load_manifest_or_404(module_id)
    if manifest.status != ModuleStatus.VALIDATED:
        raise HTTPException(400, f"Module must be VALIDATED to approve, got: {manifest.status}")
    manifest.status = ModuleStatus.APPROVED
    manifest.save(MODULES_DIR)
    _dev_mode_audit_log.log_action(  # D-19: actor + timestamp + hash
        action="module_approved", actor=user.org_id, module_id=module_id,
        details={"bundle_sha256": _current_bundle_hash(module_id)},
    )
    return {"status": "success", "module_id": module_id, "new_status": "approved"}


@_app.post("/admin/modules/{module_id}/reject")
def reject_module(
    module_id: str,
    request: RejectModuleRequest,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),
):
    """Reject a VALIDATED module. With feedback: bounded repair (D-09). Without: terminal + GC (D-10)."""
    manifest = _load_manifest_or_404(module_id)
    _dev_mode_audit_log.log_action(
        action="module_rejected", actor=user.org_id, module_id=module_id,
        details={"feedback": request.feedback, "terminal": request.feedback is None},
    )
    if request.feedback:
        from tools.builtin.module_builder import repair_module
        # ... load audit_log for module_id, call repair_module with synthetic
        # validation_report constructed from request.feedback, module returns to VALIDATED
        manifest.status = ModuleStatus.VALIDATING
    else:
        manifest.status = ModuleStatus.FAILED
        _queue_for_gc(module_id)  # D-10/D-11: heavyweight artifact purge, JSONL preserved
    manifest.save(MODULES_DIR)
    return {"status": "success", "module_id": module_id, "new_status": manifest.status}
```

### Pattern 3: SSE payload extension — scan manifests, don't rely on `ModuleLoader.list_modules()`
**What:** `_build_pipeline_state()` currently sources `modules` exclusively from `loader.list_modules()`, which only knows about *loaded* modules. A module sitting in `VALIDATED` state has never been loaded, so it is invisible to today's SSE stream — this is the actual gap behind D-01/D-04, not a UI-only problem.
**When to use:** Any time the pipeline graph needs to show a module that hasn't been installed yet.
**Example:**
```python
# Source: dashboard_service/pipeline_stream.py — extend _build_pipeline_state()
from shared.modules.manifest import ModuleManifest, ModuleStatus

def _build_pending_approval_list(modules_dir: Path) -> list[dict]:
    """Scan MODULES_DIR for manifests not yet loaded (VALIDATED/APPROVED/VALIDATING)."""
    pending = []
    for manifest in ModuleManifest.discover(modules_dir):
        if manifest.status in (ModuleStatus.VALIDATED, ModuleStatus.APPROVED, ModuleStatus.VALIDATING):
            pending.append({
                "id": manifest.module_id,
                "name": manifest.display_name,
                "status": manifest.status,
                "pending_approval": manifest.status == ModuleStatus.VALIDATED,
                "build_stage": manifest.status,  # coarse; refine with BuildSession tracking if needed
            })
    return pending

# In _build_pipeline_state():
# modules = [...existing loaded modules...] + _build_pending_approval_list(MODULES_DIR)
```

### Pattern 4: `pipelinePageMachine` wraps the existing SSE `EventSource`, doesn't replace it
**What:** `connectPipelineSSE()` in `ui_service/src/lib/adminClient.ts` already returns a raw `EventSource` with `onmessage`/`onerror` callbacks; `nexusStore.ts` (Zustand) already wires it. D-14 asks for an XState machine with SSE connection state as one region — model this as a `fromCallback` actor invoking the existing `connectPipelineSSE()`, mirroring how `monitoringPageMachine` uses `fromPromise` actors for its polling regions.
**When to use:** New page-level state machine for the pipeline page.
**Example:**
```typescript
// Source: pattern derived from ui_service/src/machines/monitoringPage.ts (parallel regions)
// + ui_service/src/lib/adminClient.ts connectPipelineSSE (existing, unmodified)
import { setup, fromCallback } from 'xstate';
import { connectPipelineSSE, type PipelineState } from '../lib/adminClient';

export const pipelinePageMachine = setup({
  types: {
    context: {} as { pipeline: PipelineState | null; selectedNodeId: string | null },
    events: {} as
      | { type: 'SSE_MESSAGE'; data: PipelineState }
      | { type: 'SSE_ERROR' }
      | { type: 'SELECT_NODE'; id: string }
      | { type: 'CLOSE_PANEL' },
  },
  actors: {
    sseConnection: fromCallback(({ sendBack }) => {
      const es = connectPipelineSSE(
        (state) => sendBack({ type: 'SSE_MESSAGE', data: state }),
        () => sendBack({ type: 'SSE_ERROR' }),
      );
      return () => es.close();  // cleanup on region exit
    }),
  },
}).createMachine({
  id: 'pipelinePage',
  type: 'parallel',
  states: {
    connection: {
      initial: 'connecting',
      states: {
        connecting: { invoke: { src: 'sseConnection' }, on: { SSE_MESSAGE: 'connected' } },
        connected: { on: { SSE_ERROR: 'reconnecting', SSE_MESSAGE: { actions: 'updatePipeline' } } },
        reconnecting: { on: { SSE_MESSAGE: 'connected' } },  // native EventSource auto-retries
      },
    },
    reviewPanel: {
      initial: 'closed',
      states: {
        closed: { on: { SELECT_NODE: 'open' } },
        open: { on: { CLOSE_PANEL: 'closed', SELECT_NODE: 'open' } },
      },
    },
  },
});
```

### Pattern 5: Rate-limit middleware keys on the raw header, not `request.state.user`
**What:** `RateLimitMiddleware` must protect *unauthenticated* endpoints too (`/admin/bootstrap`, `/admin/health`) per REQ-020 ("all HTTP endpoints"). If it's added after `APIKeyAuthMiddleware` in the stack it would run before auth resolves `request.state.user` (Starlette wraps middleware in reverse-add order — last `add_middleware()` call is outermost and runs first). Reading `X-API-Key` directly from headers sidesteps stack-order coupling entirely.
**When to use:** Building the REQ-020 middleware for both `dashboard_service/main.py` and `orchestrator/admin_api.py`.
**Example:**
```python
# Source: pattern modeled on shared/auth/middleware.py APIKeyAuthMiddleware (existing)
from shared.utils.rate_limiter import get_rate_limiter_registry, RateLimitExceeded

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        key = request.headers.get("X-API-Key") or request.client.host  # per-key, fallback per-IP
        limiter = get_rate_limiter_registry().get(f"http:{key}")
        if not await limiter.acquire():
            retry_after = limiter.retry_after()
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after": retry_after},
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        return await call_next(request)
```

### Anti-Patterns to Avoid
- **Don't add a new `ModuleStatus.PENDING_APPROVAL` state.** `VALIDATED` already means exactly this in context (D-01: "A module reaching VALIDATED surfaces as a pending-approval node"). Adding a redundant state fragments the manifest schema for no benefit.
- **Don't route the approval gate through `DraftManager`.** Freshly-built modules (Path A) never become drafts; forcing them through the draft lifecycle to reuse `promote_draft`'s RBAC would require synthesizing a fake draft for every build, adding indirection without benefit. Build parallel `approve`/`reject` endpoints instead (Pattern 2).
- **Don't try to intercept/mock `EventSource` in Playwright.** Test against real running services (Pitfall 4).
- **Don't put per-org retention logic inside Tempo/Prometheus config.** Neither supports it in this deployment's current single-tenant form (see Summary, Alternatives Considered).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token bucket rate limiting | New rate-limit class | `shared/utils/rate_limiter.py` `TokenBucketRateLimiter`/`RateLimiterRegistry` | Already thread-safe, async-capable, has `retry_after()` built in — exactly REQ-020's shape, just needs an HTTP middleware wrapper, not a new algorithm |
| Draft diff/validate/promote lifecycle | New review workflow | `shared/modules/drafts.py` `DraftManager` | Fully implemented, tested (Phase 3 Plan 06), RBAC-wired |
| Per-attempt repair audit trail | New audit table | `shared/modules/audit.py` `BuildAuditLog`/`AttemptRecord`/`FailureFingerprint` | D-15 explicitly says "sourced from BuildAuditLog" — it already has `attempt_number`, `failure_fingerprint`, `failure_type`, timestamps |
| Content-addressed artifact identity for GC reference checks | New hash tracking | `shared/modules/artifacts.py` `ArtifactBundleBuilder`, `shared/modules/versioning.py` `VersionManager.list_versions()`/`get_active_version()` | D-12's reference-safety check is a direct `bundle_sha256` lookup against `active_versions` — the query surface already exists |
| Org tier resolution for retention policy | New tier config | `shared/billing/quota_manager.py` `QuotaManager._resolve_plan()` + `TIER_QUOTAS` dict pattern | Establishes the exact `{"free": ..., "team": ..., "enterprise": -1}` convention (unlimited = `-1` sentinel) — mirror this shape for `TIER_RETENTION_DAYS` |
| Chat structured-action approve/reject UI | New chat card component | `ui_service/src/components/chat/ActionCard.tsx` | Already implements pending/executing/completed/failed states with Framer Motion; D-02 explicitly says "extends the Phase 6 ActionCard structured-action pattern" |

**Key insight:** This phase is >80% wiring against existing primitives. The risk is not missing functionality — it's building a parallel implementation next to code that already does the job (e.g., a second draft manager, a second audit log format, a second rate limiter class).

## Common Pitfalls

### Pitfall 1: Two files will be named `test_rate_limit_429.py` if you're not careful
**What goes wrong:** `tests/feature/test_rate_limit_429.py` already exists and tests **outbound** 429 handling (NEXUS calling external provider APIs and backing off) — fully mocked with `unittest.mock`, no real server involved. REQ-020 needs **inbound** 429 tests (our own dashboard/admin endpoints returning 429 to callers) which is a different concern entirely.
**Why it happens:** Naming collision on "rate limit" + "429" makes it easy to assume test coverage exists when it doesn't.
**How to avoid:** Name the new integration test file distinctly (e.g., `tests/integration/admin/test_inbound_rate_limit.py`) and verify it spins up a real `TestClient` hitting real middleware, not mocked `httpx`.
**Warning signs:** Grepping for "rate_limit" and finding a green test suite that never touches `orchestrator/admin_api.py` or `dashboard_service/main.py`.

### Pitfall 2: REQ-017's literal acceptance text doesn't match the deployed observability stack
**What goes wrong:** Building "Prometheus retention flags per org" literally requires Mimir/Cortex (Prometheus has no native per-tenant retention) and Tempo multi-tenancy requires `X-Scope-OrgID` propagated from every trace-emitting service plus a new `overrides.yaml` — Tempo's own docs warn that per-tenant overrides silently zero-out unset fields [CITED: grafana.com/docs/tempo/latest/operations/manage-advanced-systems/multitenancy/]. Attempting this literally would balloon the phase into an infra migration.
**Why it happens:** The requirement text was likely written against an aspirational multi-tenant observability design (`docs/archive/PLAN.md §4`) that predates the current single-instance Prometheus/Tempo deployment actually shipped in `docker-compose.yaml`.
**How to avoid:** Implement tiered retention against org-scoped SQLite tables (`usage_records` today; `audit_events` once Phase 7 ships) as the retention target, using the `QuotaManager.TIER_QUOTAS` naming convention. Document this reinterpretation explicitly in the plan and flag it for user confirmation (see Assumptions Log A1).
**Warning signs:** A plan task that says "configure Tempo overrides.yaml" or "add Mimir" — this is a strong signal the phase scope has silently expanded into Phase 9 territory.

### Pitfall 3: Middleware ordering silently breaks per-org rate limiting
**What goes wrong:** Starlette/FastAPI wrap middleware in *reverse* `add_middleware()` call order — the last one added is outermost and runs first on the request path. If `RateLimitMiddleware` is added after `APIKeyAuthMiddleware` (as both `dashboard_service/main.py` and any new admin wiring would naturally do by appending), it becomes outermost and runs *before* auth resolves `request.state.user` — so keying the limiter off `request.state.user.org_id` will `AttributeError` or silently fall through to an "unauthenticated" bucket for every request, including authenticated ones.
**Why it happens:** It's intuitive to assume middleware added later runs later; Starlette's actual behavior is the opposite.
**How to avoid:** Read the `X-API-Key` header directly in the rate-limit middleware (Pattern 5) instead of depending on `request.state.user`, which sidesteps stack-order dependencies entirely. If per-org limiting (as opposed to per-key) is required, resolve the org via `APIKeyStore.validate_key()` directly inside the rate-limit middleware — don't rely on another middleware having already run.
**Warning signs:** Rate limit tests pass when hitting endpoints directly but the limiter never seems to distinguish between different API keys in integration.

### Pitfall 4: Playwright cannot reliably test mocked `EventSource`/SSE connections
**What goes wrong:** Community reports (GitHub issues, blog posts) describe Playwright's `page.route()` request interception not delivering events to `EventSource` connections, causing SSE-dependent tests to hang indefinitely [CITED: web search results, multiple community reports 2026].
**Why it happens:** `EventSource` uses a streaming `fetch`-like connection that Playwright's interception layer doesn't fully support faking.
**How to avoid:** Test against a **real** running dashboard service (matches this repo's existing `make test-monkey` "requires services up" precedent), not a mocked SSE endpoint. For the "reconnect after dashboard restart" scenario in REQ-018, shell out to `docker compose restart dashboard_service` (or stop/start) from Playwright's `globalSetup`/test body and assert on the UI's existing `connected` state flip (`nexusStore.ts` already sets `connected: false` on `es.onerror` — this behavior exists today and just needs an E2E assertion wrapped around it).
**Warning signs:** A Playwright test that intercepts `**/stream/pipeline-state` with `page.route()` and never resolves.

### Pitfall 5: Freshly-built modules (Path A) have no `active_versions` row to protect — don't over-apply D-12
**What goes wrong:** `install_module()` (the chat-driven build path) never calls `VersionManager.record_version()` — only `DraftManager.promote_draft()` does. If the GC worker's reference-safety check (D-12) is written assuming every module has a version row, it will either no-op incorrectly or throw on `KeyError` for Path A modules.
**Why it happens:** The two module lifecycles (fresh build vs. dev-mode draft edit) look similar in the CONTEXT.md language ("VALIDATED", "reject", "artifacts") but have divergent backend implementations.
**How to avoid:** Write the reference-safety check as "if a version row exists for this bundle_sha256, check `active_versions` before deleting; if no version row exists at all, it's safe to delete unconditionally" — don't assume every rejected module has a version to protect.
**Warning signs:** GC worker code that calls `VersionManager.get_version(version_id)` without a preceding existence check, for artifacts that came from `build_module()` rather than `DraftManager`.

## Code Examples

### Tier-cutoff retention pruning (mirrors `QuotaManager` tier convention)
```python
# Source: pattern modeled on shared/billing/quota_manager.py TIER_QUOTAS (existing)
from datetime import datetime, timedelta, timezone

TIER_RETENTION_DAYS = {
    "free": 7,
    "team": 90,
    "enterprise": -1,  # -1 = unlimited, same sentinel convention as TIER_QUOTAS
}

def prune_expired_usage(usage_store, api_key_store, org_ids: list[str]) -> dict:
    """Daily cleanup pass — one policy of the shared GC worker (D-11)."""
    results = {}
    for org_id in org_ids:
        org = api_key_store.get_organization(org_id)
        plan = org.plan if org else "free"
        retention_days = TIER_RETENTION_DAYS.get(plan, TIER_RETENTION_DAYS["free"])
        if retention_days < 0:
            continue  # enterprise: unlimited, skip
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat() + "Z"
        # usage_records already indexed on (org_id, created_at) — see shared/billing/usage_store.py
        deleted = usage_store.delete_before(org_id=org_id, cutoff=cutoff)  # new method to add
        results[org_id] = deleted
    return results
```

### Shared background worker skeleton (D-11 — mirrors existing SSE loop shape)
```python
# Source: pattern modeled on dashboard_service/pipeline_stream.py pipeline_event_generator (existing)
import asyncio
import logging

logger = logging.getLogger(__name__)

async def gc_and_retention_worker(interval_seconds: int = 86400):
    """One scheduled worker, two policies (D-11). Runs as an asyncio background task
    started at FastAPI startup — same async-while-True shape as the SSE generator,
    no new scheduling library needed (no APScheduler in requirements today)."""
    while True:
        try:
            gc_result = run_artifact_gc()        # D-10/D-12: reject cleanup + orphan sweep
            retention_result = prune_expired_usage(...)  # REQ-017
            logger.info(f"GC/retention pass: {gc_result}, {retention_result}")
        except Exception as e:
            logger.warning(f"GC/retention worker error: {e}")
        await asyncio.sleep(interval_seconds)

# Wire into orchestrator startup (orchestrator_service.py) or dashboard_service/main.py
# via asyncio.create_task(gc_and_retention_worker()) in an @app.on_event("startup") hook.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `install_module()` guards on `VALIDATED` | Guard on `APPROVED` | This phase | Closes the "no module installed without explicit approval" done-criterion at the enforcement layer, not just the UI |
| Pipeline SSE reports only loaded modules | Reports loaded + pending-approval (manifest-scanned) modules | This phase | Makes D-04 ("the graph is the notification") possible — today VALIDATED modules are invisible to the graph entirely |
| Pipeline page state lives in Zustand only | Zustand SSE transport wrapped by `pipelinePageMachine` (XState) | This phase | Brings pipeline page in line with `financePageMachine`/`monitoringPageMachine` precedent (D-14) |
| No inbound HTTP rate limiting anywhere | `TokenBucketRateLimiter` reused as HTTP middleware on :8001 and :8003 | This phase | Closes the "No rate limiting" open risk listed in `.planning/STATE.md` |

**Deprecated/outdated:** None — this phase extends existing patterns rather than replacing anything.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | REQ-017's "Prometheus retention flags per org" is reinterpreted as app-level SQLite retention (`usage_records`, future `audit_events`) rather than literal Prometheus/Tempo multi-tenant infra, because the latter requires Mimir/Cortex/Tempo `X-Scope-OrgID` propagation not present in this deployment | Summary, Pitfall 2, Code Examples | If the user actually wants true observability-backend-layer per-org retention, this phase's scope is significantly larger (new services: Mimir or Cortex; header propagation changes in every OTel-instrumented service) and should likely be re-scoped or deferred to Phase 9. **Flag for discuss-phase / user confirmation before locking Wave boundaries.** |
| A2 | Freshly-built modules (Path A, via `build_module()`) are the primary target of the approval gate; `DraftManager`'s existing `admin+`-gated `promote_draft` is treated as an already-compliant secondary path that doesn't need its own approve/reject endpoint | Summary, Pattern 1-2, Pitfall 5 | If discuss-phase intended the approval gate to also formally intercept the draft-promotion path (not just gate it via existing RBAC), an additional endpoint/UI affordance would be needed for drafts specifically |
| A3 | `Purpose.CRITIC` (defined but unused end-to-end in `shared/providers/llm_gateway.py`) is the correct LLM Gateway lane for D-08's walkthrough generation, rather than adding a new `Purpose.WALKTHROUGH` enum value | Don't Hand-Roll section (implicit), D-08 | Low risk — reusing CRITIC avoids new routing-config plumbing; if wrong, the fix is a one-line enum addition, not a redesign |
| A4 | The GC worker and retention worker run as a single `asyncio` background task started at FastAPI app startup (no new scheduling library), matching the existing SSE `while True` + `asyncio.sleep` precedent, rather than adding APScheduler or a cron-based external trigger | Code Examples, Standard Stack | Low risk — if daily-interval precision or persistence-across-restart scheduling is required, a lightweight "last-run timestamp" check-on-startup should be added; APScheduler would be the fallback if requirements grow |

**If this table is empty:** N/A — see rows above. A1 is the highest-risk assumption and should be surfaced to the user explicitly before planning locks Wave boundaries.

## Open Questions

1. **Does the approval gate need to intercept `DraftManager.promote_draft()` for dev-mode edits, or only fresh `build_module()` output?**
   - What we know: D-01 through D-19's language ("VALIDATED", "reject with feedback", "artifact cleanup") maps cleanly onto `ModuleManifest.status` (Path A). `DraftManager`'s promote flow (Path B) is already `admin+`-gated and separately audited.
   - What's unclear: Whether "no module installed without explicit user approval" (done criterion) is meant to also formally gate draft promotions with the new UI review panel, or whether existing RBAC on `promote_draft` already satisfies that criterion for Path B.
   - Recommendation: Default to Path A as primary (per A2); confirm with user whether Path B needs the same review-panel treatment or can remain as-is.

2. **What is the actual per-org tier source of truth for retention — `Organization.plan` (auth) or a separate billing-tier table?**
   - What we know: `shared/auth/models.py` `Organization.plan` (default `"free"`) is the only tier field found in the codebase; `QuotaManager._resolve_plan()` already reads it via `APIKeyStore.get_organization()`.
   - What's unclear: Whether this field is considered authoritative for retention policy too, or whether a future billing system will introduce a separate plan/tier concept.
   - Recommendation: Reuse `Organization.plan` for retention tiering (matches quota precedent exactly) unless the user indicates a separate billing-tier source is planned.

3. **Should the rate limiter's bucket key be per-API-key or per-org?**
   - What we know: `X-API-Key` header maps 1:1 to an org via `APIKeyStore.validate_key()`, but a single org can have multiple keys (rotation, multiple integrations).
   - What's unclear: Whether REQ-020 intends fairness per credential (each key gets its own bucket) or per tenant (all keys under one org share a bucket, preventing one org's multiple keys from bypassing the limit).
   - Recommendation: Per-key is simpler and matches the existing `RateLimiterRegistry.get(provider)` per-identifier pattern; flag as Claude's Discretion per CONTEXT.md and default to per-key unless told otherwise.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | `ui_service` build, Playwright | ✓ | v26.4.0 | — |
| npm | Playwright install | ✓ | 11.17.0 | — |
| Python 3 | Backend services | ✓ | 3.12.9 | — |
| Docker | `docker compose` full-stack E2E (REQ-018) | ✓ | 29.2.0 | — |
| `@playwright/test` | REQ-018 | ✗ (not in `ui_service/package.json`) | — | Full Wave 0 install required — no fallback, this is a hard new-tooling task |
| Redis | Rate limiting (if Redis-backed limiter were chosen) | ✗ (no Redis service in `docker-compose.yaml`) | — | Use in-repo `TokenBucketRateLimiter` (in-memory, per-process) — no new infra needed |
| Mimir / Cortex | True per-org Prometheus retention | ✗ | — | Use app-level SQLite retention instead (see Assumption A1) |
| Tempo multi-tenancy (`X-Scope-OrgID`) | True per-org trace retention | ✗ (single-tenant config today) | — | Use app-level SQLite retention instead (see Assumption A1) |

**Missing dependencies with no fallback:**
- `@playwright/test` — must be installed fresh; this is expected Wave 0 work for REQ-018, not a blocker, just budget it explicitly.

**Missing dependencies with fallback:**
- Redis, Mimir/Cortex, Tempo multi-tenancy — all have documented in-repo/app-level fallbacks used throughout this research; none block phase execution.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest (existing — `tests/unit`, `tests/integration`, `tests/feature`) |
| Backend config file | `tests/conftest.py` (existing, no changes needed) |
| Frontend framework | **none exists** — Playwright must be installed fresh for REQ-018 |
| Frontend config file | none — see Wave 0 |
| Quick run command (backend) | `cd tests && python -m pytest unit/modules/ integration/admin/ -v --tb=short` |
| Full suite command (backend) | `make verify` (existing unified command, chains 7 test tiers) |
| Quick run command (frontend E2E) | `npx playwright test --project=chromium` (once installed) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-014 | `install_module()` rejects non-APPROVED status | unit | `pytest tests/unit/modules/test_installer_approval_guard.py -x` | ❌ Wave 0 |
| REQ-014 | `approve`/`reject` endpoints enforce admin+ RBAC | integration | `pytest tests/integration/admin/test_approval_gate.py -x` | ❌ Wave 0 |
| REQ-014 | Reject-without-feedback purges module dir, preserves JSONL | integration | `pytest tests/integration/admin/test_reject_gc.py -x` | ❌ Wave 0 |
| REQ-017 | Retention prune deletes rows older than tier cutoff, preserves newer | unit | `pytest tests/unit/test_retention_worker.py -x` | ❌ Wave 0 |
| REQ-017 | GC never deletes artifacts referenced by `active_versions` | unit | `pytest tests/unit/test_gc_reference_safety.py -x` | ❌ Wave 0 |
| REQ-018 | Pipeline SSE initial connect renders live state | e2e | `npx playwright test pipeline-sse-connect.spec.ts` | ❌ Wave 0 |
| REQ-018 | Reconnect after dashboard restart | e2e | `npx playwright test pipeline-sse-reconnect.spec.ts` | ❌ Wave 0 |
| REQ-020 | Inbound requests over limit return 429 + Retry-After | integration | `pytest tests/integration/admin/test_inbound_rate_limit.py -x` | ❌ Wave 0 (distinct from existing outbound-focused `tests/feature/test_rate_limit_429.py` — see Pitfall 1) |

### Sampling Rate
- **Per task commit:** relevant quick-run command above for the deliverable being touched
- **Per wave merge:** `make verify` (backend) + `npx playwright test` (frontend, once installed)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `ui_service/playwright.config.ts` + `ui_service/package.json` devDependency + `tests/e2e/` directory — none exist today
- [ ] `tests/unit/modules/test_installer_approval_guard.py` — covers REQ-014 status guard
- [ ] `tests/integration/admin/test_approval_gate.py` — covers REQ-014 approve/reject RBAC
- [ ] `tests/unit/test_retention_worker.py` + `tests/unit/test_gc_reference_safety.py` — covers REQ-017
- [ ] `tests/integration/admin/test_inbound_rate_limit.py` — covers REQ-020 (name deliberately distinct from existing `tests/feature/test_rate_limit_429.py`)
- [ ] Framework install: `npm install --save-dev @playwright/test && npx playwright install --with-deps chromium`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (indirect) | Existing `APIKeyAuthMiddleware` — no change needed, new endpoints sit behind it |
| V3 Session Management | no | N/A — API-key model, no session state introduced by this phase |
| V4 Access Control | yes | `require_permission(Permission.ADMIN_ALL)` on approve/reject endpoints (D-17); same RBAC dependency injection pattern already used for `validate_draft`/`promote_draft`/`rollback_module` |
| V5 Input Validation | yes | Pydantic request models for new endpoints (`RejectModuleRequest` etc.), following existing `DraftCreateRequest`/`RollbackRequest` pattern |
| V6 Cryptography | no | No new cryptographic primitives introduced (Fernet credential store, SHA-256 artifact hashing already exist and are unmodified) |
| V13 API and Web Service | yes | Rate limiting (REQ-020) is itself a V13-adjacent control (resource-consumption limiting) — this phase net-improves this category |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Module install bypass (agent installs unreviewed code) | Elevation of Privilege | Install attestation guard now requires `APPROVED` status (Pattern 1) — this IS the mitigation this phase delivers |
| Artifact hash tampering between validation and install | Tampering | Already mitigated by existing `bundle_sha256` verification in `install_module()` — unchanged by this phase, just gated one status later |
| HTTP endpoint flooding / brute-force on `/admin/bootstrap` | Denial of Service | New `RateLimitMiddleware` (REQ-020), keyed per-IP for unauthenticated paths, per-key for authenticated ones (Pattern 5) |
| Rejected module artifacts leaking sensitive generated code after "deletion" | Information Disclosure | D-10's JSONL audit preservation is intentional (compliance trail) but must **not** include raw source code in the audit log entry — only hashes/metadata, per existing `AttemptRecord` shape which already stores `bundle_sha256` not raw file content |
| GC race condition: worker deletes an artifact mid-install | Tampering / DoS | D-12's reference-safety check must run inside the same transaction/lock window as the delete — recommend the GC worker checks `active_versions` immediately before each `shutil.rmtree()` call, not in a batch pre-check that could go stale |

## Sources

### Primary (HIGH confidence — read directly from this codebase)
- `.planning/phases/08-co-evolution-approval/08-CONTEXT.md` — locked decisions D-01 through D-19
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` — requirement text, phase ordering, current risk register
- `shared/modules/manifest.py`, `drafts.py`, `audit.py`, `artifacts.py`, `versioning.py` — full read
- `tools/builtin/module_builder.py`, `module_validator.py` (partial), `module_installer.py`, `module_pipeline.py`, `module_admin.py` (partial) — full/partial read
- `orchestrator/admin_api.py` (headers + full draft/version endpoint block), `orchestrator/capability_map.py`, `shared/auth/rbac.py`, `models.py`, `middleware.py` — full read
- `dashboard_service/pipeline_stream.py` — full read
- `shared/utils/rate_limiter.py` — full read
- `shared/billing/usage_store.py`, `quota_manager.py` — partial read (schema + tier logic)
- `shared/contracts/ui_capability_schema.py` — partial read
- `ui_service/src/app/pipeline/page.tsx`, `components/pipeline/NodeDetailPanel.tsx`, `StageNode.tsx`, `components/chat/ActionCard.tsx`, `store/nexusStore.ts`, `machines/monitoringPage.ts`, `lib/adminClient.ts` (partial), `lib/errors.ts`, `package.json` — full/partial read
- `config/tempo.yaml`, `config/prometheus.yaml`, `docker-compose.yaml` (service/port list) — full/partial read
- `Makefile` (test target block) — partial read
- npm registry (`npm view @playwright/test version`, npmjs.org downloads API) — live query, 2026-07-12
- slopcheck 0.6.1 (installed and run this session) — `[OK]` verdict for `@playwright/test`

### Secondary (MEDIUM confidence — WebSearch, cross-checked)
- Grafana Tempo multi-tenancy documentation (`grafana.com/docs/tempo/latest/operations/manage-advanced-systems/multitenancy/`) — per-tenant retention override behavior and the "zero-value on unset field" warning
- FastAPI rate-limiting best-practice search results — 429 + `Retry-After` (seconds, not date) convention, middleware-before-business-logic placement recommendation

### Tertiary (LOW confidence — single-source or community reports, flagged for validation)
- Playwright + `EventSource` interception limitation — based on community/GitHub issue reports found via WebSearch, not verified against official Playwright documentation directly (Context7 unavailable this session). Recommend the planner treat "test against real services" as the safe default rather than attempting to verify the mocking limitation further.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions read directly from `package.json`/`requirements.txt` or verified live against npm registry
- Architecture: HIGH — every pattern in this document is grounded in code actually read from the repository, not inferred
- Pitfalls 1, 3, 5: HIGH — derived directly from reading the actual middleware/installer/versioning code
- Pitfall 2 (REQ-017 infra mismatch): MEDIUM — the Tempo/Prometheus config facts are HIGH confidence (read directly), but the recommended reinterpretation is a judgment call flagged in Assumptions Log A1
- Pitfall 4 (Playwright + EventSource): MEDIUM — based on WebSearch community reports, not official Playwright docs (Context7 unavailable)

**Research date:** 2026-07-12
**Valid until:** ~30 days for backend architecture findings (stable, internal codebase); ~14 days for the Playwright/EventSource compatibility claim specifically, since this is version-sensitive browser/tooling behavior that could change with a Playwright minor release
