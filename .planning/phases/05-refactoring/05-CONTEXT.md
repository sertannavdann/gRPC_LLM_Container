# Phase 05 — Refactoring: Context

> User decisions from planning discussion

---

## Problem Statement

The NEXUS codebase has accumulated redundancy across Phase 3 (Self-Evolution Engine). Six areas of duplicated code exist across the module builder, validator, installer, contracts, and sandbox service. The build pipeline invokes the LLM Gateway as a stateless code-generation endpoint without structured agent identities or auto-prompt composition. Adapter connections use inline lambdas in hardcoded definitions, disconnected from the provider lock/unlock pattern established in Phase 4. The finance page uses an iframe that cannot resolve Docker-internal DNS from the browser. DraftManager and VersionManager exist but are not registered as orchestrator chat tools.

This phase eliminates all technical debt before any UI work begins, ensuring Phase 6 (UX/UI Visual Expansion) operates on a clean, unified codebase.

## Academic Anchors

Two research documents inform the design decisions in this phase:

### Event-Driven Microservice Orchestration Principles (EDMO)

- **T1 (Saga Pattern)**: Build pipeline stages map to orchestration-based saga with compensating actions
- **T4 (Bounded Retry with Jitter)**: `min(base * 2^attempt, cap) + random_jitter` for LLM provider transient failures. Benchmarks: reduces P99 from 2600ms to 1100ms, error rate from 17% to 3%
- **T6 (CQRS)**: Module status/reporting (read) separated from build pipeline (write)
- **Outbox Pattern**: Immutable per-attempt artifacts as event store for audit and replay

### Agentic Builder-Tester Pattern for NEXUS

- **§3.2 (soul.md Structure)**: Mission, Scope, Capabilities, Guardrails, Interfaces, Metrics, Stop Conditions, Acceptable Patterns
- **§4.1 (Auto-Prompt Composition)**: `compose(system=soul.md, context=stage, intent=request, repair_hints=validator)`
- **§4.3 (Blueprint2Code Confidence Scoring)**: Score scaffolds on completeness, feasibility, edge-case handling, efficiency, quality. Reject confidence < 0.6
- **§2.3 (Planner-Coder Gap)**: 75.3% of multi-agent failures from vague plans. Mitigate with multi-prompt generation + monitor agent
- **§8 (Self-Correcting Pipeline)**: Iterative agent loops improve success rate from 53.8% to 81.8%

## Decisions

### Locked (NON-NEGOTIABLE)

1. **Consolidate all duplicated code before any UI work**: FORBIDDEN_IMPORTS, AST import checker, module_id parsing, SHA-256 hashing, error shapes — single source of truth for each.
2. **soul.md agent identities created AND wired**: Builder, Tester, Monitor agents with version-controlled soul.md files + `compose()` function integrated into build pipeline. Not just designed — actively used.
3. **Adapter connections use lock/unlock pattern**: Same `ProviderUnlockBase` pattern from Phase 4 extended to adapter connections. Replaces inline lambdas in hardcoded `ADAPTER_DEFINITIONS`.
4. **Finance backend path consolidation**: Single API proxy path only. Iframe removed. Lock/unlock gating wired so Phase 6 just renders it.
5. **DraftManager + VersionManager registered as orchestrator tools**: Chat agent can manage module drafts conversationally.
6. **Remove direct .env file manipulation**: Replace `readFileSync`/`writeFileSync` of `.env` in adapter routes with Admin API credential store calls.

### Deferred Ideas

- UI page rendering (Phase 6)
- Marketplace module publishing (Phase 9)
- E2E Playwright tests for Pipeline UI SSE
- Adaptive pipeline reconfiguration (self-evolving workflow type)
- Curriculum Agent / Executor Agent co-evolution (Phase 8)

### Claude's Discretion

- Exact naming convention for adapter lock subclasses
- soul.md file path structure (suggested: `agents/souls/`)
- Blueprint2Code confidence threshold (suggested: 0.6)
- Bounded retry backoff base/cap values (suggested: 1s/30s)
- Whether to create `AdapterUnlockBase` or reuse `ProviderUnlockBase` directly
