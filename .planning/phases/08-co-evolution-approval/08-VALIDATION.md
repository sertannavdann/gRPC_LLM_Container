---
phase: 8
slug: co-evolution-approval
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-12
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend) / Playwright (E2E — Wave 0 installs) |
| **Config file** | `pytest.ini` (backend); `ui_service/playwright.config.ts` — none yet, Wave 0 installs |
| **Quick run command** | `python -m pytest tests/unit -x -q` |
| **Full suite command** | `make verify` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit -x -q` (scoped to touched test files)
- **After every plan wave:** Run `make verify`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | — | — | REQ-014, REQ-017, REQ-018, REQ-020 | — | — | — | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `ui_service/playwright.config.ts` + `@playwright/test` devDependency — no Playwright exists anywhere in ui_service (REQ-018)
- [ ] `tests/unit/test_approval_gate.py` — stubs for REQ-014 install-gate assertions
- [ ] `tests/unit/test_retention_worker.py` — stubs for REQ-017 purge policies
- [ ] `tests/unit/test_rate_limit_middleware.py` — stubs for REQ-020 429/Retry-After behavior

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Blueprint card visual quality / coherence | REQ-014 | Aesthetic judgment | Open /pipeline, trigger a build, review pending node + blueprint expansion |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
