# NEXUS — Research Summary (GSD Context Pack)

> **GSD Canonical File** | Auto-generated 2026-02-15

This file provides quick-reference pointers to the most relevant source documents for GSD planning context.

---

## Architecture & System Design

| Document | Key Takeaway |
|----------|-------------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | **Current truth**: 7-service gRPC microservice stack, LIDM routing (Standard/Heavy), module system Tracks A1-A3 complete, A4 in progress. 533 lines — read this first. |
| [docs/archive/HIGH_LEVEL_DESIGN.md](../../docs/archive/HIGH_LEVEL_DESIGN.md) | HLD v4.0 with Mermaid diagrams, full port map, component deep dives. Contains supervisor-worker references (historical) alongside current orchestrator design. |
| [docs/archive/PROJECT_VISION.md](../../docs/archive/PROJECT_VISION.md) | Aspirational: dual-agent co-evolution (Curriculum + Executor), provider routing strategy, module marketplace. Track C not yet started. |

## Roadmap & Planning

| Document | Key Takeaway |
|----------|-------------|
| [docs/ROADMAP.md](../../docs/ROADMAP.md) | Current sprint: Track A4 (LLM builder), Pipeline UI, testing. Q2 2026: Track C (co-evolution). Q3: auth + multi-tenant. Q4: scaling. 2027: agent mesh v2. |
| [docs/archive/PLAN.md](../../docs/archive/PLAN.md) | **Critical**: 6-phase commercial hardening plan (Auth → Metering → Audit → Retention → Marketplace → SSO) with file-level implementation details. This is the primary source for commercial requirements. |
| [docs/archive/EXECUTION_PLAN.md](../../docs/archive/EXECUTION_PLAN.md) | 5 parallel tracks (SRE/LLM/Integration/State/Network) with detailed task breakdowns. Tracks A & B mostly complete. |

## Security & Operations

| Document | Key Takeaway |
|----------|-------------|
| [docs/SECURITY.md](../../docs/SECURITY.md) | Fernet credential encryption, sandbox isolation, threat model (Admin API = HIGH risk due to no auth), security roadmap. |
| [docs/OPERATIONS.md](../../docs/OPERATIONS.md) | Health checks, Grafana dashboards, Prometheus queries, troubleshooting playbooks, performance tuning (LIDM thresholds). |
| [docs/KNOWN-ISSUES.md](../../docs/KNOWN-ISSUES.md) | 15 tracked issues: no module builder (#1), no approval gates (#2), no admin tests (#3), dashboard SRP (#4), finance OCP (#5). |

## Business & Strategy

| Document | Key Takeaway |
|----------|-------------|
| [docs/MONETIZATION_STRATEGY.md](../../docs/MONETIZATION_STRATEGY.md) | Hybrid pricing: seats ($49-99) + run-unit metering + marketplace take-rate (85/15). Free/Team/Enterprise tiers. Open-core boundary clearly defined. |
| [docs/NEXUS_LEAN_CANVAS.md](../../docs/NEXUS_LEAN_CANVAS.md) | UVP: "self-evolving agent platform". AARRR metrics, 90-day launch plan, customer segments, unfair advantages (self-evolution, gRPC-native, local-first). |

## API & Extension

| Document | Key Takeaway |
|----------|-------------|
| [docs/API-REFERENCE.md](../../docs/API-REFERENCE.md) | Complete REST + gRPC API reference: Admin API (module CRUD, config, credentials), Dashboard API (context, adapters, SSE), gRPC RPCs. |
| [docs/EXTENSION-GUIDE.md](../../docs/EXTENSION-GUIDE.md) | Step-by-step module building: manifest → adapter → test → install. BaseAdapter[T] pattern, canonical schemas, credential injection. |

## Historical Context

| Document | Key Takeaway |
|----------|-------------|
| [docs/archive/BRANCH_SUMMARY.md](../../docs/archive/BRANCH_SUMMARY.md) | Major branch evolution: multi-provider registry, MCP bridge, crash recovery, self-consistency scoring. OpenClaw competitive analysis. |
| [docs/archive/next-phase.md](../../docs/archive/next-phase.md) | Original self-evolution design (Tiers 1-4): module infra → code gen → lifecycle → self-evolution loop. Faithfully implemented in Tracks A1-A3. |
| [docs/_gsd_import/HISTORY_SUMMARY.md](../../docs/_gsd_import/HISTORY_SUMMARY.md) | Pivot history: supervisor→orchestrator, direct-import→HTTP-bridge, static-categories→dynamic. Lessons and deprecated decisions. |
