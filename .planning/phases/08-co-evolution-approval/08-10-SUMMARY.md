---
phase: 08-co-evolution-approval
plan: 10
subsystem: auth
tags: [rbac, session-context, chat-tools, module-approval, grpc, audit]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: "08-02's shared/modules/approval.py core (approve_module/reject_module with actor/org_id split) and shared.audit ActorContext/AuditStore"
provides:
  - "shared/auth/session_context.py — contextvar-scoped authenticated session User for non-HTTP entry points (chat/gRPC)"
  - "Chat approve_module/reject_module actions on ModuleAdminTool, enforcing admin+ RBAC identically to the HTTP endpoints"
  - "Real authenticated-principal + org_id resolution in QueryAgent (replaces the org_id = \"default\" placeholder)"
affects: [08-11, 08-12, 08-13, Phase 9 marketplace/approval-chain work]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Session identity contextvar (shared/auth/session_context.py) mirrors shared/audit/context.py's ContextVar/Token/contextmanager shape — distinct from ActorContext (audit-only, no role) and is the authorization source for privileged chat tool actions"
    - "Module-level resolver function (_resolve_session_user) factored out of the gRPC service method so RBAC-critical metadata parsing is unit-testable without constructing the full OrchestratorService"
    - "_require_admin_session() single shared gate: read session -> fail closed on missing session -> fail closed on missing WRITE_CONFIG permission -> return (user, None) on success"

key-files:
  created:
    - shared/auth/session_context.py
    - tests/unit/test_module_admin_approval.py
  modified:
    - orchestrator/orchestrator_service.py
    - tools/builtin/module_admin.py

key-decisions:
  - "Factored _resolve_session_user() as a module-level function (not just an OrchestratorService method) so gRPC metadata -> User resolution is unit-testable via a stub context/store without instantiating the full gRPC service (which pulls in LLM clients, sandbox, checkpointing, etc.)"
  - "OrchestratorService constructs its own APIKeyStore in __init__ (admin_api.py's instance doesn't exist yet at that point — start_admin_server() runs later in serve()), then serve() passes that same instance into start_admin_server(api_key_store=...) so gRPC session resolution, the HTTP admin API, and the retention worker all share one store instead of two"
  - "ApproveModuleStrategy/RejectModuleStrategy obtain their DevModeAuditLog via draft_manager.audit_log (already the same instance orchestrator_service.py threads into DraftManager/VersionManager) rather than adding a new constructor dependency to ModuleAdminTool"
  - "RBAC check strictly precedes module_id validation in both strategies (fail-closed ordering) so a malformed action still returns a permission error before any file I/O is attempted"

requirements-completed: ["REQ-014"]

duration: 25min
completed: 2026-08-14
---

# Phase 8 Plan 10: Chat Approval Session Identity + RBAC Summary

**Chat-side approve/reject on ModuleAdminTool, gated by a gRPC-metadata-resolved session User enforcing the same admin+ RBAC and calling the same `shared/modules/approval.py` core as the HTTP endpoints.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-08-14 (session start)
- **Completed:** 2026-08-14T04:48:15Z
- **Tasks:** 2/2 completed
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `shared/auth/session_context.py`: contextvar-scoped authenticated `User` for chat/gRPC, distinct from the audit-only `ActorContext` — the authorization source `get_session_user()` that privileged tool actions must consult.
- `orchestrator/orchestrator_service.py`: `x-api-key` gRPC metadata resolved to a `User` via a new `APIKeyStore` instance; `QueryAgent` now activates `session_user(user)` + `ActorContext(channel="chat", actor_id=user.user_id, org_id=user.org_id)` for the request duration when authenticated; `_process_query`'s `org_id = "default"` placeholder now reads `user.org_id` when a session resolved.
- `tools/builtin/module_admin.py`: `ApproveModuleStrategy`/`RejectModuleStrategy` registered on `ModuleAdminTool`, gated by a shared `_require_admin_session()` helper that fails closed on no session or non-admin role, then calls `shared.modules.approval.approve_module`/`reject_module` directly with `actor=user.user_id` and `org_id=user.org_id` — never a hardcoded `"chat_agent"` string.
- 24 new tests in `tests/unit/test_module_admin_approval.py` covering session-context round-trip, gRPC metadata resolution edge cases (missing/unknown/raising key store, case-insensitive header, bytes vs str), and the full approve/reject RBAC behavior matrix (admin success, operator/viewer/no-session fail-closed, reject-with-feedback repair path vs terminal reject).

## Task Commits

Each task was committed atomically:

1. **Task 1: Session identity for non-HTTP entry points + chat actor context** - `24f9072` (feat)
2. **Task 2: RBAC-guarded approve/reject strategies on ModuleAdminTool** - `ee6f1ec` (feat)

**Plan metadata:** committed by orchestrator after merge (worktree mode — this agent does not write STATE.md/ROADMAP.md)

_TDD applied both tasks: tests were authored alongside the RED-phase check (import failures confirmed missing symbols before implementation), then implementation landed to GREEN before each task's commit._

## Files Created/Modified
- `shared/auth/session_context.py` - New: `set_session_user`/`get_session_user`/`session_user`/`reset_session_user`/`SessionAuthError`, mirrors `shared/audit/context.py`'s contextvar pattern
- `orchestrator/orchestrator_service.py` - Modified: `self._api_key_store` construction, module-level `_resolve_session_user()`, `_get_session_user()` method, `QueryAgent` ExitStack wiring of `session_user()`+`actor_context()`, `_process_query(user=...)` param, `serve()` passes `api_key_store=` into `start_admin_server()`
- `tools/builtin/module_admin.py` - Modified: `_require_admin_session()`, `_validate_module_id()`, `ApproveModuleStrategy`, `RejectModuleStrategy`, registration in `ModuleAdminTool.__init__` reusing `draft_manager.audit_log`
- `tests/unit/test_module_admin_approval.py` - New: 24 tests across `TestSessionContextRoundTrip`, `TestResolveSessionUser`, `TestApproveModuleStrategy`, `TestRejectModuleStrategy`

## Decisions Made
- `_resolve_session_user()` factored as a module-level function rather than inlined in the `OrchestratorService` method, purely for testability — `OrchestratorService` construction pulls in LLM clients/sandbox/checkpointing and is too heavy to instantiate in a unit test; the resolver's logic (gRPC metadata parsing + `APIKeyStore.validate_key`) is the security-critical part and needed direct coverage.
- `serve()` now explicitly passes the `OrchestratorService`'s `APIKeyStore` into `start_admin_server(api_key_store=...)`, closing a latent duplicate-store gap: previously `admin_api.py` would have constructed its own second `APIKeyStore` against the same SQLite file. This wasn't strictly required by the plan's acceptance criteria (which only checks `orchestrator_service.py` has exactly one `APIKeyStore(` construction) but was a straightforward Rule 2 hardening once the gap was visible — two file-backed SQLite handles opening the same DB is a latent correctness risk (WAL mode + writes from two connections), not just style.
- Chose to thread `draft_manager.audit_log` (with a `version_manager.audit_log` fallback) into the two new strategies rather than adding a new `audit_log=` constructor parameter to `ModuleAdminTool` — both managers already receive the same `DevModeAuditLog` instance from `orchestrator_service.py`, so this avoids introducing a second way to obtain the same object per the plan's explicit guidance.

## Deviations from Plan

None - plan executed as written. The `_resolve_session_user()` module-level extraction and the `start_admin_server(api_key_store=...)` wiring are implementation choices within Task 1's stated behavior/acceptance criteria (testability and "no duplicate store"), not scope changes — no new files outside the plan's `files_modified` list were created, and both were called out under "Decisions Made" above rather than treated as silent additions.

## Issues Encountered
- `make proto-gen` was required before the first test run (`llm_pb2` import failure from `shared/clients/llm_client.py`, a pre-existing gitignored-stub gap flagged in the plan-spawn instructions, not caused by this plan's changes). Regenerated once at the start of execution; no further action needed.

## User Setup Required

None - no external service configuration required. `AUTH_DB_PATH` env var (already documented/used elsewhere in the codebase) governs where the new `APIKeyStore` instance persists; defaults to `data/api_keys.db` exactly as the existing admin API store does.

## Next Phase Readiness

- D-02 (chat approval) and D-17 (admin+ RBAC identical across HTTP and chat) are both satisfied and covered by tests.
- `ApproveModuleStrategy`/`RejectModuleStrategy` are automatically discoverable to the LLM via `CompositeTool.get_schema()` (no separate wiring needed — schema derives from `self._strategies`).
- No blockers for subsequent Phase 8 plans. Chat clients must supply a valid `x-api-key` gRPC metadata entry with an admin+ role key to exercise the new actions; unauthenticated/lower-role chat sessions continue to work for all non-privileged actions exactly as before.

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-14*
