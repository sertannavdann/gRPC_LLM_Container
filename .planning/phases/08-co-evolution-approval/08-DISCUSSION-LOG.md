# Phase 8: Co-Evolution & Approval - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 8-co-evolution-approval
**Areas discussed:** Approval Surface & Placement, Review Content Depth & Module HMI, Rejection & Artifact Cleanup, Live Build Visual Coherence, Approval Policy & RBAC

---

## Approval Surface & Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Extend Pipeline page | VALIDATED module = pending-approval node in React Flow; review in NodeDetailPanel | ✓ |
| Dedicated /approvals page | Queue/inbox page with full-page review view | |
| Hybrid | Badge on pipeline + full-screen review + slide-over queue | |

**User's choice:** A — extend the Pipeline page.
**Notes:** Chat approval also enabled, "with optional inputs and interactive drawn blueprints." SSE chosen over CapabilityEnvelope for approval state transport. Notification = "inject the module into the available services as a badge" (the graph itself is the notification surface).

---

## Review Content Depth & Module HMI

| Option | Description | Selected |
|--------|-------------|----------|
| React Flow mini-graph | Module structure as interactive node graph | |
| Blueprint card | Designed SVG schematic, technical-drawing style | |
| Both, progressive | Blueprint card summary expanding into React Flow structure graph | ✓ |

**User's choice:** C (progressive blueprint); ALL five review layers (blueprint, code diff, sandbox report, credentials, repair history) "with dropdown the ability" (collapsible sections); A for module HMI — every installed module gets a standard auto-generated UI surface from the AdapterRunResult envelope; plain-language walkthrough generated once at validation time and stored with the draft.

---

## Rejection & Artifact Cleanup

**User's choice:** User flagged the essential problem: "memory management in the overlayed artefacts... we need to ensure the module artifacts to be removed." Detailed mechanics delegated to Claude's recommendations under autonomy grant.
**Resolved as:** Reject-with-feedback → one bounded repair cycle via `gateway.generate(purpose=REPAIR)`; reject-without-feedback terminal → purge draft dirs, bundles, unreferenced version overlays; audit JSONL preserved; single background GC worker shared with REQ-017 retention cleanup; reference-safety check against `active_versions` pointers before delete.

---

## Live Build Visual Coherence

**User's choice:** "Live build and evolution should be visually coherent." Mechanics delegated under autonomy grant.
**Resolved as:** SSE-driven StageNode progression using Phase 6 status colors/error taxonomy/design tokens; new `pipelinePageMachine` (XState v5); per-attempt timeline from BuildAuditLog; Framer Motion transitions.

---

## Approval Policy & RBAC

**User's choice:** Selected for discussion ("approval and RBAC"); mechanics delegated under autonomy grant.
**Resolved as:** Always-manual approval (done criterion), enforced at install attestation guard; approve/reject = admin+ (matches validate/promote RBAC); chat approval enforces same RBAC; policy config scaffold with `auto_approve: false` hard default; full actor/timestamp/hash audit records.

---

## Claude's Discretion

- Non-UI deliverables (trace retention tiers, rate limiter implementation, Playwright E2E scope)
- Blueprint card visual design; mini-graph layout algorithm
- GC schedule/batching; walkthrough prompt design; generic module panel layout
- Chat blueprint rendering: React Flow reuse vs lighter SVG variant

## Deferred Ideas

- Module versioning/rollback UI beyond approval needs — Phase 9 (REQ-015)
- Marketplace publishing/browsing — Phase 9
- Auto-approve policy activation — scaffold only this phase
- Multi-approver chains — Phase 9

## Session Note

User granted full autonomy mid-discussion: "Have more autonomy into keep building what is requested by having the recommendations followed-up. I want you to keep on building with no input — I won't be in front of my Laptop, keep building." Areas 3–5 were resolved by adopting Claude's stated recommendations; the workflow chains into planning and execution autonomously.
