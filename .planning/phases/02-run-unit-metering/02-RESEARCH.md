# Phase 02: Run-Unit Metering Primitive - Research

**Researched:** 2026-02-15
**Domain:** Usage Metering, Billing Primitives, Quota Enforcement, Prometheus Metrics
**Confidence:** HIGH

## Summary

Phase 2 implements per-request compute metering for the NEXUS platform. Every tool call and LLM inference is measured in "run units" — a normalized compute currency — persisted in SQLite, enforced via quota limits, exposed via Prometheus counters, and queryable through the Admin API. This phase depends on Phase 1 (Auth Boundary) for org_id scoping and API key identification.

**Key findings:**
- The `_tools_node` in `core/graph.py` already tracks `start_time`, `latency_ms`, and `tool_name` per call — ideal instrumentation point
- Existing `shared/observability/metrics.py` provides `ToolMetrics` and `ProviderMetrics` dataclasses + OTel counter/histogram factories — the run-unit counter follows the same pattern
- The orchestrator's `_process_query` method is the natural quota-check intercept point (before any compute starts)
- SQLite WAL mode (already used in auth) handles concurrent read/write from orchestrator + admin API
- Phase 1's `org_id` on `AgentState` and auth middleware provides the identity needed for per-org metering

**Primary recommendation:** Create `shared/billing/` package with three modules: `run_units.py` (calculator), `usage_store.py` (SQLite persistence), `quota_manager.py` (enforcement). Wire the calculator into `_tools_node`, the quota check into `_process_query`, billing API into `admin_api.py`, and Prometheus counter into the existing OTel meter.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLite | 3.40+ | Usage records storage | Already used for auth, registry, credentials |
| OpenTelemetry | 1.20+ | Prometheus counter export | Already configured in `shared/observability/` |
| FastAPI | 0.109+ | Billing API endpoints | Already used in `admin_api.py` |
| Pydantic | 2.0+ | Request/response models | Already used throughout |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `time` | stdlib | `time.perf_counter()` for CPU-time measurement | Already used in `_tools_node` |
| `datetime` | stdlib | Period tracking (monthly reset) | Already used throughout |
| `calendar` | stdlib | `monthrange()` for billing period boundaries | Standard library |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLite usage_records | Redis sorted sets | Redis adds infra complexity; SQLite is sufficient for single-node and aligns with existing stores |
| Per-tool-call recording | Per-request aggregation only | Per-tool granularity enables better cost attribution and debugging; slight write overhead is acceptable |
| Simple counter quota | Token bucket rate limiting | Quota is monthly aggregate (100/5000 runs), not per-second rate — simple counter is the right model |
| OTel Counter | Prometheus client_python | OTel already configured with Prometheus exporter; adding a native Prometheus counter would create dual metric pipelines |

**Installation:**
```bash
# All dependencies already present in existing requirements.txt
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure
```
shared/billing/
├── __init__.py          # Export public API
├── run_units.py         # RunUnitCalculator class
├── usage_store.py       # UsageStore class (SQLite persistence)
└── quota_manager.py     # QuotaManager class (enforcement + tier limits)

core/graph.py                       # Instrument _tools_node with run-unit recording
orchestrator/admin_api.py           # Billing API endpoints
orchestrator/orchestrator_service.py # Quota check before _process_query
shared/observability/metrics.py     # Add RunUnitMetrics dataclass + factory
```

### Pattern 1: Run-Unit Formula
**What:** Normalized compute cost per tool execution.
**Formula:** `run_units = max(cpu_seconds, gpu_seconds) × tier_multiplier + tool_overhead`
**Constants:**
```python
TIER_MULTIPLIERS = {
    "standard": 1.0,   # 0.5B model
    "heavy": 1.5,      # 14B model
    "ultra": 3.0,      # Reserved
}

TOOL_OVERHEADS = {
    "default": 0.1,           # Standard tool call
    "sandbox_execute": 0.2,   # Sandbox execution
    "build_module": 0.5,      # Module build (expensive)
    "validate_module": 0.3,   # Module validation
}
```
**When to use:** After every tool execution in `_tools_node`, after every LLM inference.

### Pattern 2: Usage Storage (SQLite)
**What:** Append-only usage records with monthly aggregation.
**Schema:**
```sql
CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    user_id TEXT,
    thread_id TEXT,
    tool_name TEXT NOT NULL,
    run_units REAL NOT NULL,
    tier TEXT DEFAULT 'standard',
    cpu_seconds REAL DEFAULT 0.0,
    latency_ms REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    period TEXT NOT NULL  -- 'YYYY-MM' for monthly aggregation
);

CREATE INDEX IF NOT EXISTS idx_usage_org_period ON usage_records(org_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_org_created ON usage_records(org_id, created_at);
```
**When to use:** Every tool execution and LLM inference recorded as a row.

### Pattern 3: Quota Enforcement
**What:** Pre-request check against monthly aggregate.
**Tier limits:**
```python
TIER_QUOTAS = {
    "free": 100,      # 100 run-units per month
    "team": 5000,     # 5000 run-units per month
    "enterprise": -1, # Unlimited (-1 = no limit)
}
```
**When to use:** At the start of `_process_query` in orchestrator, before any compute begins.
**Error response:** gRPC `RESOURCE_EXHAUSTED` with detail message including current usage and limit.

### Pattern 4: Prometheus Counter Export
**What:** OTel counter exposed via existing Prometheus scrape endpoint.
**Metric:** `nexus_run_units_total{org, tier, tool}` — incremented after each tool execution.
**When to use:** Alongside the SQLite write, using the existing OTel meter pattern from `shared/observability/metrics.py`.

## Dependency Chain

```
Phase 1 (Auth) ──► org_id in AgentState ──► per-org usage tracking
                   │
                   ├── APIKeyStore ──► org plan tier lookup
                   │
                   └── Auth middleware ──► user/org context on request

shared/billing/run_units.py ──► pure calculator, no deps beyond constants
shared/billing/usage_store.py ──► SQLite only
shared/billing/quota_manager.py ──► usage_store + org plan lookup

core/graph.py._tools_node ──► run_units.calculate() + usage_store.record()
orchestrator._process_query ──► quota_manager.check_quota()
admin_api.py ──► usage_store.query() for billing API
metrics.py ──► OTel counter for nexus_run_units_total
```

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Write amplification (one SQLite INSERT per tool call) | LOW | WAL mode handles concurrent writes; batch if >1000 calls/min |
| Quota check adds latency to every request | LOW | Single indexed SELECT; sub-1ms on SQLite |
| Clock skew on period boundaries | LOW | Use server UTC time consistently; period = `strftime('%Y-%m')` |
| GPU seconds not available (CPU-only inference) | LOW | `gpu_seconds` defaults to 0.0; formula degrades to `cpu_seconds × multiplier` |

## Testing Strategy

1. **Unit tests:** `tests/unit/test_billing.py` — calculator formula, usage store CRUD, quota enforcement at boundaries
2. **Integration tests:** `tests/auth/test_billing_integration.py` — end-to-end: tool call → record → quota check → API query
3. **Makefile target:** `make test-billing` runs both suites
