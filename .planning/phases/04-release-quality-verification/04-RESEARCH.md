# Phase 4 Research: OTC Policy Storage + Release Verification

> **GSD Research File** | 2026-02-16

---

## Research Scope

Two streams investigated:

1. **OTC (Optimal Tool Calls) policy checkpoint storage** — bridging Phase 2 run-unit metering to a tool-call optimization signal
2. **Release-quality verification infrastructure** — unified test + latency snapshot pipeline

---

## Stream 1: OTC Policy Store Architecture

### Problem Statement

The orchestrator makes tool calls per request. Currently there's no feedback loop telling it whether the number of calls was optimal, excessive, or insufficient. Phase 2 already meters run-units per tool call — the OTC framework creates the reward signal that evaluates tool-call efficiency.

### Key Insight: Policy Optimization, Not Weight Training

This is NOT transformer weight training. The "weights" being saved are routing policy parameters:
- **Per (intent_class, module_set) pair** → estimated optimal tool-call count $n$
- **Arm weights** — per-module average rewards (contextual bandit) or small policy network
- **Confidence bounds** — UCB-style sample count for exploration/exploitation

Total checkpoint size: ~200 bytes per (intent, module_set) pair. The entire `policy_checkpoints` table stays under 1 MB even at 1000+ combinations.

### OTC Reward Function

The OTC-GRPO tool reward peaks when actual calls $m$ equals optimal $n$:

$$r_{\text{tool}} = \sin\left(\frac{f(m,n) \cdot \pi}{2n}\right), \quad f(m,n) = \frac{2nm}{m+n}$$

Composite reward bridges Phase 2 metering:

$$r_{\text{composite}} = \alpha \cdot r_{\text{tool}} \cdot r_{\text{correctness}} - \beta \cdot r_{\text{cost}}$$

Where:
- $r_{\text{correctness}} \in \{0, 1\}$ — contract test pass/fail
- $r_{\text{cost}}$ — normalized run-unit expenditure from Phase 2 `UsageStore`
- $\alpha = 1.0$, $\beta = 0.1$ (default config)

### Storage Schema: 6 Tables

| Table | Purpose | Row Size |
|-------|---------|----------|
| `intent_classes` | Low-cardinality lookup of discovered intent clusters | ~128 bytes |
| `module_sets` | Fingerprint of module set available at decision time | ~256 bytes |
| `policy_checkpoints` | Core lookup: (intent, modules) → optimal_n + arm_weights | ~200 bytes |
| `trajectory_log` | Append-only completed request trajectories | ~150 bytes |
| `reward_events` | Scored trajectories (separates observation from evaluation) | ~100 bytes |

Design follows the proven `UsageStore` pattern: SQLite, WAL mode, append-only for logs, upsert for checkpoints.

### Storage Alternatives Evaluated

| Approach | Verdict |
|----------|---------|
| **SQLite + msgpack BLOBs** | ✅ Selected — matches existing codebase pattern |
| Append-only event log (no checkpoint table) | Rejected — requires recomputing policy on every read |
| Single JSONB row | Rejected — doesn't scale past ~100 combinations |
| Filesystem + SQLite index | Rejected — overengineered for <1MB data |
| TimescaleDB hypertable | Deferred — relevant when trajectory_log > 100M rows |

### Arm Weights Complexity Ceiling

Three options for the `arm_weights` BLOB in `policy_checkpoints`:

1. **Bandit means** (selected for Phase 4): one float per module = ~40 bytes for 10 modules. Recomputable from `trajectory_log`.
2. **LinUCB context vectors**: one weight vector per module × context dim. ~2 KB. Better accuracy.
3. **Small neural policy**: 2-layer MLP, ~50-200 KB. Requires gradient updates. Phase 6+ territory.

### Integration Points

| Component | How OTC Connects |
|-----------|-----------------|
| `shared/billing/usage_store.py` | `run_units` per tool call → `r_cost` signal |
| `orchestrator/rl/reward.py` | Existing Agent0 reward extends with OTC composite |
| `core/graph.py` → `_tools_node` | Tool call count per request = $m$ signal |
| `orchestrator/orchestrator_service.py` | Trajectory capture instrumentation point |

### Existing RL Code Relationship

The `orchestrator/rl/` package contains Agent0-style training infrastructure:
- `reward.py` — uncertainty + tool complexity + cost (3-weight composite)
- `metrics.py` — per-provider stats tracking
- `training.py` — GRPO training loop with PyTorch
- `curriculum_agent.py` — co-evolution scheduler

The OTC reward function lives in `shared/billing/` because it bridges **metering** (Phase 2) to the RL signal. The Agent0 training loop in `orchestrator/rl/` is the consumer (Phase 6+). No architectural conflict.

### Research Sources

- OTC-GRPO framework: tool-call optimization reducing calls by 73.1% while maintaining accuracy on Qwen2.5-7B
- ToolRL: fine-grained reward decomposition (tool name + parameter + value match) for stable convergence
- Existing codebase pattern: `UsageStore` append-only WAL-mode SQLite

---

## Stream 2: Release Verification Infrastructure

### Current Test Landscape

| Category | Count | Runner |
|----------|-------|--------|
| Unit tests | ~530 | `make test-unit` |
| Integration tests | ~200 | `make test-integration` |
| Contract tests | 21+ | `make test-self-evolution` (partial) |
| Feature tests | 46+ | `make test-self-evolution` (partial) |
| Scenario tests | 26+ | `make test-self-evolution` (partial) |
| Auth tests | ✅ | `make auth-test` |
| Billing tests | ✅ | `make billing-test` |
| Showroom | ✅ | `make showroom` (bash script, curl-based) |

### Gap: No Admin API Integration Tests (REQ-019)

The Admin API (`orchestrator/admin_api.py`) has endpoints for:
- Module CRUD (list, get, enable, disable)
- Credential management (set, delete, check)
- Routing config (get, put, patch, delete category, reload)
- Billing (usage, history, quota)
- Dev-mode (drafts, versions, rollback)
- Health check

No integration tests exercise these beyond manual curl. Regressions go undetected.

### Gap: No Unified Verification Command (REQ-028)

Currently requires running 6+ separate make targets. No single pass/fail gate. No latency snapshot.

### Verification Pipeline Design

```
make verify
  ├── Unit tests (pytest tests/unit/)
  ├── Contract tests (pytest tests/contract/)
  ├── Integration tests (pytest tests/integration/)
  ├── Admin API tests (pytest tests/integration/admin/) ← NEW
  ├── Feature tests (pytest tests/feature/)
  ├── Showroom (scripts/showroom_test.sh)
  └── Latency snapshot → data/verify_snapshot.json
```

Exit 0 = all green. Non-zero = failure with structured report.

### Latency Snapshot Format

```json
{
  "timestamp": "2026-02-16T...",
  "orchestrator_version": "git-sha",
  "endpoints": {
    "/admin/health": { "p50_ms": 12, "p95_ms": 45, "p99_ms": 120 },
    "/admin/modules": { "p50_ms": 35, "p95_ms": 90, "p99_ms": 200 }
  },
  "total_tests": 730,
  "passed": 730,
  "failed": 0,
  "duration_s": 45.2
}
```

---

## Decision: Discovery Level

**Level 0 (Skip)** for both streams:
- OTC schema follows existing `UsageStore` SQLite pattern (grep confirms)
- Reward function is pure math (no new dependencies beyond stdlib `math`)
- Admin API tests follow existing `tests/integration/` patterns
- `make verify` extends existing Makefile infrastructure

No external libraries, no new architectural patterns.
