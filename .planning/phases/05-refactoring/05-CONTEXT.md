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

## Wave 3 Addendum (Plan 05-04)

After completion of Waves 1-2, a new refactoring wave was approved to resolve service dependency debt discovered during pipeline UI integration.

### Additional Locked Decisions

1. **Dashboard optional instrumentation must not block startup**: `opentelemetry-instrumentation-fastapi` is optional; missing package cannot crash import-time startup.
2. **No orchestrator→dashboard credential proxy**: Orchestrator uses local `CredentialStore` methods directly (`has_credentials`, `store`, `delete`) instead of HTTP proxying credential operations through dashboard.
3. **SSE loop performs single-pass collection**: Remove dashboard self-probe and deduplicate registry/module loader calls per cycle.
4. **Unknown service state must be explicit**: gRPC-derived service state defaults to `unknown` (not `idle`) and UI must render it intentionally.

### Scope Notes

- Keep changes surgical to service dependency cleanup only; no broad auth or architecture rewrites in this wave.
- Preserve existing behavior for unrelated request/auth helper utilities in orchestrator admin API.
- Update planning artifacts for traceability: add `05-04-PLAN.md` and `05-04-SUMMARY.md`.

---

## Wave 4: Tool Consolidation & SOLID Cleanup (Plan 05-05)

**Gathered:** 2026-02-17
**Status:** Ready for planning
**Data source:** Live SSE pipeline capture from running Docker services

<domain>
### Phase Boundary

Reduce 27 registered tools to ~11 through polymorphic abstraction, eliminate all mock data from production code, delete 769 lines of dead code, and establish a universal `BaseTool` ABC that mirrors the existing `BaseAdapter[T]` pattern. Fix SRP/OCP/ISP/DIP violations in the tool and context layers.

This wave does NOT add new capabilities — it restructures existing tools behind proper abstractions.

</domain>

<decisions>
### Tool Architecture — Locked (NON-NEGOTIABLE)

1. **Universal `BaseTool[TRequest, TResponse]` ABC**: Every tool inherits from BaseTool. Mirrors `BaseAdapter[T]` pattern with `validate_input()`, `execute_internal()`, `format_output()` lifecycle methods. Self-describing: name, description, parameters as class attributes.

2. **`CompositeTool(BaseTool)` for multi-action tools**: Uses Strategy pattern — each action is a separate `ActionStrategy` class. `CompositeTool` holds `List[ActionStrategy]`. `execute()` finds matching strategy by action name.

3. **Typed Pydantic request/response models**: Each tool defines `RequestModel(BaseModel)` and `ResponseModel(BaseModel)`. Strong validation contracts. Separate JSON schemas maintained for LLM tool-calling interface (not auto-generated from Pydantic).

4. **`ToolResult` envelope with metadata**: Standardized return type: `ToolResult(status, data, error, metadata={duration_ms, tool_version, request_id})`. Follows `AdapterResult` pattern. Feeds metering and audit.

5. **Explicit tool registration**: Keep manual `register()` calls in `orchestrator_service.py`. No auto-discovery. More control, easier to debug.

### Tool Consolidation — Locked (NON-NEGOTIABLE)

6. **Collapse user context tools**: `get_user_context`, `get_daily_briefing`, `get_commute_time` → single `UserContextTool(BaseTool)` with category parameter. Briefing = category="all". Commute = category="navigation".

7. **Absorb `finance_query` into `UserContextTool`**: `user_context(category="finance", action="query", search="uber")`. Single tool handles both summaries and structured queries (pagination, sort, filter).

8. **2 composite module tools**:
   - `ModulePipelineTool(CompositeTool)` — build, write, repair, validate, install (build through install)
   - `ModuleAdminTool(CompositeTool)` — drafts, versions, enable/disable, credentials, list, uninstall

9. **Merge `web_search` + `load_web_page`**: → single `WebTool(BaseTool)` with action param (search vs load).

10. **Keep knowledge tools separate**: `search_knowledge` and `store_knowledge` stay as `KnowledgeSearchTool(BaseTool)` and `KnowledgeStoreTool(BaseTool)`. ChromaDB-specific, different backend from web.

### Dead Code Removal — Locked (NON-NEGOTIABLE)

11. **Delete `destinations.py`** (137 lines): Never registered as tool. Inline alias logic in user_context.
12. **Delete `feature_test_harness.py`** (253 lines): Never called from orchestrator. No call path.
13. **Delete `chart_validator.py`** (379 lines): Never registered as tool. Total: 769 lines removed.

### Context Data Flow — Locked (NON-NEGOTIABLE)

14. **`ContextBridge` class (service object, not generic)**: `__init__(dashboard_url)`, `fetch(categories)`, `normalize()`. Injected into tools. Sole data source for all context data.

15. **Adapter self-describes normalization**: `BaseAdapter` gets abstract `normalize_for_tools()` method. Each adapter (cibc, openweather, etc.) implements its own normalization. Removes the hardcoded 6-category switch in `_normalize_context_for_tools()`. Fixes OCP violation.

16. **Delete ALL mock data**:
    - Delete inline `_get_mock_context()` (130 lines) from `user_context.py`
    - Delete `shared/adapters/finance/mock.py`
    - Delete `shared/adapters/calendar/mock.py`
    - Delete `shared/adapters/health/mock.py`
    - Delete `shared/adapters/navigation/mock.py`
    - If real adapter has no credentials, return empty data with status message. No synthetic data in production.
    - Test fixtures only in `tests/` directory.

17. **Empty categories are acceptable**: Health and navigation show nothing until real adapters are added. Categories without data return `{'category': 'weather', 'status': 'no credentials configured'}`. Clean and honest.

### Claude's Discretion

- Exact naming conventions for ActionStrategy subclasses
- Internal dispatch mechanism within CompositeTool (dict lookup vs match/case)
- Whether to create a shared `OperationBase` ABC for both `BaseAdapter` and `BaseTool` (suggested: NO — keep them separate, just mirror patterns)
- Exact ToolResult metadata fields beyond duration_ms, tool_version, request_id
- How to handle finance_query's pagination/sort params when absorbed into UserContextTool
- Migration strategy: big-bang rewrite vs incremental (suggested: incremental with backward-compat shim)

</decisions>

<specifics>
### Specific References

- BaseTool MUST mirror BaseAdapter lifecycle: `validate_input()` → `execute_internal()` → `format_output()`. The user wants polymorphic consistency across the entire codebase.
- "Follow polymorphism when designing the APIs so they will be derived in the structural flow and an abstract class and interfaces that define the virtual functions. Derived classes will override the platform-specific functions."
- No overlap tolerated. Every data path must have exactly one owner.
- Strategy pattern chosen for CompositeTool sub-actions (not action registry dict, not abstract methods per action).

### Target Tool Count

| Before | After | Tool |
|--------|-------|------|
| get_user_context + get_daily_briefing + get_commute_time + finance_query | UserContextTool | 4 → 1 |
| web_search + load_web_page | WebTool | 2 → 1 |
| build_module + write_module_code + repair_module + validate_module + install_module | ModulePipelineTool | 5 → 1 |
| list_modules + enable_module + disable_module + store_module_credentials + uninstall_module + create_draft + edit_draft + diff_draft + validate_draft + promote_draft + list_versions + rollback_version | ModuleAdminTool | 12 → 1 |
| search_knowledge | KnowledgeSearchTool | 1 → 1 |
| store_knowledge | KnowledgeStoreTool | 1 → 1 |
| math_solver | MathSolverTool | 1 → 1 |
| execute_code | CodeExecutorTool | 1 → 1 |
| **TOTAL** | | **27 → 8** |

### Files to Delete (769 lines)
- `tools/builtin/destinations.py`
- `tools/builtin/feature_test_harness.py`
- `tools/builtin/chart_validator.py`
- `shared/adapters/finance/mock.py`
- `shared/adapters/calendar/mock.py`
- `shared/adapters/health/mock.py`
- `shared/adapters/navigation/mock.py`

</specifics>

<deferred>
### Deferred Ideas

- Shared `OperationBase` ABC for both `BaseAdapter` and `BaseTool` — evaluate after BaseTool is stable
- Auto-discovery via `@register_tool` decorator — future phase if tool count grows
- Auto-generation of LLM tool schemas from Pydantic models — revisit when schema drift becomes a problem
- Plugin-style module tool loading — future phase with marketplace

</deferred>

---

*Phase: 05-refactoring (Wave 4)*
*Context gathered: 2026-02-17*

