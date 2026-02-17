---
phase: 05-refactoring
plan: 05
subsystem: tools, orchestrator
tags: [BaseTool, CompositeTool, ActionStrategy, dependency-injection, OCP, SOLID]

requires:
  - phase: 05-refactoring plan 03
    provides: DraftManager/VersionManager wiring, adapter lock/unlock
  - phase: 05-refactoring plan 04
    provides: SSE cleanup, credential proxy elimination
provides:
  - BaseTool[TRequest, TResponse] ABC with validate/execute/format lifecycle
  - CompositeTool with ActionStrategy dispatch pattern
  - 8 consolidated tools replacing 27 registrations
  - ContextBridge injectable service (replaces module-level functions)
  - normalize_for_tools() / normalize_category_for_tools() on BaseAdapter (OCP fix)
  - Mock adapter deletion (4 files removed)
  - Dead code deletion (3 files removed)
affects: [orchestrator, core/graph, tools/builtin, shared/adapters]

tech-stack:
  added: []
  patterns: [BaseTool ABC, CompositeTool+ActionStrategy, constructor DI, backward-compat aliases]

key-files:
  created:
    - tools/builtin/web_tools.py
    - tools/builtin/knowledge_store.py
    - tools/builtin/module_pipeline.py
    - tools/builtin/module_admin.py
  modified:
    - tools/base.py
    - tools/builtin/__init__.py
    - tools/builtin/user_context.py
    - tools/builtin/context_bridge.py
    - tools/builtin/knowledge_search.py
    - tools/builtin/math_solver.py
    - tools/builtin/code_executor.py
    - shared/adapters/base.py
    - shared/adapters/__init__.py
    - orchestrator/orchestrator_service.py
    - core/graph.py
    - dashboard_service/aggregator.py

key-decisions:
  - "Keep old module_builder/validator/installer/manager files as implementation backends for CompositeTool strategies (thin delegation, not duplication)"
  - "Add backward-compat aliases for all 27 old tool names to preserve LLM prompt references"
  - "normalize_category_for_tools() as classmethod on adapters (OCP: new adapters add normalization without modifying ContextBridge)"
  - "ContextBridge as injectable class with env-var fallback defaults (testable, no global state)"

patterns-established:
  - "BaseTool ABC: validate_input -> execute_internal -> format_output lifecycle"
  - "CompositeTool + ActionStrategy: action='X' dispatch for multi-action tools"
  - "Constructor DI: dependencies passed at creation, not via set_* globals"
  - "Backward-compat wrapper functions at module level for gradual migration"

duration: ~45min
completed: 2026-02-17
---

# Phase 5 Plan 05: Tool Consolidation & SOLID Cleanup Summary

**BaseTool ABC hierarchy consolidating 27 tool registrations into 8 polymorphic classes with constructor DI, OCP-compliant adapter normalization, and mock/dead code elimination**

## Performance

- **Duration:** ~45 min (across 2 sessions)
- **Tasks:** 5
- **Files modified:** 40

## Accomplishments

- Created BaseTool[TRequest, TResponse] ABC mirroring BaseAdapter[T] pattern with validate/execute/format lifecycle
- Consolidated 27 tool registrations into 8 primary tools (UserContextTool, WebTool, KnowledgeSearchTool, KnowledgeStoreTool, MathSolverTool, CodeExecutorTool, ModulePipelineTool, ModuleAdminTool)
- Fixed OCP violation: adapter normalization now lives on adapter classmethods, not in conditional chains
- Deleted 4 mock adapter files and 3 dead code files
- Eliminated _register_draft_version_tools() closure method (logic moved to ModuleAdminTool)

## Task Commits

Each task was committed atomically:

1. **Task 1: BaseTool ABC** - `c1d2a8e` (refactor)
2. **Task 2: Delete dead code** - `14e6d7a` (refactor)
3. **Task 3: ContextBridge + adapters + mock deletion** - `46ccd2a` (refactor)
4. **Task 4: Build 8 consolidated tool classes** - `8d2ad8d` (refactor)
5. **Task 5: Rewire orchestrator + cleanup** - `89a605c` (refactor)

## Files Created/Modified

### Created
- `tools/builtin/web_tools.py` — WebTool merging web_search + web_loader with backward-compat functions
- `tools/builtin/knowledge_store.py` — KnowledgeStoreTool split from knowledge_search
- `tools/builtin/module_pipeline.py` — ModulePipelineTool (CompositeTool) with 5 strategies: build, write_code, repair, validate, install
- `tools/builtin/module_admin.py` — ModuleAdminTool (CompositeTool) with 12 strategies: list, enable, disable, credentials, uninstall, create_draft, edit_draft, diff_draft, validate_draft, promote_draft, list_versions, rollback_version

### Modified (key files)
- `tools/base.py` — Added BaseTool ABC, CompositeTool, ActionStrategy, ToolResult, BaseToolLegacy
- `tools/builtin/user_context.py` — Rewritten as UserContextTool class absorbing finance_query logic
- `tools/builtin/context_bridge.py` — Rewritten as ContextBridge injectable class
- `tools/builtin/knowledge_search.py` — Rewritten as KnowledgeSearchTool class
- `tools/builtin/math_solver.py` — Rewritten as MathSolverTool class
- `tools/builtin/code_executor.py` — Rewritten as CodeExecutorTool class
- `shared/adapters/base.py` — Added normalize_for_tools() and normalize_category_for_tools()
- `orchestrator/orchestrator_service.py` — Replaced 27 registrations with 8 primary + aliases, removed _register_draft_version_tools()
- `core/graph.py` — Added "module_pipeline" to _is_module_build_session() check

### Deleted
- `tools/builtin/destinations.py` — Dead code (no callers)
- `tools/builtin/feature_test_harness.py` — Dead code (no callers)
- `tools/builtin/chart_validator.py` — Dead code (guarded import, no callers)
- `shared/adapters/finance/mock.py` — Mock adapter replaced by real CIBC adapter
- `shared/adapters/calendar/mock.py` — Mock adapter replaced by real Google Calendar adapter
- `shared/adapters/health/mock.py` — Mock adapter with no real replacement
- `shared/adapters/navigation/mock.py` — Mock adapter with no real replacement

## Decisions Made

1. **Kept old module files as implementation backends**: module_builder.py, module_validator.py, module_installer.py, module_manager.py contain complex logic that ModulePipelineTool/ModuleAdminTool strategies delegate to via lazy imports. Deleting them would require duplicating ~500 lines of implementation.

2. **Kept web_search.py, web_loader.py, finance_query.py**: Test files patch internal `requests` objects in these modules. Added backward-compat functions to web_tools.py instead. Tests continue to pass without modification.

3. **normalize_category_for_tools() as classmethod**: Enables calling without an adapter instance (ContextBridge doesn't hold adapter instances). New adapters add their own normalization method without touching ContextBridge.

4. **22 backward-compat aliases**: Every old tool name (get_user_context, build_module, web_search, etc.) registered as alias pointing to the new consolidated tool instance. LLM prompts and intent patterns continue to work unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Kept old tool files instead of deleting**
- **Found during:** Task 5 (orchestrator rewiring)
- **Issue:** Plan specified deleting module_builder.py, module_validator.py, module_installer.py, module_manager.py, web_search.py, web_loader.py, finance_query.py. However, ModulePipelineTool strategies do lazy imports from these files, and test files patch their internal request objects.
- **Fix:** Kept all 7 files. Added backward-compat wrapper functions to web_tools.py. The old files serve as implementation backends and test-compatible modules.
- **Files modified:** tools/builtin/web_tools.py (added backward-compat functions)
- **Verification:** All imports succeed, math_solver evaluates correctly, no broken test patches

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking)
**Impact on plan:** Minimal. The consolidation goal was achieved at the orchestrator registration level. Old files remain as implementation backends, not as registered tools.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tool consolidation complete: 8 primary tools with backward-compat aliases
- BaseTool ABC established as pattern for future tool development
- Ready for Phase 7 (Audit Trail) or any further refactoring

---
*Phase: 05-refactoring*
*Completed: 2026-02-17*
