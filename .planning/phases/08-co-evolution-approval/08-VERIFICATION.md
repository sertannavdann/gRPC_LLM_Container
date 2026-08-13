---
phase: 08-co-evolution-approval
verified: 2026-08-13T05:13:39Z
status: gaps_found
score: 6/13 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Module approval gates UI (REQ-014) — review code, credentials, sandbox results before install"
    status: failed
    reason: "Only the backend enforcement slice (plan 08-01) has been executed. No UI component exists for reviewing generated code, credentials, or sandbox results, and no chat approval strategy exists. Plans 08-04 through 08-08 (which the phase's own source_audit assigns this scope to) have not been written or executed."
    artifacts:
      - path: "ui_service/src/components"
        issue: "grep for approve/reject UI turns up only the generic chat tool-call ActionCard.tsx, unrelated to module review; no module-review, blueprint, walkthrough, or credential-review components exist"
    missing:
      - "Module review UI (code diff, credential list, sandbox/test results, five review layers per D-06)"
      - "Pipeline page wiring for pending-approval node + approve/reject actions (D-01, D-04, D-05)"
      - "Chat-based approval strategy (D-02)"
  - truth: "Tiered trace retention (REQ-017) — per-org retention policies + background cleanup worker"
    status: failed
    reason: "No retention worker, no per-org retention policy config, and no Prometheus retention-flag wiring exist anywhere in the codebase. shared/modules/gc.py (created in 08-01, ahead of schedule) only writes a .gc_pending marker file — it explicitly does not implement sweep/purge logic. Plan 08-02, which owns this scope, has not been written or executed."
    artifacts:
      - path: "shared/modules/gc.py"
        issue: "Marker-write only (queue_for_gc); no consumer/sweep worker exists to act on .gc_pending markers or any other retention tier"
    missing:
      - "Background cleanup worker (daily sweep)"
      - "Per-org retention tier configuration (Free 7d / Team 90d / Enterprise unlimited)"
      - "Prometheus retention flag wiring"
  - truth: "Pipeline SSE E2E tests (REQ-018) — Playwright tests for reconnection logic"
    status: failed
    reason: "No Playwright test files exist in the repository (only vendored node_modules/next Playwright testmode shims, not project tests). Plan 08-09, which owns this scope, has not been written or executed."
    missing:
      - "Playwright test suite covering initial connect, reconnect after dashboard restart, and error handling on SSE failure"
  - truth: "Rate limiting (REQ-020) — token bucket with 429 + Retry-After on all HTTP endpoints"
    status: failed
    reason: "No token-bucket/rate-limit middleware exists on any FastAPI app (orchestrator/admin_api.py, dashboard_service). shared/utils/rate_limiter.py and hits in shared/providers/* are outbound-provider throttling for LLM API calls, unrelated to inbound HTTP request rate limiting. No 429/Retry-After behavior found on any endpoint, including the four new approve/reject/review/audit endpoints this phase added. Plan 08-03, which owns this scope, has not been written or executed."
    missing:
      - "Token bucket (Redis-backed or in-memory) middleware applied to all HTTP endpoints"
      - "429 response with Retry-After header on limit exceeded"
  - truth: "Done Criteria: No module installed without explicit user approval"
    status: failed
    reason: "The status guard itself works (install_module() requires ModuleStatus.APPROVED, confirmed by passing unit tests and direct grep). However, code review CR-01 (confirmed empirically by this verifier — see below) shows the install-time attestation path is broken by construction: approve_module() mutates manifest.json (status + updated_at), which is part of the hashed bundle the installer's attestation check recomputes. Any attestation captured at validate time can never match the bundle after approval, so the one path that would cryptographically prove 'this exact approved code is what gets installed' always fails with a false hash-mismatch error. Combined with WR-01 (bundle-hash verification is entirely skipped when no attestation is passed — the path every live caller actually uses), the practical guarantee reduces to 'a status flag was flipped by an admin,' with no integrity binding between what was approved and what gets installed. A module could be approved, then have adapter.py silently modified before install, and the default (unattested) install path would accept it without detection."
    artifacts:
      - path: "shared/modules/approval.py"
        issue: "approve_module() (lines 100-101) mutates manifest.json fields that are included in the hashed bundle computed by tools/builtin/module_installer.py's attestation check (lines 110-160), making the attested-install path permanently non-functional for any module that goes through approval"
      - path: "tools/builtin/module_installer.py"
        issue: "Hash verification (lines 111-160) is entirely skipped when validation_attestation is None (WR-01) — the default and only path used by all current live callers — so post-approval tampering is undetected in practice"
    missing:
      - "Bundle hash computed excluding manifest.json (or re-issued at approval time) so attestation-verified install of an approved module succeeds"
      - "Unconditional hash verification at install time (not gated behind an optional attestation argument) so post-approval tampering is actually caught"
  - truth: "Done Criteria: Traces auto-purge per retention policy"
    status: failed
    reason: "No retention policy or purge mechanism of any kind exists in the codebase (same root cause as the REQ-017 gap above)."
    missing:
      - "Same as REQ-017 gap: background cleanup worker + per-org policy"
  - truth: "Every approve and reject decision is recorded with actor, timestamp, and bundle hash (D-19)"
    status: failed
    reason: "Fields exist and are populated (verified by reading orchestrator/admin_api.py:821-857 and shared/modules/approval.py), but code review WR-02 (confirmed by this verifier by reading the exact lines) shows 'actor' is populated with user.org_id, not the individual admin's user_id — every admin within an organization is audit-indistinguishable, directly contradicting approval.py's own docstring promise ('actor: Identity of the approving admin') and D-19's accountability intent. Additionally WR-03 (confirmed by reading approval.py:103 and gc.py:52): timestamps are emitted as `<isoformat>+00:00Z`, which is not valid ISO-8601 (both a numeric offset and a Z designator are present) — this will break strict parsers, including the retention worker (08-02, not yet built) that is expected to consume `rejected_at` from the GC marker."
    artifacts:
      - path: "orchestrator/admin_api.py"
        issue: "Lines 823 and 855 pass actor=user.org_id (tenant identity) instead of user.user_id (individual identity) into approve_module/reject_module"
      - path: "shared/modules/approval.py"
        issue: "Lines 103, 157 (and shared/modules/gc.py:52) construct malformed ISO-8601 timestamps via isoformat() + \"Z\" while isoformat() already includes a +00:00 offset"
    missing:
      - "actor=user.user_id (individual identity) passed to approve_module/reject_module"
      - "Single, valid ISO-8601 timestamp format (either offset OR Z suffix, not both)"
deferred: []
---

# Phase 8: Co-Evolution & Approval — Verification Report

**Phase Goal:** Module approval gates UI (REQ-014), tiered trace retention (REQ-017), Pipeline SSE E2E tests (REQ-018), rate limiting (REQ-020). Done criteria: "No module installed without explicit user approval" and "Traces auto-purge per retention policy."
**Verified:** 2026-08-13T05:13:39Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Scope Note

Only plan `08-01-PLAN.md` (backend enforcement core of the approval gate) has been written and executed for this phase. Plans `08-02` through `08-09` — which `08-01-PLAN.md`'s own `<source_audit>` table assigns the remaining phase scope to (retention worker, rate limiting, Pipeline UI wiring, chat approval strategy, SSE E2E tests) — do not exist as PLAN files yet. This verification therefore covers two layers:

1. **08-01's own must-haves** (PT1–PT7 below) — verified against the actual codebase, not SUMMARY.md claims.
2. **The full phase goal / roadmap done-criteria** (RT1–RT6 below) — verified against the actual codebase to honestly report the phase-level gap. These are **not** treated as "deferred to a later phase" per the verification process's Step 9b, because 08-02–08-09 are unwritten sub-plans of *this same phase* (08), not later phases in the milestone roadmap — there is no roadmap evidence of a later phase absorbing this scope.

## Goal Achievement

### Observable Truths — Phase-Level (Roadmap Done Criteria + Deliverables)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| RT1 | Module approval gates UI (REQ-014) — review code/credentials/sandbox results before install | ✗ FAILED | No UI component exists; only the unrelated generic chat `ActionCard.tsx` matched a grep for approve/reject in `ui_service/src` |
| RT2 | Tiered trace retention (REQ-017) — per-org policy + cleanup worker | ✗ FAILED | No retention worker, no per-org policy config anywhere in repo; `shared/modules/gc.py` only writes a marker file, explicitly scoped (by its own docstring) to NOT include sweep logic |
| RT3 | Pipeline SSE E2E tests (REQ-018) — Playwright reconnection tests | ✗ FAILED | No project Playwright spec files found (`find` for `*.spec.ts` under pipeline paths returned nothing; only vendored `node_modules/next` Playwright shims exist) |
| RT4 | Rate limiting (REQ-020) — token bucket, 429 + Retry-After on all HTTP endpoints | ✗ FAILED | No inbound HTTP rate-limit middleware found on `orchestrator/admin_api.py` or `dashboard_service`; existing `rate_limiter.py`/provider hits are outbound LLM-provider throttling, unrelated |
| RT5 | Done: No module installed without explicit user approval | ✗ FAILED | Status guard itself works (see PT1), but empirically confirmed CR-01 (attestation-verified install of a legitimately approved module always fails hash check) + WR-01 (hash check skipped entirely on the default no-attestation path used by all live callers) together mean the "approval" the guard enforces has no cryptographic binding to what actually gets installed — see reproduction below |
| RT6 | Done: Traces auto-purge per retention policy | ✗ FAILED | Same as RT2 — no purge mechanism exists |

**Score:** 0/6 phase-level truths verified.

### Observable Truths — Plan 08-01's Own Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| PT1 | `install_module()` refuses to install any module whose status is not APPROVED (D-16) | ✓ VERIFIED | `tools/builtin/module_installer.py:98` guard compares `ModuleStatus.APPROVED`; `_log_install_rejection(module_id, "not_approved", ...)` at line 100; `tests/unit/modules/test_installer_approval_guard.py` — 8/8 pass (`python -m pytest tests/unit/modules/test_installer_approval_guard.py -q` → `8 passed`) |
| PT2 | Admin (WRITE_CONFIG) can approve a VALIDATED module → APPROVED (D-16/D-17) | ✓ VERIFIED | `shared/modules/approval.py:60-117` `approve_module()` guards `manifest.status == VALIDATED`, sets `APPROVED`, saves; empirically reproduced with a temp module dir (see RT5 evidence) — transition confirmed to succeed |
| PT3 | Approve/reject below admin+ role returns 403 (D-17) | ✓ VERIFIED | Both endpoints gated by `Depends(require_permission(Permission.WRITE_CONFIG))` (`orchestrator/admin_api.py:814,839`); `shared/auth/rbac.py:48-54` `require_permission` raises `HTTPException(403, ...)` when the role lacks the permission — same proven decorator pattern already used and tested for sibling draft/version endpoints. Live integration assertion (`tests/integration/admin/test_approval_gate.py`) is present but **skips** (17/17 skipped) — this is the documented pre-existing Docker/gRPC-on-50054 environment gate (confirmed identical skip behavior on sibling `test_module_crud.py`), not an implementation failure |
| PT4 | Reject-with-feedback → one bounded repair cycle, returns to pending approval (VALIDATING) (D-09) | ✓ VERIFIED | `shared/modules/approval.py:160-205` sets `ModuleStatus.VALIDATING`, calls `repair_module()` inside try/except (best-effort), logs `module_rejected` with `terminal: False` |
| PT5 | Reject-without-feedback is terminal: FAILED + queued for GC (D-09/D-10) | ✓ VERIFIED | `shared/modules/approval.py:207-222` sets `ModuleStatus.FAILED`, calls `queue_for_gc()` (imported from `shared/modules/gc.py`), logs `module_rejected` with `terminal: True`; `shared/modules/gc.py:23-61` writes `.gc_pending` marker JSON |
| PT6 | Every approve/reject decision recorded with actor, timestamp, bundle hash (D-19) | ✗ FAILED | Fields exist and are non-null, but **WR-02** (confirmed by reading `orchestrator/admin_api.py:823,855`): `actor=user.org_id` (tenant, not individual) — contradicts `approval.py`'s own docstring ("actor: Identity of the approving admin") and defeats per-admin accountability. **WR-03** (confirmed by reading `approval.py:103,157` and `gc.py:52`): `isoformat() + "Z"` produces malformed timestamps like `...+00:00Z` (two conflicting UTC designators) |
| PT7 | `ApprovalPolicy` config object exists, `auto_approve` defaults to False (D-18) | ✓ VERIFIED | `shared/modules/policy.py:16-29`; `python -c "from shared.modules.policy import ApprovalPolicy; assert ApprovalPolicy().auto_approve is False"` exits 0; no `from __future__ import annotations` present (grep count 0, avoiding the known Pydantic gotcha) |

**Score:** 6/7 plan-08-01 truths verified.

**Combined score: 6/13 must-haves verified.**

### CR-01 Reproduction (independent, by this verifier)

Built a temp module (VALIDATED status), computed an attestation hash the way `validate_module()` would, called `approve_module()`, then called `install_module(module_id, validation_attestation=attestation)`:

```
Attestation hash at validate time: 0f565cdb...71453fc
approve_module result: {'status': 'success', 'module_id': 'test/cr01demo', 'new_status': 'approved'}
install_module (with attestation) result: {'status': 'error', 'error': 'Artifact integrity failure: bundle hash mismatch.
  Expected 0f565cdb...71453fc, got c307f545...45bd47533. Files may have been modified after validation.'}
```

This confirms code review finding CR-01 independently: a legitimately validated-then-approved module, installed via the attestation-verified path with zero tampering, is rejected. Root cause: `approve_module()`'s `manifest.save()` mutates `manifest.json` (status + `updated_at`), and `manifest.json` is one of the three files hashed into the bundle both at validate-time attestation and at install-time verification.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `shared/modules/policy.py` | `ApprovalPolicy` Pydantic model, `auto_approve=False` hard default | ✓ VERIFIED | Present, substantive, no dataclass/future-annotations pitfall |
| `shared/modules/approval.py` | `approve_module`/`reject_module` core functions | ✓ VERIFIED | Both present, wired into `orchestrator/admin_api.py` endpoints via direct import |
| `orchestrator/admin_api.py` | POST approve/reject + GET review/audit endpoints | ✓ VERIFIED | Four endpoints present at lines 810-925, RBAC-gated, wired to `approval.py` functions |
| `tools/builtin/module_installer.py` | Install guard raised to APPROVED | ✓ VERIFIED | Confirmed via grep + reproduction above |
| `shared/modules/gc.py` | GC marker contract (pre-authorized early deliverable of 08-02's scope) | ⚠️ PARTIAL | Marker-write only, as scoped — no sweep/consumer worker exists yet (that remains unbuilt 08-02 scope, tracked as RT2/RT6 gap) |
| Module approval gate UI (any `ui_service` component) | Code/credential/sandbox review surface | ✗ MISSING | No such component exists anywhere in `ui_service/src` |
| Retention/cleanup worker | Background daily sweep process | ✗ MISSING | Does not exist |
| Rate-limit middleware | Token bucket on HTTP endpoints | ✗ MISSING | Does not exist |
| Playwright E2E test suite | Pipeline SSE reconnection tests | ✗ MISSING | Does not exist |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `orchestrator/admin_api.py` approve/reject endpoints | `shared/modules/approval.py` | direct function call after RBAC dependency resolves | ✓ WIRED | `admin_api.py:821-826,852-858` call `approve_module`/`reject_module` directly |
| `shared/modules/approval.py reject_module` (no feedback) | `shared/modules/gc.py queue_for_gc` | import + call in terminal-reject branch | ✓ WIRED | `approval.py:14,211` |
| `tools/builtin/module_installer.py` install guard | `shared.modules.manifest.ModuleStatus.APPROVED` | status comparison before install | ✓ WIRED | `module_installer.py:98` |
| `shared/modules/approval.py approve_module` (mutates manifest) | `tools/builtin/module_installer.py` attestation hash check | shared hashed-bundle contents (manifest.json) | ✗ BROKEN | CR-01 — the two sides of this link compute hashes over mutually-incompatible manifest states; see reproduction above |

### Requirements Coverage

| Requirement | Source Plan | Description (REQUIREMENTS.md) | Status | Evidence |
|-------------|------------|-------------------------------|--------|----------|
| REQ-014 | 08-01 (declared) | "UI review of generated code + required credentials + sandbox test results; approve/reject with feedback loop" | ⚠️ PARTIAL | Backend approve/reject/feedback-loop mechanics delivered and functionally correct (PT1-PT5, PT7); the "UI review" half of the requirement — which is explicitly in the requirement text — is entirely unbuilt (RT1). Requirement cannot be marked SATISFIED on its literal text. |
| REQ-017 | **none** | "Prometheus retention flags per org; background cleanup worker prunes expired data daily" | ✗ ORPHANED / BLOCKED | Mapped to phase 08 in REQUIREMENTS.md but not claimed by any existing PLAN's `requirements` frontmatter (only 08-01 exists, and it declares only `["REQ-014"]`). No implementation exists (RT2). |
| REQ-018 | **none** | "Playwright tests verify: initial connect, reconnect after dashboard restart, error handling on SSE failure" | ✗ ORPHANED / BLOCKED | Mapped to phase 08 in REQUIREMENTS.md but not claimed by any existing PLAN. No implementation exists (RT3). |
| REQ-020 | **none** | "Redis-backed or in-memory token bucket; configurable per-endpoint; returns 429 with Retry-After header" | ✗ ORPHANED / BLOCKED | Mapped to phase 08 in REQUIREMENTS.md but not claimed by any existing PLAN. No implementation exists (RT4). |

**Note:** REQ-017, REQ-018, REQ-020 being unclaimed by any PLAN is expected at this point in the phase's lifecycle (only wave/plan 08-01 of what `08-01-PLAN.md`'s own `<source_audit>` describes as a 9-plan phase has been written), but per verification instructions every requirement ID mapped to this phase in REQUIREMENTS.md must be accounted for here regardless of plan-authoring state.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `shared/modules/approval.py` / `tools/builtin/module_installer.py` | approval.py:100-101, installer.py:110-160 | Attestation hash includes a field (`manifest.json`) that approval itself mutates | 🛑 Blocker | CR-01 — approved-module attested install path is permanently broken (reproduced independently above) |
| `tools/builtin/module_installer.py` | 111 | Hash verification only runs `if validation_attestation:` — optional, and unused by all live callers | 🛑 Blocker (compounds CR-01) | WR-01 — post-approval tampering undetected in the actual (default) install path |
| `orchestrator/admin_api.py` | 823, 855 | `actor=user.org_id` instead of `user.user_id` | ⚠️ Warning | WR-02 — audit trail cannot attribute approve/reject to an individual admin, contradicting D-19 intent and the function's own docstring |
| `shared/modules/approval.py`, `shared/modules/gc.py` | approval.py:103,157; gc.py:52 | `datetime.now(timezone.utc).isoformat() + "Z"` — malformed ISO-8601 (`+00:00Z`) | ⚠️ Warning | WR-03 — downstream strict parsers (including the not-yet-built 08-02 retention worker, which is documented to consume `rejected_at`) may reject/mis-handle these timestamps |
| `tests/integration/admin/conftest.py` vs `orchestrator/admin_api.py` | conftest.py:392-412 vs admin_api.py:889-915 | Test mirror of `/audit` reads a different data source (`DevModeAuditLog.get_events`) than the production endpoint (`BuildAuditLog.load` glob over `AUDIT_DIR`) | ⚠️ Warning | WR-04 — the shipped `/audit` endpoint has zero test coverage; only the mock is exercised |
| `orchestrator/admin_api.py` | 906 (approx) | `/audit` endpoint defaults `AUDIT_DIR` to `/app/data/audit`, inconsistent with the rest of the codebase's `data/audit` default | ⚠️ Warning | WR-05 — in non-container/dev environments the audit endpoint silently globs an empty directory |
| `orchestrator/admin_api.py` | 886 | `getattr(manifest, "walkthrough", "")` — field does not exist on `ModuleManifest` | ℹ️ Info | IN-02 — always returns empty string; expected/acceptable since `walkthrough` is explicitly 08-04's scope, not 08-01's |
| `orchestrator/admin_api.py` | 31 | Unused `ModuleStatus` import | ℹ️ Info | IN-01 — cosmetic |
| `tools/builtin/module_installer.py` | 162-168 | Duplicate `if not _module_loader` guard | ℹ️ Info | IN-03 — pre-existing dead code, not introduced by this phase |
| `shared/modules/gc.py` | 47-48 | `mkdir(parents=True, exist_ok=True)` creates a phantom module directory for a bogus/typo'd `module_id` | ℹ️ Info | IN-04 — minor robustness gap |

No `TBD`/`FIXME`/`XXX` debt markers found in any file touched by this phase.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit test suite for install guard + policy scaffold | `python -m pytest tests/unit/modules/test_installer_approval_guard.py -q` | `8 passed` | ✓ PASS |
| Integration test suite for approve/reject/review/audit endpoints | `python -m pytest tests/integration/admin/test_approval_gate.py -q` | `17 skipped` | ? SKIP — pre-existing Docker/gRPC-on-50054 environment gate (autouse `test_environment` fixture), not an implementation failure; identical skip behavior confirmed on sibling `test_module_crud.py` |
| CR-01 reproduction (attested install of approved module) | custom script, temp module dir | `install_module` returns `status=error, "Artifact integrity failure: bundle hash mismatch"` after a clean approve with zero tampering | ✗ FAIL — confirms CR-01 independently |

### Probe Execution

No `scripts/*/tests/probe-*.sh` files referenced by this phase's PLAN/SUMMARY. Step 7c: SKIPPED (no declared or conventional probes for this phase).

### Human Verification Required

### 1. Live RBAC integration test run

**Test:** Run `make up` (or otherwise bring the orchestrator gRPC service up on port 50054), then `python -m pytest tests/integration/admin/test_approval_gate.py -v`.
**Expected:** All 17 tests pass, confirming 403 for viewer/operator and 200 for admin on approve/reject, and correct payload shape for review/audit reads.
**Why human:** Requires starting the Docker Compose stack, which this verifier's sandboxed environment does not have running; the code-path is verified statically (RBAC decorator pattern, function wiring) but not exercised end-to-end.

### 2. CR-01 fix validation once addressed

**Test:** After a fix (e.g., excluding `manifest.json` from the hashed bundle, or re-issuing the attestation at approval time), re-run the CR-01 reproduction: validate → approve → install with attestation, on a real on-disk module.
**Expected:** Install succeeds without a false hash-mismatch.
**Why human:** Requires a design decision (which of the two fixes in the code review's suggested remediation to take) before it can be re-verified.

## Gaps Summary

Plan 08-01 delivered a functionally mostly-correct backend enforcement slice for module approval (6/7 of its own must-haves verified), but the **phase itself is far from its goal**: 3 of 4 roadmap deliverables (module approval UI, tiered trace retention, rate limiting, Pipeline SSE E2E tests — all of REQ-017/018/020 and the UI half of REQ-014) have zero implementation, because plans 08-02 through 08-09 have not yet been written or executed. Additionally, a confirmed critical defect (CR-01, independently reproduced by this verifier) means the one security property the completed slice is supposed to deliver — "an approved module's exact, attested code gets installed" — does not actually hold: the attested path always fails, and the default unattested path (used by every live caller) performs no integrity check at all. A secondary defect (WR-02) means the audit trail cannot attribute approve/reject decisions to an individual admin, only to their organization.

**Recommendation:** Do not mark the phase complete. Plan and execute 08-02 (retention worker), 08-03 (rate limiting), and the UI-facing plans (08-04 through 08-08) before re-verifying the phase-level done criteria. Independently, before or alongside that work, fix CR-01 (exclude `manifest.json` from the hashed bundle, or re-issue attestation at approval time) and WR-02 (use `user.user_id` for `actor`) — both are narrow, well-scoped fixes that do not require new plans and should not block progress on the remaining phase scope.

---

*Verified: 2026-08-13T05:13:39Z*
*Verifier: Claude (gsd-verifier)*
