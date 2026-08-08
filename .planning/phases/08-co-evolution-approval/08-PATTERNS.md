# Phase 8: Co-Evolution & Approval - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 24
**Analogs found:** 21 / 24

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `orchestrator/admin_api.py` (approve/reject endpoints) | controller (FastAPI route) | request-response | `orchestrator/admin_api.py::promote_draft`/`validate_draft` (lines 1457-1502) | exact |
| `tools/builtin/module_installer.py` (status guard change) | middleware (attestation guard) | request-response | same file, lines 88-106 (existing `VALIDATED` guard) | exact |
| `orchestrator/retention_worker.py` (NEW — GC + retention worker) | service (background worker) | batch | `dashboard_service/pipeline_stream.py::pipeline_event_generator` (async while-True + sleep loop) | role-match |
| `shared/modules/policy.py` (NEW — ApprovalPolicy) | config | CRUD | `orchestrator/routing_config.py` (Pydantic config models) | role-match |
| `shared/auth/rate_limit_middleware.py` (NEW) | middleware | request-response | `shared/auth/middleware.py::APIKeyAuthMiddleware` | exact |
| `shared/billing/usage_store.py` (extend — `delete_before()`) | model/store | CRUD | same file, `record()`/`get_period_total()` (lines 59-115) | exact |
| `tools/builtin/module_admin.py` (add Approve/Reject strategies) | controller (tool strategy) | request-response | same file, `PromoteDraftStrategy`/`ValidateDraftStrategy` (lines 194-218) | exact |
| `tools/builtin/module_builder.py` (walkthrough hook) | service | event-driven | `tools/builtin/module_builder.py::repair_module` LLM gateway call (lines 570-580) | role-match |
| `tools/builtin/module_validator.py` (walkthrough hook alt. site) | service | event-driven | same file, `validate_module()` finalize block (lines 243-266) | exact |
| `dashboard_service/pipeline_stream.py` (extend `_build_pipeline_state`) | service (SSE producer) | streaming | same file, `_build_pipeline_state()`/`_build_adapter_list()` (lines 78-179) | exact |
| `ui_service/src/machines/pipelinePageMachine.ts` (NEW) | provider (XState machine) | event-driven | `ui_service/src/machines/monitoringPage.ts` | role-match (parallel-region pattern; needs `fromCallback` not `fromPromise`) |
| `ui_service/src/components/pipeline/NodeDetailPanel.tsx` (extend, 5 accordion sections) | component | request-response | same file (existing Status/Auth/Test Runner sections) | exact |
| `ui_service/src/components/pipeline/BlueprintCard.tsx` (NEW) | component | request-response | `ui_service/src/components/pipeline/StageNode.tsx` (dashed-border technical aesthetic) | role-match |
| `ui_service/src/components/pipeline/ModuleNode.tsx` (extend — pendingApproval badge) | component | request-response | same file (existing `stateStyles` map pattern) | exact |
| `ui_service/src/components/chat/ApprovalActionCard.tsx` (NEW) | component | request-response | `ui_service/src/components/chat/ActionCard.tsx` | exact |
| `ui_service/src/components/pipeline/ModulePanel.tsx` (NEW — generic output panel, D-07) | component | transform | `ui_service/src/components/pipeline/NodeDetailPanel.tsx` (Status key/value row pattern) + `shared/modules/output_contract.py::AdapterRunResult` | role-match |
| `ui_service/src/lib/adminClient.ts` (extend — approve/reject/audit fetchers) | utility (typed fetch client) | request-response | same file, `adminApi.enableModule`/`disableModule` (lines 206-219) | exact |
| `ui_service/src/store/nexusStore.ts` (extend or wrap) | store (Zustand) | event-driven | same file (existing `startSSE`/`enableModule` actions) | exact |
| `tests/unit/modules/test_installer_approval_guard.py` (NEW) | test | CRUD | `tests/unit/modules/test_rollback_pointer.py` | role-match |
| `tests/integration/admin/test_approval_gate.py` (NEW) | test | request-response | `tests/integration/admin/test_module_crud.py` + `conftest.py` | exact |
| `tests/integration/admin/test_reject_gc.py` (NEW) | test | file-I/O | `tests/integration/admin/test_module_crud.py` (fixtures) + `tests/unit/modules/test_rollback_pointer.py` (VersionManager tmp_path pattern) | role-match |
| `tests/unit/test_retention_worker.py` + `tests/unit/test_gc_reference_safety.py` (NEW) | test | batch | `tests/unit/modules/test_rollback_pointer.py` (tmp_path SQLite isolation) | role-match |
| `tests/integration/admin/test_inbound_rate_limit.py` (NEW) | test | request-response | `tests/integration/admin/test_module_crud.py` (RBAC pattern) — NOT `tests/feature/test_rate_limit_429.py` (outbound, unrelated — see Pitfall 1) | role-match |
| `ui_service/e2e/pipeline-sse-reconnect.spec.ts` + `playwright.config.ts` (NEW) | test (E2E) | streaming | none — greenfield, no Playwright infra exists | no analog |

## Pattern Assignments

### `orchestrator/admin_api.py` — approve/reject endpoints (controller, request-response)

**Analog:** `orchestrator/admin_api.py::promote_draft` / `validate_draft` (same file, lines 1457-1502)

**Imports already present at top of file** (lines 9-28, no new imports needed except `ModuleManifest`/`ModuleStatus`):
```python
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from shared.auth.models import User
from shared.auth.rbac import Permission, get_current_user, require_permission
```
Add: `from shared.modules.manifest import ModuleManifest, ModuleStatus` and `from pathlib import Path`.

**RBAC pattern** (copy verbatim shape, admin+ = `Permission.ADMIN_ALL`, lines 1457-1461):
```python
@_app.post("/admin/modules/drafts/{draft_id}/validate")
def validate_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),
):
    """
    Trigger sandbox validation for a draft.

    RBAC: admin+ role required.
    """
```

**Core request-response pattern** (lines 1481-1502, `promote_draft` — mirror this exactly for `approve_module`/`reject_module`, swapping `_draft_manager.promote_draft(...)` for direct `ModuleManifest.load()`/`.save()` mutation per Path A):
```python
@_app.post("/admin/modules/drafts/{draft_id}/promote")
def promote_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),
):
    """
    Promote a validated draft to a new version.

    RBAC: admin+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.promote_draft(
        draft_id=draft_id,
        actor=user.org_id
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result
```

**Error handling pattern:** `if result.get("status") == "error": raise HTTPException(400, result.get("error", "Unknown error"))` — every draft endpoint in this file follows this exact shape (see lines 1451-1454, 1475-1478, 1499-1502, 1523-1526, 1550-1553). Reuse verbatim for approve/reject.

**D-19 audit logging — IMPORTANT correction to RESEARCH.md Pattern 2:** there is **no** standalone `_dev_mode_audit_log` module-level variable in `admin_api.py`. The single `DevModeAuditLog` instance is constructed once in `orchestrator/orchestrator_service.py` (lines 979, 1816) and passed into both `DraftManager` and `VersionManager` as `audit_log=`. It is accessible from admin_api.py as `_draft_manager.audit_log` (or `_version_manager.audit_log` — same instance). Use that reference, not a new global:
```python
# Source: shared/modules/drafts.py lines 179-190 (DraftManager.create_draft, existing call site)
if self.audit_log:
    self.audit_log.log_action(
        action="draft_created",
        actor=actor,
        module_id=module_id,
        draft_id=draft_id,
        details={"source_version": from_version, "files_copied": list(files_copied.keys())}
    )
```
For approve/reject: `_draft_manager.audit_log.log_action(action="module_approved", actor=user.org_id, module_id=module_id, details={"bundle_sha256": ...})`.

**RBAC dependency shape reference — `shared/auth/rbac.py`:** `Permission.ADMIN_ALL` used by `validate_draft`/`promote_draft`/`rollback_module`; `Permission.MANAGE_MODULES` used by lower-privilege module ops (enable/disable/discard_draft). Approve/reject must use `Permission.ADMIN_ALL` per D-17.

---

### `tools/builtin/module_installer.py` — status guard change (middleware/enforcement, request-response)

**Analog:** same file, existing guard (lines 88-106) — this is a **1-line value change**, not a new pattern.

**Exact current code to modify** (lines 96-106):
```python
if manifest.status != ModuleStatus.VALIDATED and manifest.status != ModuleStatus.VALIDATED.value:
    _log_install_rejection(
        module_id, "not_validated", f"Status: {manifest.status}"
    )
    return {
        "status": "error",
        "error": (
            f"Module {module_id} has not been validated (status: {manifest.status}). "
            f"Call validate_module('{module_id}') first."
        ),
    }
```
Change comparison target from `ModuleStatus.VALIDATED` to `ModuleStatus.APPROVED` (D-16). `ModuleStatus.APPROVED` already exists in `shared/modules/manifest.py` line 21 — no schema change required. `_log_install_rejection` helper (already defined in this file) should be reused unmodified for the new rejection reason `"not_approved"`.

---

### `orchestrator/retention_worker.py` (NEW) — GC + retention worker (service, batch)

**Analog:** `dashboard_service/pipeline_stream.py::pipeline_event_generator` (lines 181-190) — closest existing async-loop shape in the codebase. No scheduling library (APScheduler etc.) exists anywhere in `requirements.txt`.

**Loop shape to copy:**
```python
# Source: dashboard_service/pipeline_stream.py lines 181-190
async def pipeline_event_generator(app) -> AsyncGenerator[str, None]:
    """Yield SSE events with pipeline state updates."""
    while True:
        try:
            state = await _build_pipeline_state(app)
            yield f"data: {json.dumps(state)}\n\n"
        except Exception as e:
            logger.warning(f"SSE state build error: {e}")
            yield f"data: {json.dumps({'error': str(e), 'timestamp': time.time()})}\n\n"
        await asyncio.sleep(2)  # 2-second update interval
```
Adapt to: `while True: try: run_artifact_gc(); prune_expired_usage(...); except Exception as e: logger.warning(...); await asyncio.sleep(interval_seconds)` — no `yield`, this is a fire-and-forget background task, not a generator.

**Startup wiring analog:** neither `orchestrator/orchestrator_service.py` nor `dashboard_service/main.py` currently has an `asyncio.create_task()` background-task pattern at startup — this is genuinely greenfield wiring. The closest existing precedent for "service constructs a stateful object at startup and stores it on shared state" is `dashboard_service/main.py` lines 301-313 (`ModuleLoader` construction + `app.state.module_loader = module_loader`). Follow that same "construct once, store as module/app state" shape, then call `asyncio.create_task(gc_and_retention_worker())` in the equivalent startup hook (`orchestrator_service.py`'s `serve()` — grep for where `start_admin_server(...)` is called, since GC worker should start alongside it).

**Reference-safety check (D-12) — use existing `VersionManager` query surface, do not build new tracking:**
```python
# Source: shared/modules/versioning.py — VersionManager methods already exist
# get_active_version(module_id) -> ModuleVersion | None (lines 253+)
# list_versions(module_id) -> list[ModuleVersion] (lines 205+)
```
Per Pitfall 5 (RESEARCH.md): Path A modules (`build_module()` → `install_module()`) never call `record_version()`, so a rejected Path A module usually has **no** version row at all — safe to delete unconditionally. Only check `active_versions` when a version row exists for the bundle hash being deleted.

---

### `shared/modules/policy.py` (NEW) — ApprovalPolicy config scaffold (config, CRUD)

**Analog:** `orchestrator/routing_config.py` — Pydantic config model pattern already established in this codebase (`RoutingConfig`, `CategoryRouting`, `TierConfig`, `PerformanceConstraints`).

**IMPORTANT project-specific gotcha (from MEMORY.md):** do NOT use `from __future__ import annotations` with Pydantic models in this codebase — it causes deferred-eval errors (documented Phase 2 pitfall). `routing_config.py` avoids this; new `policy.py` must too.

**Tier-cutoff convention to mirror** (`shared/billing/quota_manager.py` lines 16-20):
```python
TIER_QUOTAS = {
    "free": 100.0,
    "team": 5000.0,
    "enterprise": -1.0,
}
```
Mirror this exact shape for `TIER_RETENTION_DAYS = {"free": 7, "team": 90, "enterprise": -1}` (unlimited = `-1` sentinel, same convention).

`ApprovalPolicy` scaffold per D-18: a Pydantic `BaseModel` with `auto_approve: bool = False` as hard default field — follow `RoutingConfig`'s field-with-default style, not a dataclass (this codebase uses Pydantic for hot-reloadable config, dataclasses for manifest/audit records — `ModuleManifest`/`AttemptRecord` are `@dataclass`, `RoutingConfig`/`CategoryRouting` are Pydantic `BaseModel`; policy.py should follow the Pydantic convention since it's config, not a record).

---

### `shared/auth/rate_limit_middleware.py` (NEW) — inbound rate limiting (middleware, request-response)

**Analog:** `shared/auth/middleware.py::APIKeyAuthMiddleware` (full file, 97 lines) — this is the canonical `BaseHTTPMiddleware` shape used by both target FastAPI apps today.

**Full pattern to mirror (imports + class shape + dispatch + factory function):**
```python
# Source: shared/auth/middleware.py, lines 1-77 (full)
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .api_keys import APIKeyStore

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_PATHS = [
    "/health", "/admin/health", "/docs", "/openapi.json", "/redoc", "/metrics",
]

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key_store: APIKeyStore, public_paths: Optional[list[str]] = None):
        super().__init__(app)
        self.api_key_store = api_key_store
        self.public_paths = public_paths or DEFAULT_PUBLIC_PATHS

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        for public in self.public_paths:
            if path == public or path.startswith(public + "/"):
                return await call_next(request)
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return JSONResponse(status_code=401, content={"detail": "Missing API key"})
        user = self.api_key_store.validate_key(api_key)
        if user is None:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        request.state.user = user
        request.state.org_id = user.org_id
        return await call_next(request)
```
Model `RateLimitMiddleware` on this exact shape: same `__init__(self, app, ...)` + `super().__init__(app)`, same OPTIONS-skip-first pattern, same `JSONResponse(status_code=..., content={...})` error-return style. Per Pitfall 3 (RESEARCH.md), read `X-API-Key` directly from `request.headers` rather than depending on `request.state.user` (avoids Starlette's reverse middleware-order gotcha).

**Rate limiter primitive to wrap (do not reimplement):** `shared/utils/rate_limiter.py::TokenBucketRateLimiter` / `RateLimiterRegistry` (full file read, 318 lines) — `get_rate_limiter_registry().get(key)` then `await limiter.acquire()` / `limiter.retry_after()`. Already thread-safe + async-capable + has `retry_after()` built in.

**Wiring analog:** `shared/auth/middleware.py::create_auth_middleware()` (lines 80-96) shows the factory-function wiring pattern (`app.add_middleware(...)` + return store) — use as template for a `create_rate_limit_middleware(app, ...)` helper if one is desired, though direct `app.add_middleware(RateLimitMiddleware, ...)` calls in `dashboard_service/main.py` and `orchestrator/admin_api.py::start_admin_server()` are equally consistent with how `APIKeyAuthMiddleware` is actually wired in `admin_api.py` (lines 1745-1756, direct `_app.add_middleware(...)` call, not via the factory).

---

### `dashboard_service/pipeline_stream.py` — extend `_build_pipeline_state()` (SSE producer, streaming)

**Analog:** same file, `_build_adapter_list()` / `_build_tool_list()` helper-function pattern (lines 78-118) — small pure functions that transform a data source into an SSE-ready list, called from `_build_pipeline_state()`.

**Exact current module list construction to extend** (lines 146-159):
```python
# Query data sources ONCE per cycle
loader = getattr(app.state, "module_loader", None)
module_list = loader.list_modules() if loader else []
all_adapters = adapter_registry.list_all_flat()

# Build module entries
modules = []
for m in module_list:
    modules.append({
        "id": f"{m.get('category', '?')}/{m.get('platform', '?')}",
        "name": m.get("name", "unknown"),
        "state": "running" if m.get("is_loaded") else "disabled",
        "category": m.get("category"),
    })
```
This only sources from `loader.list_modules()` (loaded modules). Add a new helper `_build_pending_approval_list(modules_dir)` following the exact same "small pure function, called once per cycle" style as `_build_adapter_list`, using `ModuleManifest.discover(modules_dir)` (classmethod already exists, `shared/modules/manifest.py` lines 132-140) to scan for `VALIDATED`/`APPROVED`/`VALIDATING` manifests not yet loaded, then merge into the `modules` list before returning from `_build_pipeline_state()`.

**Return dict shape to extend** (lines 170-178) — add `pending_approval` / `build_stage` keys per-module, keep the same flat dict-of-lists envelope shape:
```python
return {
    "services": services,
    "modules": modules,
    "adapters": adapters,
    "adapters_count": len(adapters),
    "tools": tools,
    "stage_tools": stage_tools,
    "timestamp": time.time(),
}
```

---

### `tools/builtin/module_admin.py` — Approve/Reject strategies (controller/tool-strategy, request-response)

**Analog:** same file, `PromoteDraftStrategy` / `ValidateDraftStrategy` (lines 194-218).

**Exact pattern to copy (constructor + execute + `action_name` class attr):**
```python
# Source: tools/builtin/module_admin.py lines 207-218
class PromoteDraftStrategy(ActionStrategy):
    action_name = "promote_draft"
    description = "Promote a validated draft to a new module version"

    def __init__(self, draft_manager=None):
        self._dm = draft_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._dm:
            return {"status": "error", "error": "Draft manager not available"}
        return self._dm.promote_draft(draft_id=kwargs.get("draft_id"), actor="chat_agent")
```
New `ApproveModuleStrategy`/`RejectModuleStrategy` follow this exact shape — `action_name = "approve_module"` / `"reject_module"`, constructor takes whatever dependency exposes the manifest mutation (likely a thin wrapper calling the same logic as the new admin_api.py endpoints, or importing `tools.builtin.module_installer`-adjacent helpers directly), `execute(**kwargs)` returns the same `{"status": ..., ...}` dict shape used everywhere in this file.

**Registration site** (constructor, lines 265-286) — new strategies register via `self._register_strategy(...)` alongside existing ones:
```python
self._register_strategy(ValidateDraftStrategy(draft_manager))
self._register_strategy(PromoteDraftStrategy(draft_manager))
```

**Chat RBAC note (D-17):** `ModuleAdminTool` strategies today hardcode `actor="chat_agent"` (not the session's actual role) — RESEARCH.md's architecture diagram states chat approval "enforces the same RBAC via the session's API key role." The strategy execute() path will need the calling session's `User`/role threaded through (not just a hardcoded actor string) to satisfy D-17 for the chat path — flag this as a wiring gap the planner must address explicitly, current strategies do not have a role-check precedent to copy from.

---

### `tools/builtin/module_validator.py` — LLM walkthrough hook (D-08) (service, event-driven)

**Analog:** same file, `validate_module()` finalize block (lines 243-266) — this is the exact point where `manifest.status = ModuleStatus.VALIDATED` is set and `manifest.save(MODULES_DIR)` is called; walkthrough generation must happen here, once, before save.

**Hook site (existing code, lines 249-265):**
```python
# Update manifest
if manifest_file.exists():
    manifest = ModuleManifest.load(manifest_file)
    # Update old ValidationResults for backwards compatibility
    legacy_results = ValidationResults()
    legacy_results.syntax_check = "pass" if syntax_check.passed else "fail"
    if report.runtime_results:
        legacy_results.unit_tests = (
            "pass" if report.runtime_results.tests_failed == 0 else "fail"
        )
    legacy_results.validated_at = report.validated_at
    if report.status == "FAILED":
        legacy_results.error_details = "\n".join([h.message for h in report.fix_hints])

    manifest.validation_results = legacy_results
    manifest.status = ModuleStatus.VALIDATED if report.status == "VALIDATED" else ModuleStatus.FAILED
    manifest.save(MODULES_DIR)
```
Insert walkthrough generation right before `manifest.save(MODULES_DIR)`, gated on `report.status == "VALIDATED"` only (no walkthrough for failed builds).

**LLM Gateway call pattern to copy** (`tools/builtin/module_builder.py` lines 570-580, `repair_module`'s `Purpose.REPAIR` call — same call shape, different `purpose`):
```python
contract, gen_metadata = _run_async(
    _llm_gateway.generate(
        purpose=Purpose.REPAIR,
        messages=messages,
        schema=contract_schema,
        allowed_dirs=allowed_dirs,
        job_id=audit_log.job_id,
        temperature=0.4,
    )
)
```
Per RESEARCH.md Assumption A3, use `Purpose.CRITIC` (`shared/providers/llm_gateway.py` line 77, already defined but unused end-to-end) rather than adding a new `Purpose.WALKTHROUGH` enum value. This walkthrough call needs no `schema=`/structured-contract — plain-text generation, since D-08 wants prose, not a code-patch contract.

**Storage:** `ModuleManifest` dataclass (`shared/modules/manifest.py`) has no `walkthrough` field today — this phase must add one (e.g., `walkthrough: str = ""`) to the dataclass, following the exact field-addition style already used for `validation_results` (line 86) — plain dataclass field with a default, serialized automatically via `asdict()` in `to_dict()`.

---

### `ui_service/src/machines/pipelinePageMachine.ts` (NEW) — XState v5 machine (provider, event-driven)

**Analog:** `ui_service/src/machines/monitoringPage.ts` (full file, 237 lines) — closest existing parallel-region XState v5 machine using `setup({ types, actors, guards }).createMachine({...})`.

**Structural pattern to copy (parallel regions, each with own initial/states):**
```typescript
// Source: ui_service/src/machines/monitoringPage.ts lines 75-125, 222-236 (imports + setup + one region)
import { setup, fromPromise } from 'xstate';
import { adminApi, type FeatureHealth } from '../lib/adminClient';

export const monitoringPageMachine = setup({
  types: {
    context: {} as MonitoringPageContext,
    events: {} as MonitoringPageEvent,
  },
  actors: {
    fetchFeatureHealth: fromPromise(async () => { /* ... */ }),
  },
  guards: {
    isHealthRetryable: ({ context }) => context.healthError !== null,
  },
}).createMachine({
  id: 'monitoringPage',
  type: 'parallel',
  context: { /* ... */ },
  states: {
    health: { initial: 'loading', states: { /* loading/loaded/error */ } },
    activeTab: {
      initial: 'overview',
      states: { overview: {}, modules: {}, alerts: {} },
      on: { TAB_OVERVIEW: '.overview', TAB_MODULES: '.modules', TAB_ALERTS: '.alerts' },
    },
  },
});
```
**Key difference for `pipelinePageMachine`:** monitoringPage.ts only uses `fromPromise` actors (polling). Pipeline page needs `fromCallback` (SSE `EventSource` is a long-lived callback-style connection, not a one-shot promise) — this specific actor type has **zero existing usage anywhere in `ui_service/src/`** (confirmed via grep), so RESEARCH.md's Pattern 4 code sample (reproduced below) is the only reference, not an in-repo analog:
```typescript
// Source: RESEARCH.md Pattern 4 (derived, not yet in codebase) — wraps existing
// connectPipelineSSE() from ui_service/src/lib/adminClient.ts (lines 287-299, unmodified)
import { setup, fromCallback } from 'xstate';
import { connectPipelineSSE, type PipelineState } from '../lib/adminClient';

actors: {
  sseConnection: fromCallback(({ sendBack }) => {
    const es = connectPipelineSSE(
      (state) => sendBack({ type: 'SSE_MESSAGE', data: state }),
      () => sendBack({ type: 'SSE_ERROR' }),
    );
    return () => es.close();  // cleanup on region exit
  }),
},
```
Second region (`reviewPanel: closed/open`) follows the `activeTab` region shape from monitoringPage.ts verbatim (simple state-only sub-states + `on` transitions at the parent level).

---

### `ui_service/src/components/pipeline/NodeDetailPanel.tsx` — extend with 5 accordion sections (component, request-response)

**Analog:** same file (full file read, 313 lines) — existing `<section>` pattern (Status/Auth/Connected/Test Runner) is the direct template; UI-SPEC.md mandates reusing this exact header rhythm inside `@radix-ui/react-accordion` triggers instead of plain `<section>`.

**Existing section header style to preserve inside accordion triggers** (lines 141-144, repeated for every section):
```tsx
<section>
  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
    Status
  </h3>
  ...
</section>
```

**Existing panel shell to extend, not replace** (lines 94-136 — backdrop + slide-in panel + header):
```tsx
<AnimatePresence>
  {node && (
    <>
      <motion.div key="backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      <motion.div key="panel" initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 w-96 bg-zinc-900 border-l border-zinc-700 z-50 flex flex-col shadow-2xl">
        {/* header, then content */}
      </motion.div>
    </>
  )}
</AnimatePresence>
```
Add the five D-06 accordion sections + D-19 walkthrough block + footer Approve/Reject buttons inside the existing `<div className="flex-1 overflow-auto p-4 space-y-4">` content area (line 139), conditioned on `node.type === 'module' && pendingApproval === true` per UI-SPEC.md Component Contract §2.

**Test result `<pre>` styling to reuse for the Code Diff accordion section** (lines 291-295):
```tsx
{testResult.stdout && (
  <pre className="text-[11px] text-zinc-400 bg-zinc-950 rounded p-2 overflow-auto max-h-60 whitespace-pre-wrap font-mono">
    {testResult.stdout}
  </pre>
)}
```

**Pass/fail row iconography to reuse for the Sandbox Validation Report section** (lines 258-263):
```tsx
{testResult.exit_code === 0 ? (
  <CheckCircle2 className="w-4 h-4 text-green-400" />
) : (
  <XCircle className="w-4 h-4 text-red-400" />
)}
```

---

### `ui_service/src/components/pipeline/ModuleNode.tsx` — pendingApproval badge (component, request-response)

**Analog:** same file (full file, 58 lines) — existing `stateStyles` lookup-map pattern is the exact template for adding a `pendingApproval` visual variant.

**Exact pattern to extend** (lines 20-28):
```tsx
const stateStyles: Record<string, { border: string; badge: string; badgeText: string }> = {
  running: { border: 'border-blue-500/60 bg-blue-500/10', badge: 'bg-blue-500/20', badgeText: 'text-blue-300' },
  disabled: { border: 'border-zinc-600/40 bg-zinc-800/40', badge: 'bg-zinc-600/20', badgeText: 'text-zinc-400' },
  failed: { border: 'border-red-500/60 bg-red-500/10', badge: 'bg-red-500/20', badgeText: 'text-red-300' },
};

function ModuleNodeComponent({ data }: NodeProps) {
  const d = data as unknown as ModuleNodeData;
  const style = stateStyles[d.state] ?? stateStyles.disabled;
  return (
    <div className={`rounded-lg border px-4 py-3 min-w-[170px] shadow-md ${style.border}`}>
      <Handle type="target" position={Position.Left} className="!bg-zinc-500" />
      ...
      <Handle type="source" position={Position.Right} className="!bg-zinc-500" />
    </div>
  );
}
```
Per UI-SPEC.md Component Contract §1: add `pendingApproval: boolean` to `ModuleNodeData` interface (line 11-18), add an `amber-500/60` border variant + a top-right `Eye`-icon badge with a Framer Motion `scale: [1, 1.08, 1]` pulse loop, and a `"· Needs Review"` label suffix — this is additive to the existing `stateStyles` map, not a rewrite.

---

### `ui_service/src/components/chat/ApprovalActionCard.tsx` (NEW) — chat approval card (component, request-response)

**Analog:** `ui_service/src/components/chat/ActionCard.tsx` (full file, 213 lines) — D-02 explicitly names this as the pattern to extend.

**Full shell + state machine to copy verbatim** (lines 85-96, 125-213 — `pending`/`executing`/`completed`/`failed` AnimatePresence blocks):
```tsx
<div className="rounded-lg border border-border bg-card p-4 space-y-3 max-w-md">
  {/* Header */}
  <div className="flex items-center gap-3">
    <div className="rounded-full bg-primary/10 p-2">
      <Icon className="w-4 h-4 text-primary" />
    </div>
    ...
  </div>
  {/* Arguments */}
  ...
  <AnimatePresence mode="wait">
    {status === 'pending' && ( /* approve/reject buttons */ )}
    {status === 'executing' && ( /* spinner */ )}
    {status === 'completed' && ( /* green check, spring entrance */ )}
    {status === 'failed' && ( /* red warning, shake keyframes: x: [0, -10, 10, -10, 10, 0] */ )}
  </AnimatePresence>
</div>
```

**Approve/Reject button pattern to reuse verbatim, just relabel** (lines 136-150):
```tsx
<button onClick={() => onApprove(toolCall.id)}
  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-green-500 hover:bg-green-600 text-white text-sm font-medium transition-colors">
  <Check className="w-4 h-4" />
  Approve
</button>
<button onClick={() => onReject(toolCall.id)}
  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors">
  <X className="w-4 h-4" />
  Reject
</button>
```
Per Copywriting Contract in UI-SPEC.md, relabel to "Approve Module" / "Reject Module". Additions over the base card per UI-SPEC.md §5: `Puzzle` icon instead of `parseToolName`'s category icon map, an inline collapsed `BlueprintCard` summary, and an optional feedback `<textarea>` shown only when `status === 'pending'`.

**Failed-state shake keyframes to reuse for `rejected` node transition (D-13) too** (lines 190-200):
```tsx
{status === 'failed' && (
  <motion.div key="failed" initial={{ scale: 0, opacity: 0 }}
    animate={{ scale: 1, opacity: 1, x: [0, -10, 10, -10, 10, 0], transition: { duration: 0.5 } }}
    exit={{ opacity: 0, transition: { duration: 0.1 } }}
    className="flex items-start gap-2 p-3 rounded-md bg-red-500/10 border border-red-500/20">
```

---

### `ui_service/src/components/pipeline/ModulePanel.tsx` (NEW) — generic module output panel (D-07) (component, transform)

**Analog:** `ui_service/src/components/pipeline/NodeDetailPanel.tsx`'s Status section row pattern (lines 145-185, key/value list) + backend contract `shared/modules/output_contract.py::AdapterRunResult`.

**Row pattern to reuse for `data_points` rendering:**
```tsx
{category && (
  <div className="flex items-center justify-between text-sm">
    <span className="text-zinc-400">Category</span>
    <span className="text-zinc-200">{category}</span>
  </div>
)}
```

**Backend contract fields to render** (`shared/modules/output_contract.py` — `AdapterRunResult.data_points: List[DataPoint]`, `AdapterRunResult.artifacts: List[Artifact]`; `Artifact.type: str` describes chart/file/log/report — UI-SPEC.md §6 says trust this `type` field for chart-type inference, don't shape-sniff).

**Empty-state analog:** `ui_service/src/components/ui/error-states.tsx::EmptyState` (lines 84-107, full component) — reuse verbatim with `title="No data yet"` / `description="This module hasn't returned any data. Run it from the pipeline or ask the assistant to use it."` per UI-SPEC.md Copywriting Contract.

**Card shell to reuse** (matches `ActionCard.tsx` line 97 shell): `rounded-lg border border-border bg-card p-4`.

---

### `ui_service/src/lib/adminClient.ts` — extend with approve/reject/audit fetchers (utility, request-response)

**Analog:** same file, `enableModule`/`disableModule`/`runModuleTests` (lines 206-219) — the `adminFetch<T>()` generic wrapper (lines 181-192) is the single fetch primitive every admin call goes through; new calls are one-liners against it.

**Exact pattern to copy:**
```typescript
// Source: ui_service/src/lib/adminClient.ts lines 206-219
enableModule: (category: string, platform: string) =>
  adminFetch<ModuleActionResult>(`/admin/modules/${category}/${platform}/enable`, { method: 'POST' }),

disableModule: (category: string, platform: string) =>
  adminFetch<ModuleActionResult>(`/admin/modules/${category}/${platform}/disable`, { method: 'POST' }),
```
New: `approveModule: (moduleId: string) => adminFetch<...>('/admin/modules/${moduleId}/approve', { method: 'POST' })`, `rejectModule: (moduleId: string, feedback?: string) => adminFetch<...>('/admin/modules/${moduleId}/reject', { method: 'POST', body: JSON.stringify({ feedback }) })`.

**`adminFetch<T>` generic wrapper to reuse unmodified** (lines 181-192):
```typescript
async function adminFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${ADMIN_BASE}${path}`, {
    signal: opts?.signal ?? AbortSignal.timeout(ADMIN_REQUEST_TIMEOUT_MS),
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`Admin API ${res.status}: ${body}`);
  }
  return res.json();
}
```

**SSE connection function to reuse unmodified** (lines 287-299, `connectPipelineSSE`) — consumed by the new `pipelinePageMachine`'s `fromCallback` actor, not itself modified. `PipelineState` interface (lines 63-72) needs new optional fields (`pending_approval`, `build_stage` per-module) matching the backend SSE payload extension.

---

## Shared Patterns

### RBAC (admin+ for all approve/reject/mutation endpoints)
**Source:** `shared/auth/rbac.py` — `Permission.ADMIN_ALL` via `require_permission()` FastAPI dependency; already used by `validate_draft`/`promote_draft`/`rollback_module` in `orchestrator/admin_api.py`.
**Apply to:** `orchestrator/admin_api.py` approve/reject endpoints (D-17), any new mutation endpoints.
```python
user: User = Depends(require_permission(Permission.ADMIN_ALL)),
```

### Error handling (draft/module endpoints)
**Source:** `orchestrator/admin_api.py` — repeated 3-line shape across every module-lifecycle endpoint (lines 1451-1454, 1475-1478, 1499-1502, etc.)
**Apply to:** All new admin_api.py endpoints.
```python
if result.get("status") == "error":
    raise HTTPException(400, result.get("error", "Unknown error"))
return result
```

### Audit logging (append-only JSONL, actor + timestamp + hash)
**Source:** `shared/modules/audit.py::DevModeAuditLog.log_action()` (lines 373-414), instance shared between `DraftManager`/`VersionManager`, constructed once in `orchestrator/orchestrator_service.py` (lines 979, 1816).
**Apply to:** approve/reject endpoints (D-19), reject-GC actions (D-10), rate-limit 429 events if audit trail desired.
```python
self.audit_log.log_action(
    action="draft_created",  # → "module_approved" / "module_rejected" / "module_gc_purged"
    actor=actor,
    module_id=module_id,
    draft_id=draft_id,       # optional
    details={"source_version": from_version, ...}
)
```

### Rate limiting primitive (token bucket)
**Source:** `shared/utils/rate_limiter.py` — `TokenBucketRateLimiter` / `RateLimiterRegistry` (full file, 318 lines), already thread-safe + async + Prometheus-ready.
**Apply to:** New `RateLimitMiddleware` (REQ-020), wraps this unmodified — do not reimplement the algorithm.
```python
limiter = get_rate_limiter_registry().get(f"http:{key}")
if not await limiter.acquire():
    retry_after = limiter.retry_after()
    return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded", "retry_after": retry_after},
                         headers={"Retry-After": str(int(retry_after) + 1)})
```

### FastAPI TestClient fixture pattern (RBAC-role-parameterized headers)
**Source:** `tests/integration/admin/conftest.py` (full file, 422 lines) — `admin_headers`/`operator_headers`/`viewer_headers`/`owner_headers` fixtures, `create_test_admin_app()` builds a minimal standalone FastAPI app wired with real `APIKeyAuthMiddleware` + tmp-path SQLite stores.
**Apply to:** All new integration tests (`test_approval_gate.py`, `test_reject_gc.py`, `test_inbound_rate_limit.py`) — extend `create_test_admin_app()` with the new approve/reject/rate-limited endpoints rather than building a second test-app factory.
```python
@pytest.fixture
def admin_headers(api_key_store, test_org):
    plaintext_key, _ = api_key_store.create_key(test_org.org_id, "admin")
    return {"X-API-Key": plaintext_key}
```

### Error taxonomy / no-silent-fallback UI states
**Source:** `ui_service/src/components/ui/error-states.tsx` — `DegradedBanner` (amber, optional retry), `EmptyState` (centered, icon + heading + body), `TimeoutSkeleton` (5s "taking longer" overlay). All Phase 6-established, all reused verbatim per UI-SPEC.md's Copywriting Contract for rejected/failed/empty review-panel states.
**Apply to:** `NodeDetailPanel.tsx` accordion section fetch failures, `ModulePanel.tsx` empty state, pipeline page's rejected-node transient render (D-13 — "node must not simply vanish silently").

### Framer Motion state-transition idioms
**Source:** `ActionCard.tsx` (spring entrance `{ scale: 1, opacity: 1, transition: { duration: 0.3, type: 'spring' } }` for completed; shake `x: [0, -10, 10, -10, 10, 0]` for failed) + `StageNode.tsx` (dashed-border technical aesthetic) + `NodeDetailPanel.tsx` (slide-in panel spring `{ type: 'spring', damping: 25, stiffness: 300 }`).
**Apply to:** `BlueprintCard.tsx` expand/collapse, `ModuleNode.tsx` approved/rejected transition-in, `ApprovalActionCard.tsx`.

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `ui_service/e2e/pipeline-sse-reconnect.spec.ts` + `ui_service/playwright.config.ts` | test (E2E) | streaming | No test framework exists in `ui_service/` at all (confirmed: no jest/vitest/playwright in `package.json`). Full Wave 0 install required: `npm install --save-dev @playwright/test && npx playwright install --with-deps chromium`. RESEARCH.md Pitfall 4 mandates testing against real running services (`docker compose restart dashboard_service` from the test), not mocked `EventSource` — no in-repo precedent for this pattern exists (closest conceptual precedent is `make test-monkey`'s "requires services up" convention, referenced in RESEARCH.md but not a literal file to copy). |
| `ui_service/src/machines/pipelinePageMachine.ts`'s `fromCallback` SSE actor | provider (XState actor) | streaming | Zero existing `fromCallback` usage anywhere in `ui_service/src/` (confirmed via grep) — `monitoringPage.ts`/`financePage.ts` only use `fromPromise`. RESEARCH.md Pattern 4 is the only available reference (reproduced in Pattern Assignments above), not an in-repo analog. |
| `orchestrator/retention_worker.py` background-task **startup wiring** (`asyncio.create_task(...)` at app boot) | service (worker bootstrap) | batch | No existing `asyncio.create_task()` background-task pattern at FastAPI/gRPC-server startup anywhere in `orchestrator/orchestrator_service.py` or `dashboard_service/main.py` (confirmed via grep for `on_event("startup")` / `create_task`). The worker *loop shape* has a strong analog (`pipeline_event_generator`), but the *startup wiring* does not. |

## Metadata

**Analog search scope:** `orchestrator/`, `shared/modules/`, `shared/auth/`, `shared/billing/`, `shared/utils/`, `shared/providers/`, `tools/builtin/`, `dashboard_service/`, `ui_service/src/{machines,components,lib,store,app}`, `tests/{unit,integration,feature}`
**Files scanned:** ~45 (full or targeted reads across backend lifecycle/auth/billing modules, frontend pipeline/chat/machine components, and existing test suites)
**Pattern extraction date:** 2026-07-12
