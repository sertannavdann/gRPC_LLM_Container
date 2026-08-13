---
phase: 08-co-evolution-approval
reviewed: 2026-08-13T05:04:29Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - shared/modules/approval.py
  - shared/modules/gc.py
  - shared/modules/policy.py
  - orchestrator/admin_api.py
  - tools/builtin/module_installer.py
  - tests/integration/admin/conftest.py
  - tests/integration/admin/test_approval_gate.py
  - tests/integration/cross_feature/test_audit_completeness.py
  - tests/integration/cross_feature/test_hash_chain_integrity.py
  - tests/integration/install/test_validated_only_guard.py
  - tests/unit/modules/test_installer_approval_guard.py
  - tests/unit/test_module_tools.py
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-08-13T05:04:29Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the module approval gate implementation: the `approve_module`/`reject_module`
core (shared/modules/approval.py), the GC marker writer (shared/modules/gc.py), the
ApprovalPolicy scaffold (shared/modules/policy.py), the four RBAC-gated admin
endpoints (orchestrator/admin_api.py), the raised install guard
(tools/builtin/module_installer.py), and the accompanying tests.

The delivered surface largely works: I empirically verified that `install_module`
now rejects a VALIDATED-but-unapproved module, that `approve_module` transitions
VALIDATED→APPROVED, that terminal reject moves to FAILED and writes a `.gc_pending`
marker, and that RBAC gates behave (viewer/operator forbidden on approve/reject).
Unit suites pass (8 + 26).

However, adversarial tracing surfaced a real correctness contradiction between the
approval step and the install-time bundle-hash guard, plus several accountability and
test-coverage defects. Key concerns below.

## Critical Issues

### CR-01: Approval mutates the hashed manifest.json, so attestation-verified install of an approved module always fails the hash check

**File:** `shared/modules/approval.py:100-101`, cross-referenced with `tools/builtin/module_installer.py:110-160`

**Issue:** The install-time integrity guard recomputes a bundle hash over
`adapter.py`, `test_adapter.py`, **and `manifest.json`** and compares it to the
attestation's `bundle_sha256` (module_installer.py:132-160). But `approve_module`
rewrites `manifest.json` — it flips `manifest.status` VALIDATED→APPROVED and
`manifest.save()` also refreshes `updated_at` (manifest.py:118-120). Both fields are
inside the hashed bundle. Therefore any attestation captured while the module was
VALIDATED can **never** match the bundle after approval, and an attestation-carrying
install of a legitimately-approved module is rejected with
"Artifact integrity failure: bundle hash mismatch."

I confirmed this empirically: validate-time attestation → `approve_module()` →
`install_module(module_id, attestation)` returns
`status=error, "Artifact integrity failure ... bundle hash mismatch"`.

The two phase-touched invariants are mutually contradictory by construction:
"approval must rewrite the manifest" vs "install must verify the manifest is
byte-identical to what was validated." The integration tests do **not** catch this
because `create_test_module(..., ModuleStatus.APPROVED.value)` creates the module
already in APPROVED state and computes `bundle_hash` from that post-approval state
(test_hash_chain_integrity.py:31-35, test_audit_completeness.py:159-164) — they never
exercise the real validate→approve→install transition, so the attestation always
matches artificially. This gives false confidence that hash-verified install of
approved modules works.

**Fix:** Exclude `manifest.json` from the hashed bundle (hash only the code
artifacts, `adapter.py`/`test_adapter.py`), so status transitions do not invalidate
attestations. Alternatively, re-issue the attestation at approval time and have
`approve_module` return the new `bundle_sha256`. Then add an integration test that
runs the full `validate_module → approve_module → install_module(attestation)` chain
against a single on-disk module (not a pre-fabricated APPROVED fixture) to lock the
invariant:
```python
# hash only immutable code artifacts, not the mutable manifest
for filename in ("adapter.py", "test_adapter.py"):
    ...
```

## Warnings

### WR-01: Install hash verification is optional, so a module tampered after approval installs arbitrary code in the default call path

**File:** `tools/builtin/module_installer.py:111`

**Issue:** The bundle-hash check is guarded by `if validation_attestation:`. Every
live caller (chat tools, `drafts.py` flow) calls `install_module(module_id)` with **no
attestation**, so the hash verification is skipped entirely. I verified that after
approval I can overwrite `adapter.py` with `import os; os.system('pwned')` and
`install_module("test/demo")` (no attestation) returns `status=success` and hot-loads
the tampered code. The module docstring advertises "Hash verification: bundle_sha256
must match validation attestation" and "only APPROVED bundles can be installed" as
security features, but neither prevents post-approval tampering in the default path.
This is pre-existing behavior, but the phase re-touched this security docstring/guard
and the approval gate's whole point (D-16) is a trustworthy install path.

**Fix:** Recompute and verify the bundle hash unconditionally at install time against
the hash recorded at approval (see CR-01), rather than only when an optional
attestation object is passed. Reject install if the on-disk artifacts differ from what
the admin approved.

### WR-02: Audit trail records the organization id, not the individual admin, defeating D-19 accountability

**File:** `orchestrator/admin_api.py:822`, `orchestrator/admin_api.py:854`

**Issue:** Both endpoints pass `actor=user.org_id` into `approve_module`/`reject_module`.
`org_id` identifies the tenant organization, not the person. The `User` model carries a
distinct `user_id` (models.py:28; populated by `validate_key`, api_keys.py:139-142). The
approval-core docstrings explicitly promise "actor: Identity of the approving admin"
(approval.py:76, 145) and D-19 requires recording who approved. As written, every admin
in an org is indistinguishable in the audit log, so the audit trail cannot attribute an
approve/reject to a specific operator.

**Fix:** Record the individual identity:
```python
actor=user.user_id,   # was user.org_id
```
(Optionally include `org_id` in the audit `details` for tenant context.)

### WR-03: Malformed ISO-8601 timestamps (`+00:00Z`) written into audit details and GC markers

**File:** `shared/modules/approval.py:103`, `shared/modules/approval.py:157`, `shared/modules/gc.py:52`

**Issue:** `datetime.now(timezone.utc).isoformat() + "Z"` produces
`2026-08-13T05:02:55.666960+00:00Z` — the offset `+00:00` and the trailing `Z` are two
mutually-exclusive UTC designators, so the string is not valid ISO-8601. These strings
land in the D-19 audit `details.timestamp` and in the `.gc_pending` marker's
`rejected_at`. Strict parsers (including `datetime.fromisoformat` on some versions and
the GC/retention worker in 08-02 that will consume `rejected_at`) will reject or
mis-handle them.

**Fix:** Emit exactly one designator:
```python
timestamp = datetime.now(timezone.utc).isoformat()          # -> ...+00:00
# or, for a Z suffix:
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

### WR-04: Production `/audit` endpoint is effectively untested — the integration mirror uses a different data source

**File:** `tests/integration/admin/conftest.py:392-412` vs `orchestrator/admin_api.py:889-915`

**Issue:** The real `/admin/modules/{c}/{p}/audit` endpoint globs `AUDIT_DIR` for
`*_audit.json` files, loads each via `BuildAuditLog.load`, filters by
`log.module_id == module_id`, and returns build **attempt** records. The test factory's
mirror instead calls `app.state.audit_log.get_events(module_id=...)` on a
`DevModeAuditLog` and returns approve/reject **events**. These are different
implementations reading different stores, so `test_audit_operator_allowed` exercises
the mock, not the shipped endpoint. The production audit query (glob, `BuildAuditLog`
loading, module_id filtering) has zero coverage and could silently break.

**Fix:** Make the test mirror faithful to the production implementation (glob
`*_audit.json` via `BuildAuditLog.load`), or better, exercise the real
`orchestrator/admin_api.py` app so the endpoint under test is the one that ships.

### WR-05: Inconsistent default `AUDIT_DIR` causes the audit endpoint to look in the wrong directory

**File:** `orchestrator/admin_api.py:906`

**Issue:** The `/audit` endpoint defaults `AUDIT_DIR` to `/app/data/audit`, whereas the
installer (module_installer.py:30) and orchestrator DevMode audit
(orchestrator_service.py:981,1816) default to `data/audit`. When `AUDIT_DIR` is unset,
the audit endpoint globs a different (likely empty/nonexistent) directory than where
build audit files are actually written, so it returns no attempts even when records
exist.

**Fix:** Use a single shared default. Match the rest of the codebase
(`os.getenv("AUDIT_DIR", "data/audit")`) or centralize the default in one constant.

## Info

### IN-01: Unused import `ModuleStatus` in admin_api.py

**File:** `orchestrator/admin_api.py:31`

**Issue:** `ModuleStatus` is imported alongside `ModuleManifest` but never referenced in
the file (only `ModuleManifest.load` is used, in the review endpoint).

**Fix:** Drop `ModuleStatus` from the import: `from shared.modules.manifest import ModuleManifest`.

### IN-02: `/review` endpoint reads a manifest field that does not exist

**File:** `orchestrator/admin_api.py:876`

**Issue:** `getattr(manifest, "walkthrough", "")` — `ModuleManifest` has no
`walkthrough` field, so this always returns the empty-string default. The review UI
will never receive a walkthrough. Either the manifest is missing the field or the
endpoint references the wrong attribute.

**Fix:** Add a `walkthrough` field to `ModuleManifest` if a walkthrough is intended, or
remove the dead reference from the review payload.

### IN-03: Duplicate `if not _module_loader` guard in install_module (dead code)

**File:** `tools/builtin/module_installer.py:162-168`

**Issue:** The same `if not _module_loader: return {...}` check appears twice
back-to-back (lines 162-163 and 167-168). The second is unreachable. Pre-existing, but
in a file the phase edited.

**Fix:** Delete the duplicated block (lines 167-168).

### IN-04: `queue_for_gc` silently creates a directory for a bogus module_id

**File:** `shared/modules/gc.py:47-48`

**Issue:** `module_dir.mkdir(parents=True, exist_ok=True)` will fabricate a module
directory (and write a `.gc_pending` marker into it) even if `module_id` refers to a
module that never existed. A caller passing a typo'd id creates a phantom directory
that the 08-02 retention worker may later act on.

**Fix:** Require the module directory to already exist before writing the marker (raise
or return an error if it does not), rather than creating it implicitly.

---

_Reviewed: 2026-08-13T05:04:29Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
