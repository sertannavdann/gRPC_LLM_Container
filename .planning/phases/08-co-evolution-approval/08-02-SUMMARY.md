---
phase: 08-co-evolution-approval
plan: 02
subsystem: auth
tags: [approval-gate, integrity-hash, audit-trail, sha256, rbac, gc]

# Dependency graph
requires:
  - phase: 08-01
    provides: manifest status-guard raised to APPROVED, GC marker writer, ApprovalPolicy scaffold, approve/reject core + RBAC-gated endpoints
provides:
  - compute_code_bundle_hash() — manifest.json-exclusive content-addressed hash, single source of truth for approval/install integrity
  - manifest.approved_bundle_sha256 field recording what an admin actually approved
  - Unconditional install-time bundle-hash verification (no longer gated behind an optional attestation argument)
  - Individual-admin audit attribution (actor=user.user_id, org_id preserved separately)
  - Single-designator ISO-8601 timestamps across approval.py and gc.py
  - /audit admin endpoint and its test mirror reading the same BuildAuditLog data source with the same AUDIT_DIR default
  - Fail-closed GC marker writer (no phantom directories for bogus module_ids)
affects: [08-03, 08-04, 08-06, 08-08, 08-09, 08-10, 08-11]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Approval-time content hash excludes mutable manifest state (status/updated_at/approved_bundle_sha256 itself) — only code artifacts are hashed, so status transitions never invalidate an attestation"
    - "Install-time integrity check runs unconditionally against manifest.approved_bundle_sha256, with attestation as an additional caller-supplied cross-check, not the sole gate"
    - "Fail-closed re-approval requirement for pre-fix manifests with no recorded approval hash"

key-files:
  created:
    - tests/integration/install/test_approval_attestation_chain.py
    - .planning/phases/08-co-evolution-approval/deferred-items.md
  modified:
    - shared/modules/artifacts.py
    - shared/modules/manifest.py
    - shared/modules/approval.py
    - shared/modules/gc.py
    - tools/builtin/module_installer.py
    - orchestrator/admin_api.py
    - tests/unit/modules/test_installer_approval_guard.py
    - tests/integration/cross_feature/conftest.py
    - tests/integration/install/test_validated_only_guard.py
    - tests/integration/admin/conftest.py
    - tests/integration/admin/test_approval_gate.py
    - tests/unit/test_module_tools.py

key-decisions:
  - "manifest.json is permanently excluded from the approval/install integrity hash — it carries mutable lifecycle state by design, so including it makes any attestation captured before a status transition unverifiable by construction (CR-01 root cause)"
  - "Install-time hash verification is unconditional (checked against manifest.approved_bundle_sha256 on every call), with the optional attestation argument treated as an additional cross-check rather than the only gate (WR-01)"
  - "Pre-fix APPROVED manifests with an empty approved_bundle_sha256 are refused at install time and require re-approval, rather than being grandfathered in as trusted (T-08-08 fail-closed)"
  - "actor is always the individual admin's user_id; org_id is threaded through as a separate optional parameter and stored in audit details for tenant context (WR-02)"

patterns-established:
  - "compute_code_bundle_hash(module_dir, module_id) is the single hashing entry point for both approval and install — do not recompute bundle hashes inline elsewhere"

requirements-completed: [REQ-014]

# Metrics
duration: 25min
completed: 2026-08-14
---

# Phase 8 Plan 02: Approval Integrity Binding + Accountability Fixes Summary

**Approval and install now share one manifest-exclusive SHA-256 code hash (`compute_code_bundle_hash`), verified unconditionally at install time against `manifest.approved_bundle_sha256`, closing the CR-01 hash-mismatch bug and the WR-01 unattested-tampering gap, plus individual-admin audit attribution and ISO-8601 hygiene.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-08-14T03:15:00+03:00 (approx)
- **Completed:** 2026-08-14T03:31:00+03:00
- **Tasks:** 3
- **Files modified:** 12 (2 created, 10 modified)

## Accomplishments
- Fixed CR-01: `approve_module()` now hashes only `adapter.py` + `test_adapter.py` (never `manifest.json`), so the VALIDATED→APPROVED status transition no longer invalidates a validate-time attestation
- Fixed WR-01: `install_module()` recomputes and verifies the code-bundle hash against `manifest.approved_bundle_sha256` on **every** call, not only when a caller opts in with an attestation argument — post-approval tampering is now caught in the default (unattested) install path
- Added fail-closed handling for pre-fix APPROVED manifests with no recorded approval hash (must re-approve, not trusted)
- Closed WR-02 (individual admin attribution), WR-03 (malformed ISO-8601 timestamps), WR-04 (`/audit` endpoint/test-mirror data-source drift), WR-05 (inconsistent `AUDIT_DIR` default), and hygiene items IN-01/IN-03/IN-04
- New regression test exercises the real validate → approve → install(attestation) chain against a single on-disk module (not a pre-fabricated APPROVED fixture)

## Task Commits

Each task was committed atomically:

1. **Task 1: Code-only bundle hash + approval-time attestation issuance** - `951d9ef` (fix)
2. **Task 2: Unconditional install-time verification + full validate→approve→install chain test** - `f489ddd` (fix)
3. **Task 3: Individual-admin attribution, ISO-8601 hygiene, audit-endpoint fidelity** - `6c85244` (fix)

## Files Created/Modified
- `shared/modules/artifacts.py` - `CODE_BUNDLE_FILES` constant + `compute_code_bundle_hash()`, the single source of truth for approval/install hashing (excludes manifest.json)
- `shared/modules/manifest.py` - `approved_bundle_sha256: str = ""` field on `ModuleManifest`
- `shared/modules/approval.py` - removed manifest-inclusive `_compute_bundle_hash`; `approve_module()`/`reject_module()` now use `compute_code_bundle_hash`, accept an `org_id` kwarg, and emit single-designator ISO-8601 timestamps
- `shared/modules/gc.py` - `queue_for_gc()` existence-guards `module_dir` instead of fabricating it, returns `Optional[Path]`, single-designator timestamp
- `tools/builtin/module_installer.py` - PRE-INSTALL CHECK 2 is now unconditional (fail-closed `missing_approval_hash` + `hash_mismatch` against `manifest.approved_bundle_sha256`), removed duplicated `if not _module_loader` guard within `install_module`
- `orchestrator/admin_api.py` - approve/reject endpoints pass `actor=user.user_id` + `org_id=user.org_id`; `/audit` `AUDIT_DIR` default fixed; dropped unused `ModuleStatus` import
- `tests/integration/install/test_approval_attestation_chain.py` - new CR-01/WR-01/T-08-08 regression suite (4 tests)
- `tests/unit/modules/test_installer_approval_guard.py`, `tests/integration/cross_feature/conftest.py`, `tests/integration/install/test_validated_only_guard.py`, `tests/unit/test_module_tools.py` - fixtures updated to set `approved_bundle_sha256` on fabricated APPROVED modules and use the code-only hash
- `tests/integration/admin/conftest.py` - `/audit` test mirror now reads `BuildAuditLog` glob'd from the audit dir (matching production); approve/reject mirrors updated; `admin_headers` assigns an explicit `user_id`
- `tests/integration/admin/test_approval_gate.py` - asserts recorded audit `actor` is the admin's `user_id`, not `org_id`
- `.planning/phases/08-co-evolution-approval/deferred-items.md` - new file, logs two pre-existing environment gaps discovered (not fixed, out of scope)

## Decisions Made
- manifest.json is permanently excluded from the integrity hash — this is the structural fix for CR-01, not a workaround
- Install-time verification is unconditional; the attestation argument is now an additional cross-check layered on top of the mandatory `approved_bundle_sha256` comparison, not the sole gate
- Pre-fix manifests with no recorded hash fail closed and require re-approval rather than being implicitly trusted

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/unit/test_module_tools.py`'s `_approve()` helper broke under the new unconditional install guard**
- **Found during:** Task 2 verification
- **Issue:** The helper simulated admin approval by only flipping `manifest.status` to APPROVED, without setting `approved_bundle_sha256`. Under the new unconditional guard this makes every subsequent `install_module()` call fail with `missing_approval_hash`, breaking 3 previously-passing tests (`test_install_validated_module`, `test_install_without_loader`, `test_build_fix_install_cycle`).
- **Fix:** `_approve()` now also computes and sets `manifest.approved_bundle_sha256 = compute_code_bundle_hash(module_dir, module_id)` before saving, matching the pattern applied to the four fixtures explicitly named in the plan.
- **Files modified:** `tests/unit/test_module_tools.py`
- **Verification:** All 26 tests in the file pass (verified with manual `llm_service` proto mocking — see Issues Encountered below).
- **Committed in:** `f489ddd` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary correctness fix directly caused by Task 2's unconditional guard; this test file was not in the plan's `files_modified` list but was broken by the change, so fixing it was in scope per Rule 3. No scope creep beyond the one-line fixture fix.

## Issues Encountered

- **`tests/unit/test_module_tools.py` fails at collection when run standalone** with `AttributeError: module 'tools.builtin' has no attribute 'module_builder'` — this is a pre-existing gap (confirmed byte-identical to the plan's base commit) where `tools.builtin.module_builder` imports generated gRPC proto modules not present in this worktree. Verified the actual test logic (including the `_approve()` fix above) by manually mocking `sys.modules['llm_service']` etc. before import; all 26 tests pass. Logged to `deferred-items.md`, not fixed (out of scope).
- **`tests/integration/admin/` cannot be collected at all** in this worktree (`ImportError: cannot import name 'llm_pb2'`, then `sandbox_pb2`) — `tests/integration/admin/conftest.py` imports `orchestrator.config_manager`, which pulls in the full `orchestrator` package and its gRPC client dependencies on several `protoc`-generated modules that aren't committed to git (`shared/generated/` contains only `__init__.py`) and aren't present without a Docker build. Confirmed pre-existing and environment-wide (unchanged top-level imports vs. the plan's base commit). Worked around for verification purposes by exercising the modified logic directly via standalone scripts bypassing the orchestrator import chain: `approve_module`/`reject_module` org_id threading + single-designator ISO-8601 timestamps, and the `/audit` mirror's `BuildAuditLog` glob/filter logic — both pass. Logged to `deferred-items.md`, not fixed (out of scope; would require generating protos or restructuring the test's import chain).
- **Accepted a literal-vs-scoped discrepancy in Task 2's acceptance criteria:** the plan states `grep -c "if not _module_loader" tools/builtin/module_installer.py` should return `1`, but the whole-file count is `2` — one inside `install_module` (the IN-03 fix target, now de-duplicated to exactly 1 occurrence) and one, unrelated and pre-existing, inside `uninstall_module` (a different function). Verified via `git show` on the base commit that the file always had 3 total occurrences (2 duplicate + 1 in `uninstall_module`), so the plan's whole-file grep undercounts the pre-existing legitimate guard. Fixed the actual IN-03 defect (duplicate within `install_module`) and left `uninstall_module`'s guard untouched, since removing it would be an unrelated functional change outside this task's scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The approval → install integrity chain is now cryptographically sound end-to-end; downstream plans building UI review flows (08-03, 08-06, 08-08, 08-09) or chat approval (08-10, 08-11) can rely on `approve_module()`'s returned `bundle_sha256` and `manifest.approved_bundle_sha256` without needing further hash-scheme changes
- `queue_for_gc()`'s `Optional[Path]` return and existence guard are ready for 08-04's retention worker to consume safely
- No blockers identified for subsequent phase-8 plans

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-14*

## Self-Check: PASSED

All 14 files referenced above (created + modified) confirmed present on disk. All 3 task commit hashes (`951d9ef`, `f489ddd`, `6c85244`) confirmed present in `git log`.
