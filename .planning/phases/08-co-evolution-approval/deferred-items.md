# Deferred Items

Out-of-scope discoveries logged during plan execution (not fixed — pre-existing,
unrelated to the current task's changes).

## 08-02 Task 2

- **`tests/unit/test_module_tools.py` fails at collection when run standalone**
  (`AttributeError: module 'tools.builtin' has no attribute 'module_builder'`).
  Root cause: `tools.builtin.module_builder` imports generated gRPC proto
  modules (`llm_service.llm_pb2`, `llm_service.llm_pb2_grpc`) that aren't
  present in this environment; other suites (e.g.
  `tests/integration/cross_feature/conftest.py`'s `setup_builder` fixture)
  work around this by mocking `sys.modules` before import, but
  `tests/unit/test_module_tools.py` does not do this itself. Confirmed
  pre-existing: byte-identical to the file at commit
  `956ab7c0134897a4a242ccef64ab0e728a40b52d` (base of this plan), and the
  same collection error reproduces with the ORIGINAL (pre-08-02)
  `module_installer.py` when run standalone without manual proto mocking.
  When manually mocked (`sys.modules['llm_service'] = MagicMock()` etc.
  before import), all 26 tests in the file pass, confirming the actual
  test logic is sound and unaffected by 08-02's changes.
  Out of scope for 08-02 — not touched.

## 08-02 Task 3

- **`tests/integration/admin/` cannot be collected in this worktree at all**
  (`ImportError: cannot import name 'llm_pb2' from 'llm_service'`, then after
  mocking that, `ImportError: cannot import name 'sandbox_pb2' from
  'shared.generated'`). Root cause: `tests/integration/admin/conftest.py`
  imports `orchestrator.config_manager`, which pulls in
  `orchestrator/__init__.py` -> `orchestrator_service.py`, which imports
  several generated gRPC proto modules (`llm_service.llm_pb2`,
  `shared.generated.sandbox_pb2`, etc.) that are `protoc`-generated build
  artifacts not present in this bare worktree (normally produced by the
  Docker build / `make proto`, not committed to git — `shared/generated/`
  contains only `__init__.py`). This is a pre-existing, environment-wide gap
  affecting the entire `tests/integration/admin/` suite (unchanged top-level
  imports — confirmed via `git show` against the plan's base commit
  `956ab7c0134897a4a242ccef64ab0e728a40b52d`), not something introduced by
  08-02. The plan's own `<verification>` section anticipates a Docker-gated
  skip, not a hard collection ImportError, indicating the plan was authored
  against an environment where these generated modules exist.
  Worked around for verification purposes by exercising the modified logic
  directly (approve_module/reject_module org_id threading + ISO-8601
  timestamps, and the audit_module_endpoint BuildAuditLog glob/filter logic)
  via standalone scripts bypassing the orchestrator import chain — all pass.
  Out of scope for 08-02 — not touched (would require generating protos or
  restructuring the test's import chain, both architectural changes beyond
  this plan's scope).

## Pre-existing test breakage confirmed at base 956ab7c (Wave 1 post-merge gate, 2026-08-14)

Verified by running each at the base commit in a throwaway worktree — none caused by Phase 8:

- `tests/unit/test_context_bridge.py` — collection error: imports `_normalize_context_for_tools`, removed in 05-05 refactor (46ccd2a)
- `tests/unit/providers/test_fallback_chain.py::test_fallback_order_matches_priority` — provider order assertion fails
- `tests/integration/cross_feature/test_feature_test_gating.py` — collection error: imports `tools.builtin.feature_test_harness`, deleted in 05-05 dead-code cleanup (14e6d7a)
- `tests/integration/cross_feature/test_contract_enforcement_pipeline.py` — 2 failures (`ImportPolicy` not iterable; orchestrator source assertion)
- `tests/integration/cross_feature/test_policy_propagation.py` — 2 failures (`ImportPolicy` not iterable)
