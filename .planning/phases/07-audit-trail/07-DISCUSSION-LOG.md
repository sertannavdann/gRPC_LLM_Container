# Phase 7: Audit Trail - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-08
**Phase:** 7-audit-trail
**Areas discussed:** Audit sink unification, Immutability enforcement, Audit write failure semantics, Before/after state capture, Coverage scope

---

## Audit Sink Unification

| Option | Description | Selected |
|--------|-------------|----------|
| A. Single queryable sink | New SQLite store is THE audit log; DevModeAuditLog dual-writes (JSONL preserved per Phase 8 D-10); BuildAuditLog stays a per-build artifact | ✓ |
| B. Coexist | New table covers only Admin API HTTP mutations; existing JSONL logs untouched | |
| C. Full migration | Retire JSONL entirely (conflicts with Phase 8 D-10) | |

**User's choice:** A (recommended option)
**Notes:** Batch acceptance — "continue with recommendations."

---

## Immutability Enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| A. Convention only | Append-only by code convention, no UPDATE/DELETE paths | |
| B. SQLite triggers | Triggers RAISE on UPDATE/DELETE | |
| C. Triggers + hash chain | B plus per-row prev_hash for tamper evidence | ✓ |

**User's choice:** C (recommended option)
**Notes:** Fits "Enterprise Foundation — Audit" milestone branding.

---

## Audit Write Failure Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| A. Fail-open | Log error, mutation proceeds (matches Phase 2 metering) | |
| B. Fail-closed | Mutation rejected if audit insert fails | ✓ |
| C. Hybrid | Fail-closed for credentials/keys/approvals, fail-open for config toggles | |

**User's choice:** B (recommended option)
**Notes:** Deliberate divergence from metering's fail-open — audit is a compliance guarantee, not telemetry.

---

## Before/After State Capture

| Option | Description | Selected |
|--------|-------------|----------|
| A. Full snapshots + redaction | Full JSON before/after; secrets replaced with [REDACTED] + SHA-256 fingerprint | ✓ |
| B. Field-level diffs | Smaller rows, but state not reconstructible at a point in time | |

**User's choice:** A (recommended option)
**Notes:** Redaction enforced at the store layer, not per-endpoint.

---

## Coverage Scope

| Option | Description | Selected |
|--------|-------------|----------|
| A. Orchestrator Admin API only | Literal ROADMAP scope (:8003) | |
| B. Plus dashboard admin mutations | Adds :8001 /admin/* mutations | |
| C. Plus chat-tool mutations | Audit at shared store layer; ModuleAdminTool actions cannot bypass | ✓ |

**User's choice:** C (recommended option)
**Notes:** Phase 8 chat approval (D-02/D-19) effectively requires tool-level coverage.

---

## Claude's Discretion

- SQLite schema DDL, index strategy, DB file location
- Hash-chain serialization format and genesis-row handling
- Redaction registry structure
- Decorator implementation details (before-state read per resource type)
- CSV export streaming strategy
- Grafana audit panel layout
- Dual-write mechanics (sync vs adapter shim)
- Actor representation for non-HTTP (chat-tool) mutations

## Deferred Ideas

- Audit retention/pruning tiers (interacts with REQ-017; revisit Phase 9)
- SIEM/webhook export beyond CSV (Phase 9)
- Cryptographic anchoring/external timestamping of hash chain (Phase 9)
- Dedicated audit UI page in ui_service beyond Grafana panel (Phase 9)
