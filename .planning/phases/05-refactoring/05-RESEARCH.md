# Phase 05: Refactoring Wave 4 — Tool Consolidation & SOLID Cleanup - Research

**Researched:** 2026-02-17
**Domain:** Python tool architecture, ABC/Generic patterns, SOLID principles, adapter pattern
**Confidence:** HIGH — all findings from direct codebase inspection

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Tool Architecture
1. **Universal `BaseTool[TRequest, TResponse]` ABC**: Every tool inherits from BaseTool. Mirrors `BaseAdapter[T]` pattern with `validate_input()`, `execute_internal()`, `format_output()` lifecycle methods. Self-describing: name, description, parameters as class attributes.
2. **`CompositeTool(BaseTool)` for multi-action tools**: Uses Strategy pattern — each action is a separate `ActionStrategy` class. `CompositeTool` holds `List[ActionStrategy]`. `execute()` finds matching strategy by action name.
3. **Typed Pydantic request/response models**: Each tool defines `RequestModel(BaseModel)` and `ResponseModel(BaseModel)`. Strong validation contracts. Separate JSON schemas maintained for LLM tool-calling interface (not auto-generated from Pydantic).
4. **`ToolResult` envelope with metadata**: Standardized return type: `ToolResult(status, data, error, metadata={duration_ms, tool_version, request_id})`. Follows `AdapterResult` pattern. Feeds metering and audit.
5. **Explicit tool registration**: Keep manual `register()` calls in `orchestrator_service.py`. No auto-discovery.

#### Tool Consolidation
6. **Collapse user context tools**: `get_user_context`, `get_daily_briefing`, `get_commute_time` → single `UserContextTool(BaseTool)` with category parameter.
7. **Absorb `finance_query` into `UserContextTool`**: `user_context(category="finance", action="query", search="uber")`. Single tool handles both summaries and structured queries.
8. **2 composite module tools**: `ModulePipelineTool(CompositeTool)` and `ModuleAdminTool(CompositeTool)`.
9. **Merge `web_search` + `load_web_page`**: → single `WebTool(BaseTool)` with action param.
10. **Keep knowledge tools separate**: `KnowledgeSearchTool(BaseTool)` and `KnowledgeStoreTool(BaseTool)`.

#### Dead Code Removal
11. Delete `tools/builtin/destinations.py` (137 lines)
12. Delete `tools/builtin/feature_test_harness.py` (253 lines)
13. Delete `tools/builtin/chart_validator.py` (379 lines)

#### Context Data Flow
14. **`ContextBridge` class**: Service object injected into tools. `__init__(dashboard_url)`, `fetch(categories)`, `normalize()`.
15. **Adapter self-describes normalization**: `BaseAdapter` gets abstract `normalize_for_tools()`. Removes hardcoded 6-category switch. Fixes OCP.
16. **Delete ALL mock data**: All 4 mock adapter files + inline `_get_mock_context()`. No synthetic data in production.
17. **Empty categories acceptable**: Return status message for unconfigured adapters.

### Claude's Discretion
- Exact naming conventions for ActionStrategy subclasses
- Internal dispatch mechanism within CompositeTool (dict lookup vs match/case)
- Whether to create a shared `OperationBase` ABC for both `BaseAdapter` and `BaseTool` (suggested: NO)
- Exact ToolResult metadata fields beyond duration_ms, tool_version, request_id
- How to handle finance_query's pagination/sort params when absorbed into UserContextTool
- Migration strategy: big-bang rewrite vs incremental (suggested: incremental with backward-compat shim)

### Deferred Ideas (OUT OF SCOPE)
- Shared `OperationBase` ABC for both `BaseAdapter` and `BaseTool`
- Auto-discovery via `@register_tool` decorator
- Auto-generation of LLM tool schemas from Pydantic models
- Plugin-style module tool loading
</user_constraints>

---

## Summary

This wave is a pure restructuring of the tool layer — no new capabilities. The existing codebase has 27 registered tools implemented as module-level functions following the Google ADK pattern (return `Dict[str, Any]` with a `status` key). The `LocalToolRegistry` stores callables and invokes them via `callable(**kwargs)`. The graph node (`_tools_node` in `core/graph.py`) calls `registry.get(tool_name)` and then `tool(**tool_args)` — it does not care whether the callable is a function or a class instance with `__call__`. This means class-based tools can be introduced with zero changes to graph.py or registry.py, provided the tool instance is callable and returns a dict with a `status` key.

The `BaseAdapter[T]` pattern in `shared/adapters/base.py` is the direct model for the new `BaseTool[TRequest, TResponse]`. The adapter lifecycle is `fetch_raw()` → `transform()` → wrapped in `fetch()` which returns `AdapterResult`. The tool lifecycle must mirror this: `validate_input()` → `execute_internal()` → `format_output()` → wrapped in `execute()` which returns `ToolResult`. The existing `ToolResult` dataclass in `tools/base.py` must be extended with `metadata` to match `AdapterResult`.

The most complex part of this wave is the mock deletion. The 4 mock adapter files are registered via `@register_adapter` at import time through `shared/adapters/__init__.py`. The `DashboardAggregator` in `dashboard_service/aggregator.py` has a `UserConfig` that defaults `calendar`, `health`, and `navigation` to `["mock"]`. Deleting mock adapters means the aggregator will find no registered platform for those categories and return empty data — which is the intended behavior per decision #17. The `UserConfig` defaults must be updated to empty lists when mock adapters are removed.

**Primary recommendation:** Use incremental migration with class-based `__call__` shims to preserve registry backward-compatibility. Wire the new ABC hierarchy in `tools/base.py`, convert tools one group at a time, then clean up function-based imports. Delete mock files last (after confirming aggregator defaults are updated).

---

## Standard Stack

### Core (already in project — no new dependencies needed)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| `abc` (stdlib) | any | ABC base class for BaseTool | Already used in `shared/adapters/base.py` |
| `typing.Generic`, `TypeVar` | any | Generic type parameters `[TRequest, TResponse]` | Already pattern in BaseAdapter |
| `pydantic.BaseModel` | v2 (already in project) | Request/response validation | Already used in orchestrator routing config |
| `dataclasses.dataclass` | any | `ToolResult` envelope | Already used in `AdapterResult` |
| `datetime` (stdlib) | any | `duration_ms` timing in metadata | Standard |
| `uuid` (stdlib) | any | `request_id` in metadata | Standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `requests` | already pinned | HTTP calls in ContextBridge class | Already used in context_bridge.py |

**Installation:** No new packages required. All libraries are already in use.

---

## Architecture Patterns

### Recommended File Structure

```
tools/
├── base.py                    # EXTEND: BaseTool ABC + ToolResult + ActionStrategy
├── registry.py                # UNCHANGED: LocalToolRegistry stays as-is
├── builtin/
│   ├── __init__.py
│   ├── context_bridge.py      # REPLACE: module functions → ContextBridge class
│   ├── user_context.py        # REPLACE: 4 funcs → UserContextTool(BaseTool)
│   ├── web_tools.py           # NEW: WebTool(BaseTool) merging web_search + web_loader
│   ├── knowledge_search.py    # REFACTOR: KnowledgeSearchTool(BaseTool)
│   ├── knowledge_store.py     # REFACTOR: KnowledgeStoreTool(BaseTool)
│   ├── module_pipeline.py     # NEW: ModulePipelineTool(CompositeTool)
│   ├── module_admin.py        # NEW: ModuleAdminTool(CompositeTool)
│   ├── math_solver.py         # REFACTOR: MathSolverTool(BaseTool)
│   ├── code_executor.py       # REFACTOR: CodeExecutorTool(BaseTool)
│   │
│   │   # TO DELETE:
│   ├── destinations.py        # DELETE: 137 lines
│   ├── feature_test_harness.py # DELETE: 253 lines
│   ├── chart_validator.py     # DELETE: 379 lines
│   │
│   │   # EXISTING (kept for backward compat during migration then removed):
│   ├── web_search.py          # REMOVE after WebTool complete
│   ├── web_loader.py          # REMOVE after WebTool complete
│   ├── finance_query.py       # REMOVE after UserContextTool absorbs it
│   ├── module_builder.py      # REMOVE after ModulePipelineTool complete
│   ├── module_validator.py    # REMOVE after ModulePipelineTool complete
│   ├── module_installer.py    # REMOVE after ModulePipelineTool complete
│   └── module_manager.py      # REMOVE after ModuleAdminTool complete
```

### Pattern 1: BaseTool[TRequest, TResponse] ABC

**What:** Abstract generic base class mirroring `BaseAdapter[T]` pattern exactly.

**Contract the registry requires:** The registry stores any callable and calls it via `callable(**kwargs)`. The graph calls `tool(**tool_args)` expecting a `dict` return with a `status` key. Therefore, class-based tools MUST implement `__call__(self, **kwargs) -> Dict[str, Any]`.

**Lifecycle methods (mirror of fetch_raw → transform → fetch):**
```python
# Source: direct inspection of shared/adapters/base.py
TRequest = TypeVar('TRequest')
TResponse = TypeVar('TResponse')

class BaseTool(ABC, Generic[TRequest, TResponse]):
    name: str = ""
    description: str = ""
    version: str = "1.0.0"

    # Subclasses define these:
    RequestModel: Type[BaseModel] = None   # Pydantic model
    ResponseModel: Type[BaseModel] = None  # Pydantic model

    @abstractmethod
    def validate_input(self, **kwargs) -> TRequest:
        """Parse and validate raw kwargs → typed RequestModel."""
        pass

    @abstractmethod
    def execute_internal(self, request: TRequest) -> TResponse:
        """Core logic. Receives validated request, returns typed response."""
        pass

    @abstractmethod
    def format_output(self, response: TResponse) -> Dict[str, Any]:
        """Convert response to LLM-consumable dict with status key."""
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Orchestrates the full lifecycle — mirrors BaseAdapter.fetch().
        Called by the registry via __call__.
        """
        import time, uuid
        start = time.perf_counter()
        request_id = str(uuid.uuid4())[:8]
        try:
            request = self.validate_input(**kwargs)
            response = self.execute_internal(request)
            result = self.format_output(response)
            duration_ms = (time.perf_counter() - start) * 1000
            # Inject ToolResult metadata
            result.setdefault("_metadata", {}).update({
                "duration_ms": round(duration_ms, 2),
                "tool_version": self.version,
                "request_id": request_id,
                "tool_name": self.name,
            })
            return result
        except ValidationError as e:
            return {"status": "error", "error": str(e), "tool": self.name}
        except Exception as e:
            return {"status": "error", "error": str(e), "tool": self.name}

    def __call__(self, **kwargs) -> Dict[str, Any]:
        """Make instances callable — satisfies LocalToolRegistry contract."""
        return self.execute(**kwargs)
```

**Registration pattern:** The new class-based tool is registered as an instance, not a class:
```python
# In orchestrator_service.py (keep manual registration)
_user_context_tool = UserContextTool(context_bridge=_context_bridge)
self.tool_registry.register(_user_context_tool, name="user_context")
```

The existing `registry.register()` accepts any callable (it checks `inspect.signature`). Registering an instance works because `__call__` makes it callable.

**CRITICAL:** The registry's `_extract_schema()` uses `inspect.signature(func)` and `inspect.getdoc(func)`. For class instances, `inspect.signature(instance)` resolves to `__call__`'s signature. The schema extractor needs `__call__` to have proper type-hinted kwargs. Alternatively, provide `name` and `description` overrides to `register()`.

### Pattern 2: CompositeTool with Strategy Pattern

**What:** Multi-action tool that dispatches to ActionStrategy objects.

**Strategy pattern implementation:**
```python
class ActionStrategy(ABC):
    """One action within a CompositeTool."""
    action_name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        pass


class CompositeTool(BaseTool):
    """
    Tool that dispatches to ActionStrategy instances by action name.
    """
    _strategies: Dict[str, ActionStrategy]  # populated in subclass __init__

    def validate_input(self, action: str = "", **kwargs) -> Dict[str, Any]:
        if action not in self._strategies:
            available = list(self._strategies.keys())
            raise ValueError(f"Unknown action '{action}'. Available: {available}")
        return {"action": action, **kwargs}

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        action = request.pop("action")
        strategy = self._strategies[action]
        return strategy.execute(request)

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        # response already has status key from strategy
        return response
```

**Dispatch mechanism recommendation:** Dict lookup (`self._strategies[action]`) over `match/case`. Dict lookup is O(1), works in Python 3.9 (match/case requires 3.10+), and is immediately testable per-strategy.

### Pattern 3: ContextBridge Class (Service Object)

**Current state:** `context_bridge.py` is a module with two free functions: `fetch_context_sync()` and `_normalize_context_for_tools()`. The `_normalize_context_for_tools()` function is a 100-line switch on category name — the OCP violation to fix.

**Target state:**
```python
class ContextBridge:
    def __init__(self, dashboard_url: str, api_key: Optional[str] = None,
                 timeout: int = 10):
        self.dashboard_url = dashboard_url
        self.api_key = api_key
        self.timeout = timeout

    def fetch(self, categories: Optional[List[str]] = None,
              user_id: str = "default") -> Dict[str, Any]:
        """HTTP fetch from dashboard. Returns raw dict."""
        ...

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegates normalization to each adapter's normalize_for_tools().
        Replaces the hardcoded 6-category switch.
        """
        ...
```

**Injection pattern:** `ContextBridge` is instantiated once in `orchestrator_service.py.__init__()` and passed to `UserContextTool.__init__()`. No global module state.

### Pattern 4: normalize_for_tools() on BaseAdapter

**Current OCP violation:** `_normalize_context_for_tools()` in `context_bridge.py` has a hardcoded dict with 6 `if`-blocks, one per category. Adding a new adapter requires editing this function.

**Fix:** Add abstract method to `BaseAdapter`:
```python
# In shared/adapters/base.py
@abstractmethod
def normalize_for_tools(self, raw_category_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform the adapter's raw API response into the format
    expected by the tool layer.
    Replaces the per-category branch in _normalize_context_for_tools().
    """
    pass
```

Each concrete adapter (CIBCAdapter, OpenWeatherAdapter, GoogleCalendarAdapter, ClashRoyaleAdapter) implements its own `normalize_for_tools()`. The `ContextBridge.normalize()` calls `adapter.normalize_for_tools(data)` for each category via the registry — no switch required.

**IMPORTANT:** The current `MockAdapter` in `base.py` is a test helper that must also implement this method (can return raw data as-is).

### Pattern 5: ToolResult Envelope

**Current `ToolResult` in `tools/base.py`:**
```python
@dataclass
class ToolResult:
    status: str
    data: Any = None
    message: str = ""
    # Missing: error, metadata
```

**Target `ToolResult` (mirrors `AdapterResult`):**
```python
@dataclass
class ToolResult:
    status: str            # "success" | "error"
    data: Any = None       # tool-specific payload
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata keys: duration_ms, tool_version, request_id, tool_name
```

The existing `ToolResult.to_dict()` must be updated to include `error` and `metadata`. The `_metadata` key injected by `BaseTool.execute()` should be consistent with this structure.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Input validation | Custom validators | Pydantic `BaseModel` | Already in project; type coercion, error messages for free |
| Schema extraction for LLM | Auto-derive from Pydantic | Hand-maintained JSON schema dicts | Decision #3 locked — Pydantic auto-gen is deferred |
| Strategy dispatch | Reflection/metaclass magic | Plain dict lookup | Simple, debuggable, Python 3.9 compatible |
| Tool callable detection | isinstance checks | Python duck typing — just implement `__call__` | Registry already calls `callable(**kwargs)` |

---

## Critical Findings by Research Question

### Q1: Exact BaseAdapter[T] Pattern

Source: `shared/adapters/base.py` (direct read, HIGH confidence)

- `BaseAdapter(ABC, Generic[T])` uses two abstract methods: `fetch_raw(config: AdapterConfig) -> Dict[str, Any]` and `transform(raw_data: Dict[str, Any]) -> List[T]`
- Public entry point is `fetch(config: Optional[AdapterConfig] = None) -> AdapterResult` — orchestrates both, wraps in try/except, returns `AdapterResult`
- `AdapterResult` is a `@dataclass` with: `success: bool`, `category: str`, `platform: str`, `data: List[Any]`, `fetched_at: datetime`, `error: Optional[str]`, `raw_count: int`, `transformed_count: int`, `metadata: Dict[str, Any]`
- `BaseTool` should mirror: `validate_input()` → `execute_internal()` → `format_output()`, orchestrated by `execute()` returning `ToolResult`
- The adapter also has `get_capabilities() -> Dict[str, bool]` — BaseTool should have `get_schema() -> Dict[str, Any]` for LLM tool-calling schema

### Q2: How LocalToolRegistry Works

Source: `tools/registry.py` (direct read, HIGH confidence)

- `register(func, name=None, description=None)` accepts any callable, stores it in `self.tools[tool_name]`
- Schema extraction: `_extract_schema(f, name, description)` uses `inspect.signature(f)` and `inspect.getdoc(f)` parsing Google-style docstrings
- **CRITICAL:** For class instances with `__call__`, `inspect.signature(instance)` returns signature of `__call__`. The schema extractor will parse the `__call__` docstring. To guarantee correct schema, either: (a) write a proper Google-style docstring on `__call__`, or (b) override schema via the `name`/`description` params plus bypass schema extraction for class-based tools by providing schema directly.
- `call_tool(tool_name, **kwargs)` calls `self.tools[tool_name](**kwargs)` — class instances work if they implement `__call__`
- Circuit breaker is per-tool, wraps every execution

### Q3: How graph.py Invokes Tools

Source: `core/graph.py` `_tools_node` (direct read, HIGH confidence)

- `tool = self.registry.get(tool_name)` returns callable or `None`
- `result = tool(**tool_args)` — called with kwargs from LLM's JSON argument string
- Expects `result.get("status", "success")` to exist
- `result.get("error")` for error message extraction
- **No `ToolResult` dataclass expected** — the graph only cares about the returned `dict`. The `ToolResult.to_dict()` method is what gets returned, but it must have `status` key.
- The graph adds latency tracking itself via `ToolExecutionResult` — the `_metadata` dict injected by `BaseTool.execute()` is additional and does not conflict.

### Q4: AdapterResult Shape

Source: `shared/adapters/base.py` (direct read, HIGH confidence)

```python
@dataclass
class AdapterResult:
    success: bool
    category: str
    platform: str
    data: List[Any]           # List of canonical objects
    fetched_at: datetime      # auto-set
    error: Optional[str]
    raw_count: int
    transformed_count: int
    metadata: Dict[str, Any]
```

Target `ToolResult` mirrors this with tool-appropriate fields:
```python
@dataclass
class ToolResult:
    status: str               # mirrors success (string form)
    data: Any                 # tool payload (not necessarily a list)
    error: Optional[str]
    metadata: Dict[str, Any]  # duration_ms, tool_version, request_id
```

### Q5: How Mock Adapters Are Wired

Source: `shared/adapters/__init__.py` (direct read, HIGH confidence)

**The mock adapter registration chain:**
1. `shared/adapters/__init__.py` imports all 4 mock adapter classes at the top level
2. Each mock class is decorated with `@register_adapter(category="finance", platform="mock", ...)` which calls `adapter_registry.register()` at import time
3. `dashboard_service/aggregator.py`'s `UserConfig` defaults: `finance: ["mock", "cibc"]`, `calendar: ["mock"]`, `health: ["mock"]`, `navigation: ["mock"]`
4. `DashboardAggregator.get_unified_context()` iterates `user_config.get_enabled_platforms(category)` and looks up `registry.get(category, platform)` for each

**What breaks when mock adapters are deleted:**
- `shared/adapters/__init__.py` must be updated — remove the 4 mock import lines and remove from `__all__`
- `dashboard_service/aggregator.py` `UserConfig` defaults must be changed: `calendar: []`, `health: []`, `navigation: []` (finance stays since `cibc` is real)
- The aggregator has a mock fallback path (`health.consecutive_failures >= MOCK_FALLBACK_THRESHOLD and registry.has_adapter(category, "mock")`) — this path will silently do nothing if `has_adapter(category, "mock")` returns False. No crash, just no fallback.
- `context_bridge.py` has `USE_MOCK_CONTEXT` env var check — the `_get_mock_context()` function deletion from `user_context.py` must not break this (the env var check in `context_bridge.py` just returns `{}` in mock mode, which is fine)

### Q6: Tests That Reference Mock Adapters or Mock Context

Source: `grep` across all `.py` files (HIGH confidence — file list found)

Files that reference mock adapters or `_get_mock_context`:
- `tests/conftest.py` — uses mock patterns
- `tests/test_adapter_integration.py` — adapter integration tests
- `tests/unit/test_registry.py` — registry tests
- `dashboard_service/aggregator.py` — mock fallback logic
- `tools/builtin/user_context.py` — inline `_get_mock_context()` (130 lines to delete)
- `tools/builtin/context_bridge.py` — `is_mock_mode()` and `USE_MOCK_CONTEXT` check

**Tests that will need updating when mocks are deleted:**
- Any test that imports `MockFinanceAdapter`, `MockCalendarAdapter`, `MockHealthAdapter`, `MockNavigationAdapter` directly must be updated to use fixture data from `tests/` directory
- The `@register_adapter` decorator at import time means test isolation requires explicit `adapter_registry.clear()` calls in teardown — or the registry's singleton must be reset

### Q7: Dashboard /context Endpoint and normalize_for_tools

Source: `dashboard_service/aggregator.py` (direct read, HIGH confidence)

The dashboard aggregator does NOT call `normalize_for_tools()` — that transformation happens in `context_bridge.py` AFTER the HTTP fetch. The aggregator returns raw canonical objects (list of `FinancialTransaction`, `CalendarEvent`, etc.) serialized via `to_dict()`.

The normalization flow is:
```
Dashboard adapter.fetch() → AdapterResult.data (canonical objects)
  → dashboard /context endpoint returns JSON
  → ContextBridge.fetch() HTTP GET
  → _normalize_context_for_tools() reshapes to tool-friendly format
  → UserContextTool.execute_internal() uses shaped data
```

When `normalize_for_tools()` moves to each adapter, the flow becomes:
```
Dashboard adapter.fetch() → AdapterResult.data
  → dashboard /context endpoint returns JSON
  → ContextBridge.fetch() HTTP GET
  → ContextBridge.normalize() calls adapter.normalize_for_tools() per category
  → UserContextTool.execute_internal()
```

**The dashboard endpoint itself does not change.** Only the tool-side normalization changes.

**Problem:** `ContextBridge` is in the orchestrator container. It cannot call `adapter.normalize_for_tools()` directly because adapter instances live in the dashboard container. `ContextBridge.normalize()` must replicate the per-adapter normalization locally OR each adapter class must be importable in the orchestrator (already possible since `shared/adapters/` is a shared volume). The practical approach: import the adapter class in the orchestrator and call `normalize_for_tools()` as a class method (not requiring an instance).

### Q8: Exact Current Function Signatures (All 27 Tools)

Source: direct code inspection (HIGH confidence)

| Tool Name (registered as) | File | Signature (key params) |
|---------------------------|------|------------------------|
| `web_search` | `web_search.py` | `(query: str, num_results: int = 5) -> Dict` |
| `math_solver` | `math_solver.py` | `(expression: str, show_steps: bool = True) -> Dict` |
| `load_web_page` | `web_loader.py` | `(url: str, extract_links: bool = False, max_chars: int = 8000) -> Dict` |
| `get_user_context` | `user_context.py` | `(categories: List[str] = None, include_alerts: bool = True, destination: str = None) -> Dict` |
| `get_daily_briefing` | `user_context.py` | `() -> Dict` — wrapper for get_user_context(categories=["all"]) |
| `get_commute_time` | `user_context.py` | `(destination: str = None) -> Dict` |
| `search_knowledge` | `knowledge_search.py` | `(query: str, top_k: int = 5) -> Dict` |
| `store_knowledge` | `knowledge_search.py` | `(text: str, metadata: dict = None) -> Dict` |
| `execute_code` | `code_executor.py` | `(code: str, language: str = "python") -> Dict` |
| `query_finance` | `finance_query.py` | `(action: str = "transactions", category: str = None, search: str = None, sort: str = "timestamp", sort_dir: str = "desc", page: int = 1, per_page: int = 10, group_by: str = "category", date_from: str = None, date_to: str = None) -> Dict` |
| `build_module` | `module_builder.py` | `(name: str, category: str, description: str = "", requires_api_key: bool = True, api_url: str = "", auth_type: str = "api_key") -> Dict` |
| `write_module_code` | `module_builder.py` | `(module_id: str, adapter_code: str) -> Dict` |
| `repair_module` | `module_builder.py` | `(module_id: str) -> Dict` |
| `validate_module` | `module_validator.py` | `(module_id: str) -> Dict` |
| `install_module` | `module_installer.py` | `(module_id: str, validation_attestation: Optional[Dict] = None) -> Dict` |
| `uninstall_module` | `module_installer.py` | `(module_id: str) -> Dict` |
| `list_modules` | `module_manager.py` | `() -> Dict` |
| `enable_module` | `module_manager.py` | `(module_id: str) -> Dict` |
| `disable_module` | `module_manager.py` | `(module_id: str) -> Dict` |
| `store_module_credentials` | `module_manager.py` | `(module_id: str, api_key: str = "", credentials_json: str = "") -> Dict` |
| `create_draft` | closure in orchestrator | `(module_id: str) -> dict` |
| `edit_draft` | closure in orchestrator | `(draft_id: str, file_path: str, content: str) -> dict` |
| `diff_draft` | closure in orchestrator | `(draft_id: str) -> dict` |
| `validate_draft` | closure in orchestrator | `(draft_id: str) -> dict` |
| `promote_draft` | closure in orchestrator | `(draft_id: str) -> dict` |
| `list_versions` | closure in orchestrator | `(module_id: str) -> list` |
| `rollback_version` | closure in orchestrator | `(module_id: str, target_version_id: str) -> dict` |

**Total: 27 tools.** The 7 draft/version tools are closures defined inline in `_register_draft_version_tools()` — they capture `_dm` (DraftManager) and `_vm` (VersionManager) via closure. These must move into `ModuleAdminTool`'s action strategies.

---

## Common Pitfalls

### Pitfall 1: inspect.signature on class instances
**What goes wrong:** `LocalToolRegistry._extract_schema()` calls `inspect.signature(f)` where `f` is a callable. For class instances, this works but resolves to `__call__`'s signature including `self` if bound incorrectly.
**Why it happens:** `inspect.signature(instance)` returns the `__call__` signature with `self` already bound — it works correctly. But the docstring parser (`inspect.getdoc(instance)`) returns the class docstring, not `__call__`'s docstring.
**How to avoid:** Override `register()` call with explicit `name` and `description` params for class-based tools. Or implement `__doc__` property on the class that returns the `__call__` docstring. The safest approach: provide `description=tool_instance.description` when calling `registry.register()`.
**Warning signs:** Registry logs "0 parameters" for a tool that should have params.

### Pitfall 2: DraftManager/VersionManager closures
**What goes wrong:** The 7 draft/version tools are closures in `_register_draft_version_tools()` that capture `_dm` and `_vm`. Moving them to `ModuleAdminTool` means the tool class needs injected `DraftManager` and `VersionManager` references.
**Why it happens:** The closures are created after `DraftManager` and `VersionManager` are instantiated (they depend on `MODULES_DIR` and registry). This init order must be preserved in `ModuleAdminTool.__init__()`.
**How to avoid:** `ModuleAdminTool.__init__(module_loader, module_registry, credential_store, draft_manager, version_manager)`. All 5 deps injected at construction.
**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'create_draft'` at runtime.

### Pitfall 3: Singleton AdapterRegistry and mock cleanup
**What goes wrong:** `AdapterRegistry` is a singleton (`_instance` class var). Tests that import mock adapters register them into the singleton. Deleting mock files stops them from being registered, but test conftest may still try to import them.
**Why it happens:** `shared/adapters/__init__.py` imports all mocks at module load. If a test file does `from shared.adapters import MockFinanceAdapter`, it will fail with ImportError after deletion.
**How to avoid:** Search all test files for direct mock adapter imports before deleting. Replace with inline `MockAdapter(BaseAdapter)` fixtures local to each test file.
**Warning signs:** `ImportError: cannot import name 'MockFinanceAdapter'` in test runs.

### Pitfall 4: BaseAdapter.normalize_for_tools() adds abstract method
**What goes wrong:** Making `normalize_for_tools()` abstract on `BaseAdapter` immediately breaks ALL existing concrete adapters (CIBCAdapter, OpenWeatherAdapter, GoogleCalendarAdapter, ClashRoyaleAdapter, ClashRoyaleAdapter, plus any dynamic modules) because they don't implement it.
**Why it happens:** Python's ABC enforcement raises `TypeError: Can't instantiate abstract class ... with abstract method normalize_for_tools` at instantiation.
**How to avoid:** Add as non-abstract with a default `return {}` implementation first. Let concrete adapters override it. Mark it "encouraged to override" in the docstring. Make abstract only after all adapters implement it.
**Warning signs:** `DashboardAggregator` fails to instantiate adapters at startup.

### Pitfall 5: Finance query pagination params in UserContextTool
**What goes wrong:** `query_finance()` has 9 parameters including `sort`, `sort_dir`, `page`, `per_page`, `group_by`, `date_from`, `date_to`. The LLM must pass all of these as `user_context(category="finance", action="query", sort="amount", ...)`. The `UserContextTool.RequestModel` must have all these as optional fields.
**Why it happens:** `finance_query.py` currently has a dedicated function — straightforward. Absorbing into UserContextTool means the single `RequestModel` has fields for ALL categories including finance pagination. The LLM JSON schema for `user_context` becomes large.
**How to avoid:** Use nested finance-specific params: `user_context(category="finance", action="query", finance_params={"sort": "amount", "per_page": 5})`. Or flatten with `**kwargs` pass-through. Decision: keep flat params, mark finance-specific params clearly in the JSON schema description.
**Warning signs:** LLM cannot discover finance pagination params from tool description.

### Pitfall 6: USE_MOCK_CONTEXT env var after mock deletion
**What goes wrong:** `context_bridge.py` has `if os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true": return {}`. After deleting `_get_mock_context()` from `user_context.py`, the env var check in the new `ContextBridge` class must still be respected (returns empty dict, not crash).
**Why it happens:** The env var was used to bypass HTTP when developing locally. The ContextBridge class replaces the module function.
**How to avoid:** Keep `USE_MOCK_CONTEXT` check in `ContextBridge.fetch()` — if set, return `{}` immediately without HTTP. Document this as a dev-only escape hatch (not production mock data).

### Pitfall 7: Module builder global state (set_* functions)
**What goes wrong:** `module_builder.py` uses global `_llm_gateway`, set by `set_llm_gateway()`. `module_validator.py` uses global `_sandbox_client`, set by `set_sandbox_client()`. `module_manager.py` uses three globals. When these become `ModulePipelineTool` and `ModuleAdminTool`, the set_* functions disappear.
**Why it happens:** The current architecture uses module-level singletons as a dependency injection substitute. The wiring happens in `orchestrator_service.py`.
**How to avoid:** Pass all dependencies into tool constructors. `ModulePipelineTool.__init__(llm_gateway, sandbox_client, modules_dir, audit_dir)`. Remove all `set_*` functions. Update orchestrator wiring.
**Warning signs:** `AttributeError: 'NoneType' has no attribute 'generate'` on first build attempt.

---

## Code Examples

### BaseTool ABC (verified against BaseAdapter pattern)

```python
# tools/base.py (extend existing file)
# Source: direct inspection of shared/adapters/base.py + tools/base.py

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Dict, Any, Optional, Type
from dataclasses import dataclass, field
from pydantic import BaseModel

TRequest = TypeVar('TRequest', bound=BaseModel)
TResponse = TypeVar('TResponse', bound=BaseModel)


@dataclass
class ToolResult:
    """Standardized return type. Mirrors AdapterResult."""
    status: str                                      # "success" | "error"
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        if self.metadata:
            result["_metadata"] = self.metadata
        return result


class BaseTool(ABC, Generic[TRequest, TResponse]):
    """
    Abstract base for all tools. Mirrors BaseAdapter[T] lifecycle.

    Lifecycle: validate_input() → execute_internal() → format_output()
    Orchestrated by execute() which returns Dict[str, Any] with status key.
    """
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    RequestModel: Optional[Type[BaseModel]] = None
    ResponseModel: Optional[Type[BaseModel]] = None

    @abstractmethod
    def validate_input(self, **kwargs) -> TRequest:
        pass

    @abstractmethod
    def execute_internal(self, request: TRequest) -> TResponse:
        pass

    @abstractmethod
    def format_output(self, response: TResponse) -> Dict[str, Any]:
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        import time, uuid
        start = time.perf_counter()
        rid = str(uuid.uuid4())[:8]
        try:
            req = self.validate_input(**kwargs)
            resp = self.execute_internal(req)
            result = self.format_output(resp)
            result.setdefault("_metadata", {}).update({
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "tool_version": self.version,
                "request_id": rid,
            })
            return result
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "_metadata": {"tool_name": self.name, "request_id": rid},
            }

    def __call__(self, **kwargs) -> Dict[str, Any]:
        """Satisfies LocalToolRegistry callable contract."""
        return self.execute(**kwargs)
```

### CompositeTool with Strategy (dict dispatch)

```python
# tools/base.py (same file, continued)

class ActionStrategy(ABC):
    action_name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        pass


class CompositeTool(BaseTool):
    """
    Multi-action tool using Strategy pattern.
    Subclasses populate self._strategies in __init__.
    """

    def __init__(self):
        self._strategies: Dict[str, ActionStrategy] = {}

    def _register_strategy(self, strategy: ActionStrategy) -> None:
        self._strategies[strategy.action_name] = strategy

    def validate_input(self, action: str = "", **kwargs) -> Dict[str, Any]:
        if not action:
            raise ValueError(f"'action' required. Available: {list(self._strategies)}")
        if action not in self._strategies:
            raise ValueError(f"Unknown action '{action}'. Available: {list(self._strategies)}")
        return {"action": action, **kwargs}

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        action = request.pop("action")
        return self._strategies[action].execute(**request)

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response  # strategies return complete result dicts
```

### ContextBridge class

```python
# tools/builtin/context_bridge.py (replace module functions)

import os, logging
from typing import Dict, Any, Optional, List
import requests

logger = logging.getLogger(__name__)


class ContextBridge:
    """Service object. Sole data source for context tools."""

    def __init__(
        self,
        dashboard_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 10,
    ):
        self.dashboard_url = dashboard_url or os.getenv(
            "DASHBOARD_URL", "http://dashboard:8001"
        )
        self.api_key = api_key or os.getenv("DASHBOARD_API_KEY") or os.getenv(
            "INTERNAL_API_KEY"
        )
        self.timeout = timeout

    @property
    def _headers(self) -> Optional[Dict[str, str]]:
        return {"X-API-Key": self.api_key} if self.api_key else None

    def fetch(
        self,
        categories: Optional[List[str]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Fetch context from dashboard. Returns empty dict on failure."""
        if os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true":
            return {}
        # ... HTTP fetch logic (migrate from existing fetch_context_sync)
        ...

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegate normalization to adapter normalize_for_tools() methods.
        This replaces _normalize_context_for_tools().
        """
        # Import adapter classes to call normalize_for_tools()
        # Each adapter's method knows its own data shape
        ...
```

### UserContextTool (consolidates 4 tools)

```python
# tools/builtin/user_context.py

from pydantic import BaseModel
from typing import Optional, List
from tools.base import BaseTool

class UserContextRequest(BaseModel):
    category: str = "all"
    action: str = "summary"       # "summary" | "query" (finance only)
    destination: Optional[str] = None
    include_alerts: bool = True
    # Finance query params (used when category="finance", action="query")
    finance_action: Optional[str] = None  # transactions|summary|categories|search
    search: Optional[str] = None
    sort: str = "timestamp"
    sort_dir: str = "desc"
    page: int = 1
    per_page: int = 10
    group_by: str = "category"
    date_from: Optional[str] = None
    date_to: Optional[str] = None

class UserContextTool(BaseTool[UserContextRequest, Dict]):
    name = "user_context"
    description = (
        "Get user's personal context: calendar, finance, health, navigation, "
        "weather, gaming. For finance queries use action='query'."
    )
    RequestModel = UserContextRequest

    def __init__(self, context_bridge: 'ContextBridge'):
        self._bridge = context_bridge

    def validate_input(self, **kwargs) -> UserContextRequest:
        return UserContextRequest(**kwargs)

    def execute_internal(self, request: UserContextRequest) -> Dict:
        # Route to appropriate handler
        if request.category == "finance" and request.action == "query":
            return self._handle_finance_query(request)
        return self._handle_context_summary(request)

    def format_output(self, response: Dict) -> Dict:
        return {"status": "success", **response}
```

### Registration in orchestrator (incremental migration example)

```python
# orchestrator/orchestrator_service.py — updated registration block

# 1. Create ContextBridge once
_context_bridge = ContextBridge(
    dashboard_url=os.getenv("DASHBOARD_URL", "http://dashboard:8001")
)

# 2. Create tool instances
_user_context_tool = UserContextTool(context_bridge=_context_bridge)
_web_tool = WebTool()
_knowledge_search_tool = KnowledgeSearchTool()
_knowledge_store_tool = KnowledgeStoreTool()
_math_tool = MathSolverTool()
_code_executor_tool = CodeExecutorTool(sandbox_client=self.sandbox_client)
_module_pipeline_tool = ModulePipelineTool(
    llm_gateway=self.llm_gateway,
    sandbox_client=self.sandbox_client,
    modules_dir=MODULES_DIR,
)
_module_admin_tool = ModuleAdminTool(
    module_loader=self.module_loader,
    module_registry=self.module_registry,
    credential_store=self.credential_store,
    draft_manager=_dm,
    version_manager=_vm,
)

# 3. Register instances with explicit names and descriptions
self.tool_registry.register(_user_context_tool, name="user_context",
    description=_user_context_tool.description)
self.tool_registry.register(_web_tool, name="web", description=_web_tool.description)
self.tool_registry.register(_module_pipeline_tool, name="module_pipeline",
    description=_module_pipeline_tool.description)
self.tool_registry.register(_module_admin_tool, name="module_admin",
    description=_module_admin_tool.description)
# ... etc.
```

---

## Migration Strategy (Claude's Discretion)

**Recommendation: Incremental with named-wrapper shim**

The incremental approach is strongly preferred over big-bang for this codebase. The key risk with big-bang is that 27 tool names change simultaneously, breaking any live conversation state and LLM prompt caches.

**Recommended order:**
1. Extend `tools/base.py` with `BaseTool`, `CompositeTool`, `ActionStrategy`, and new `ToolResult`
2. Delete dead code (no dependencies: `destinations.py`, `feature_test_harness.py`, `chart_validator.py`)
3. Refactor `context_bridge.py` to `ContextBridge` class (wire into new `user_context.py`)
4. Build `UserContextTool` (absorbs `get_user_context`, `get_daily_briefing`, `get_commute_time`, `finance_query`)
5. Build `WebTool` (absorbs `web_search`, `web_loader`)
6. Build `KnowledgeSearchTool`, `KnowledgeStoreTool`, `MathSolverTool`, `CodeExecutorTool`
7. Build `ModulePipelineTool` (absorbs `module_builder`, `module_validator`, `module_installer`)
8. Build `ModuleAdminTool` (absorbs `module_manager`, draft/version closures)
9. Update `shared/adapters/base.py` — add `normalize_for_tools()` with default `return {}`
10. Implement `normalize_for_tools()` on each concrete adapter
11. Update `ContextBridge.normalize()` to call adapter methods
12. Delete mock adapter files + update `shared/adapters/__init__.py` + fix `UserConfig` defaults
13. Update `orchestrator_service.py` tool registration block
14. Update `intent_patterns.py` tool name references if any

**On tool name change:** The LLM learns tool names from the `to_openai_tools()` schema. If `get_user_context` becomes `user_context`, any conversation state in SQLite checkpoints with old tool names will produce "tool not found" errors on the next message. **Mitigation:** Register the new tool instance ALSO under old names as aliases:
```python
# Backward compat aliases during migration (remove after testing)
self.tool_registry.register(_user_context_tool, name="get_user_context",
    description=_user_context_tool.description)
self.tool_registry.register(_user_context_tool, name="get_daily_briefing",
    description="Get a complete daily briefing.")
```

---

## Open Questions

1. **normalize_for_tools() import in ContextBridge**
   - What we know: ContextBridge is in the orchestrator container; adapters are in `shared/adapters/` (mounted in both containers)
   - What's unclear: Does calling adapter class methods from ContextBridge create undesired coupling to the dashboard layer?
   - Recommendation: Import only adapter classes (not instances) in ContextBridge. Call `normalize_for_tools()` as a classmethod or static method. This keeps the orchestrator independent of adapter instances.

2. **graph.py intent keywords for new tool names**
   - What we know: `graph.py._should_use_tools()` has keyword lists for tool activation. `intent_patterns.py` also has tool-name references.
   - What's unclear: `_should_use_tools()` uses string keywords, not tool names, so renaming tools doesn't break it. But `_is_module_build_session()` checks `state.get("tool_results")` for specific tool names like `build_module`, `write_module_code` — these must be updated to `module_pipeline`.
   - Recommendation: Update `_is_module_build_session()` to check for `module_pipeline` action name.

3. **UserConfig mock default removal**
   - What we know: `DashboardAggregator.UserConfig` defaults include `calendar: ["mock"]`, `health: ["mock"]`, `navigation: ["mock"]`
   - What's unclear: Is `UserConfig` instantiated from config file or purely hardcoded defaults?
   - Recommendation: Check `dashboard_service/main.py` for `UserConfig` instantiation. If hardcoded, change defaults. If from config file, update config file.

---

## Sources

### Primary (HIGH confidence — direct codebase inspection)
- `shared/adapters/base.py` — BaseAdapter[T], AdapterResult, AdapterConfig shapes
- `shared/adapters/registry.py` — AdapterRegistry, @register_adapter decorator
- `shared/adapters/__init__.py` — mock adapter import chain and @register_adapter trigger
- `tools/registry.py` — LocalToolRegistry, schema extraction, callable contract
- `tools/base.py` — existing ToolResult, BaseTool (minimal), circuit breaker
- `core/graph.py` — _tools_node, tool(**kwargs) call contract, result.get("status")
- `tools/builtin/context_bridge.py` — full fetch + normalize logic (100-line OCP violation)
- `tools/builtin/user_context.py` — all 3 context functions + 130-line _get_mock_context()
- `tools/builtin/finance_query.py` — query_finance() with all 9 params + 4 actions
- `tools/builtin/module_builder.py` — build/write/repair functions + global state pattern
- `tools/builtin/module_manager.py` — list/enable/disable/credentials + set_* injectors
- `tools/builtin/module_installer.py` — install/uninstall + security checks
- `orchestrator/orchestrator_service.py` lines 944-1147 — complete tool registration block
- `dashboard_service/aggregator.py` — UserConfig defaults + mock fallback chain
- `shared/adapters/finance/mock.py` — mock registration pattern to replicate in reverse
- `tools/builtin/destinations.py`, `feature_test_harness.py` — confirmed no registered tools

### Secondary (MEDIUM confidence)
- `tests/unit/test_builtin_tools.py` — test patterns for function-based tools
- `tests/unit/test_finance_query.py` — confirms test isolation uses `patch` not mock adapters

---

## Metadata

**Confidence breakdown:**
- BaseAdapter pattern to mirror: HIGH — read directly from source
- LocalToolRegistry contract: HIGH — read directly, callable(**kwargs) verified
- graph.py tool invocation contract: HIGH — _tools_node read directly
- Mock adapter deletion impact: HIGH — import chain traced end-to-end
- 27-tool function signatures: HIGH — read from source files directly
- Draft/version tool closure pattern: HIGH — read from orchestrator lines 1100-1147
- normalize_for_tools() design: MEDIUM — pattern is clear but adapter import boundary is an open question

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable internal codebase — no external APIs involved)
