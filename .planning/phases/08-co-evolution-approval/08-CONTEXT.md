# Phase 8: Co-Evolution & Approval - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

The safety-gate and human-machine-interface layer for the self-evolution engine. Users review, approve, reject, and steer what the module builder produces — through a visually coherent pipeline UI and through chat. Supporting hardening ships alongside: tiered trace retention with a background cleanup worker, Pipeline SSE E2E tests (Playwright), and rate limiting on all HTTP endpoints.

**Done criteria (from ROADMAP.md):**
- No module installed without explicit user approval
- Traces auto-purge per retention policy

Deliverables: Module approval gates UI (REQ-014), tiered trace retention (REQ-017), Pipeline SSE E2E tests (REQ-018), rate limiting (REQ-020).

</domain>

<decisions>
## Implementation Decisions

### Approval Surface & Placement
- **D-01: Review lives on the Pipeline page.** A module reaching `VALIDATED` surfaces as a pending-approval node in the React Flow graph; clicking opens the review inside the existing `NodeDetailPanel` (extended). No separate approvals page.
- **D-02: Chat approval is enabled.** The chat agent can present a module ready for approval and accept approve/reject conversationally, with **optional inputs** (e.g., feedback text, config values) and **interactive drawn blueprints** rendered in chat — extends the Phase 6 ActionCard structured-action pattern.
- **D-03: Pipeline SSE (2s stream) is the transport** for pending-approval and build state on the pipeline page. Not the 30s CapabilityEnvelope poll.
- **D-04: The graph is the notification.** On `VALIDATED`, the module is injected into the available-services graph as a node carrying a pending-approval badge. No toast/nav-badge dependency.

### Review Content Depth & Module HMI
- **D-05: Progressive blueprint (both layers).** A designed "blueprint card" summary (technical-drawing aesthetic) that expands into an interactive React Flow mini-graph of the module structure: adapter → schema → outputs → required credentials as nodes.
- **D-06: All five review layers, each a collapsible dropdown section:** (1) blueprint visual, (2) code diff viewer, (3) sandbox validation report, (4) requested credentials list, (5) repair-history timeline from `BuildAuditLog`.
- **D-07: Every installed module gets a standard, auto-generated UI surface** — a simple panel rendering its data/charts from the canonical `AdapterRunResult` envelope. Generic renderer; modules do not hand-build UI.
- **D-08: LLM-generated plain-language walkthrough** of what the module code does — generated **once at validation time**, stored with the draft, displayed in the review panel (instructional review per PROJECT.md developer-mode vision).

### Rejection & Artifact Cleanup (user-flagged as essential: artifact memory management)
- **D-09: Reject-with-feedback triggers one bounded repair cycle** — feedback flows into `gateway.generate(purpose=REPAIR)` as repair hints, then the module returns to pending approval. Reject-without-feedback is terminal.
- **D-10: Terminal rejection purges heavyweight artifacts.** Draft directory, artifact bundles, and overlay/version directories are deleted. Lightweight append-only audit records (JSONL) are preserved for the audit trail.
- **D-11: One background GC/reaper worker** sweeps orphaned and rejected artifacts on a schedule — shared with the REQ-017 trace-retention cleanup worker (one scheduled worker, two policies: trace expiry + artifact GC).
- **D-12: Reference-safety rule:** GC must never delete artifacts referenced by `active_versions` rollback pointers. Reference check before every delete.

### Live Build Visual Coherence
- **D-13: Build stages (scaffold → implement → tests → repair) render as live StageNode progression** on the pipeline graph, driven by SSE, using the same status colors, error taxonomy, and design tokens established in Phase 6. Building, validating, pending-approval, approved, rejected are all visually distinct node states.
- **D-14: New `pipelinePageMachine` (XState v5)** following the financePage/monitoringPage patterns — SSE connection state, node selection, review panel state as machine regions. Framer Motion animates stage/state transitions.
- **D-15: Per-attempt timeline** in `NodeDetailPanel` sourced from `BuildAuditLog` (attempt records, failure fingerprints, repair outcomes).

### Approval Policy & RBAC
- **D-16: Always-manual approval in this phase.** No auto-approve path. Enforced at the install attestation guard level (backend), not just UI.
- **D-17: Approve/reject requires admin+ role** — consistent with existing validate/promote/rollback RBAC. Chat approval enforces the same RBAC via the session's API key role.
- **D-18: Policy config object scaffolded** with `auto_approve: false` as a hard default — future relaxation (trusted categories, all-tests-pass auto-approve) becomes a config change, not a schema change.
- **D-19: Every approve/reject decision recorded** with actor identity, timestamp, and artifact hash in the audit log.

### Claude's Discretion
- Non-UI deliverable implementation details: trace-retention tier mechanics (REQ-017), token-bucket rate limiter implementation and per-endpoint config (REQ-020), Playwright E2E test scope for SSE reconnection (REQ-018)
- Blueprint card visual design, layout algorithm for the module structure mini-graph
- GC worker schedule and batch sizes
- Walkthrough generation prompt design and storage format
- Generic module panel layout and chart-type inference from `AdapterRunResult`
- Whether chat blueprint rendering reuses the React Flow mini-graph component or a lighter SVG variant

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & roadmap
- `.planning/ROADMAP.md` — Phase 8 section: deliverables REQ-014/017/018/020, done criteria
- `.planning/REQUIREMENTS.md` — REQ-014 (approval gates), REQ-017 (trace retention), REQ-018 (SSE E2E), REQ-020 (rate limiting) acceptance criteria

### Prior phase decisions that bind this phase
- `.planning/phases/06-ux-visual-expansion/06-CONTEXT.md` — locked UI stack (XState v5, React Flow v12, Recharts, Framer Motion), capability-driven rendering, error taxonomy, no-silent-fallback rules, same-origin BFF mandate
- `.planning/phases/05-refactoring/05-CONTEXT.md` — BaseTool/CompositeTool architecture, ModuleAdminTool/ModulePipelineTool consolidation, no-mock-data rule

### Research anchors
- `.planning/research/Agentic Builder-Tester Pattern for NEXUS.md` — §5 agent monitoring dashboards, §9 monitor agent fidelity validation
- `.planning/research/NEXUS Visualization Toolkit Architecture.md` — visualization library roles and constraints
- `.planning/research/Event-Driven Microservice Orchestration Principles.md` — T4 retry with jitter, outbox pattern for immutable artifacts

### Backend contracts this phase builds on
- `shared/modules/manifest.py` — `ModuleStatus` lifecycle (`VALIDATED` → `APPROVED` states already exist)
- `shared/modules/drafts.py` — `DraftManager` (create/edit/diff/validate/promote/discard)
- `shared/modules/audit.py` — `BuildAuditLog`, `AttemptRecord`, `FailureFingerprint`
- `shared/modules/artifacts.py` — SHA-256 artifact bundling
- `shared/modules/versioning.py` — `active_versions` pointer semantics (GC reference-safety)
- `dashboard_service/pipeline_stream.py` — SSE stream shape (`/stream/pipeline-state`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DraftManager` / `VersionManager` — the entire draft → validate → promote lifecycle exists; approval UI is a front-end over these plus a new explicit approve/reject endpoint pair
- `ModuleStatus.VALIDATED` / `APPROVED` — lifecycle states already defined in manifest.py; wiring, not schema work
- `BuildAuditLog` (append-only JSONL) — feeds the repair-history timeline (D-15) directly
- React Flow node set (`StageNode`, `ModuleNode`, `NodeDetailPanel`, `ServiceNode`) — extend, don't rebuild
- Phase 6 XState machines (`nexusApp`, `financePage`, `monitoringPage`) — pattern template for `pipelinePageMachine`
- ActionCard (Phase 6 Plan 03) — chat structured-action pattern to extend for approval cards with blueprints
- Error taxonomy + Framer Motion error components — reuse for rejected/failed build states
- RBAC middleware + role matrix — admin+ gating exists; approval endpoints slot in
- SQLite user_prefs WAL pattern — template for policy config storage if needed

### Established Patterns
- UI renders only from backend contracts (capability envelope / SSE payload) — approval state must arrive via SSE payload extension, never client-side inference
- No silent fallback — rejected/GC'd modules must render explicit states, not disappear
- Install attestation guard (VALIDATED + hash match) — extend to require APPROVED + hash match (D-16)
- Single scheduled worker pattern — new GC/retention worker follows existing background patterns

### Integration Points
- `dashboard_service/pipeline_stream.py` — extend `_build_pipeline_state()` with build-session stage, pending-approval queue, and per-module status
- `orchestrator/admin_api.py` — add approve/reject endpoints beside existing draft endpoints (RBAC admin+)
- `tools/builtin/module_builder.py` — emit stage progress events consumable by the SSE stream; hook walkthrough generation at validation
- `ui_service/src/app/pipeline/page.tsx` — main surface for all UI work
- `ModuleAdminTool` — add approve/reject actions for chat flow

</code_context>

<specifics>
## Specific Ideas

- **"Interactive drawn blueprints"** — user wants module structure presented as a drawn, interactive diagram (not raw JSON/code): blueprint-card aesthetic expanding into a React Flow structure graph
- **"Modules should have a simple interface within"** — every module ships with a simple standard UI surface auto-generated from its canonical output envelope
- **"Memory management in the overlayed artefacts is an essential problem — ensure the module artifacts are removed"** — user explicitly flagged artifact cleanup on rejection as the critical risk of this phase; treat D-10/D-11/D-12 as non-negotiable
- **"Live build and evolution should be visually coherent"** — one visual language across build progress, approval, and evolution states; no bolted-on look

</specifics>

<deferred>
## Deferred Ideas

- Module versioning/rollback UI beyond what approval requires — Phase 9 (REQ-015)
- Marketplace publishing & browsing UI — Phase 9 (REQ-025/026)
- Auto-approve policies (trusted categories, test-based) — config scaffold ships now (D-18), activation deferred
- Multi-approver / approval-chain workflows — enterprise territory, Phase 9
- Path B (DraftManager.promote_draft — dev-mode edits of installed modules) keeps its existing admin+
  RBAC gate WITHOUT the new review-panel/blueprint/walkthrough treatment — RESEARCH.md Open Question Q1
  resolved 2026-08-13 as intentionally out of scope for this phase (already satisfies "explicit user
  approval" via RBAC; revisit in Phase 9 if dev-mode usage grows)

</deferred>

---

*Phase: 8-co-evolution-approval*
*Context gathered: 2026-07-12*
