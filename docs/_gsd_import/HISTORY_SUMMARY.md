# GSD Import — Historical Context Summary

> **Generated**: 2026-02-15
> **Source**: `docs/archive/**`

## Major Pivots

- **Dec 2025 → Jan 2026: Supervisor-Worker Mesh → Unified Orchestrator.** The original multi-agent architecture (supervisor + specialized workers communicating via gRPC mesh) was replaced by a single orchestrator with LIDM routing. Reason: high message-passing overhead, complex state sync, difficult debugging. Outcome: simpler codebase, faster request path, LIDM handles specialization without coordination cost.

- **Jan 2026: LIDM (Language-Integrated Decision Making) introduced.** Small 0.5B model classifies query complexity and routes to Standard (fast/cheap) or Heavy (slow/quality) tier. Added ~200ms overhead but reduced 70% of queries to sub-second latency.

- **Jan 2026: HTTP Context Bridge replaced direct Python imports.** Orchestrator no longer imports dashboard adapters directly; communicates via HTTP REST. Decoupled services for independent scaling and eliminated circular dependencies.

- **Jan–Feb 2026: Self-evolving module system (Track A) built.** Module loader (importlib dynamic imports), SQLite registry, Fernet credential store, `@register_adapter` decorator pattern, module manifest schema. Infrastructure complete; LLM-driven builder (A4) still in progress.

## Deprecated Decisions

- **Supervisor-Worker Mesh** — fully removed Jan 2026; docs deleted. The pattern is superseded by the unified orchestrator.
- **Direct Python imports for cross-service data** — replaced by HTTP Context Bridge.
- **Static adapter categories (enum-only)** — now supports dynamic string categories for module-defined types.

## Lessons Learned

- The archive `PLAN.md` contains a detailed 6-phase commercial hardening roadmap (Auth → Metering → Audit → Retention → Marketplace → SSO) that was designed but never started. This is the primary source for commercial requirements.
- The archive `next-phase.md` is the definitive design doc for the self-evolution loop (Tiers 1-4) and was faithfully implemented in Tracks A1–A3.
- `EXECUTION_PLAN.md` organized 5 parallel tracks (SRE, LLM, Integration, State, Network) — Tracks A & B are mostly complete; C (integration) is partial.
- The project evolved from "multi-agent platform" → "self-evolving agent system" → "open-core commercial platform" — each pivot preserved backward compatibility.
