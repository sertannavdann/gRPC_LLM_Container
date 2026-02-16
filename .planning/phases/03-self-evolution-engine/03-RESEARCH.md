# Phase 03: Self-Evolution Engine (Track A4) — Research

**Researched:** 2026-02-15  
**Domain:** LLM-driven module generation, sandboxed validation, self-correction loops, adapter test strategy, visualization artifacts, dev-mode governance  
**Confidence:** HIGH

## Executive Summary

Phase 3 is the critical differentiator for NEXUS: transform natural-language requests into installable modules using a deterministic, policy-gated builder pipeline.

Final direction from research:
- Use **GitHub Models API** for backend code generation (structured JSON outputs).
- Keep **Copilot IDE Agent Mode** as human-in-loop tooling, not backend runtime dependency.
- Keep execution model **sandbox-only** for generated code.
- Use **patch-based generation** (`changed_files`) as default backend contract.
- Enforce **bounded self-repair** (max 10 attempts) with immutable artifacts and attestable validation reports.

## Foundation Choice

### Programmatic core
- Primary inference surface: GitHub Models `chat/completions` endpoint.
- Wrapper: internal `LLM Gateway` service to normalize provider calls, budgets, retries, org attribution, and response schema enforcement.
- Fallback chain: configured secondary providers through existing NEXUS provider abstraction.

### Why this is correct
1. Official backend-compatible API surface for inference.
2. Supports structured JSON output contracts (`response_format` with schema).
3. Supports future tool-based mode while keeping patch-based mode stable for MVP.
4. Cleanly integrates into existing orchestrator + metering architecture.

## End-to-End Target Architecture

1. **Build API** accepts NL intent + constraints + idempotency key.
2. **Queue/Worker** dispatches build job attempts.
3. **Build Orchestrator** runs stage flow (`scaffold -> implement -> tests -> repair`).
4. **LLM Gateway** returns schema-valid patch payload.
5. **Policy Engine** checks paths/imports/network/dependency rules.
6. **Sandbox Executor** runs generated code/tests only in isolated runtime.
7. **Validator** merges static + runtime checks into `ValidationReport`.
8. **Installer** enforces `VALIDATED` + attestation guard before installation.
9. **Artifact Store** records prompts, patches, logs, junit, reports per attempt.

## Critical Contracts

### Builder generation contract
Required fields per response:
- `stage`
- `module`
- `changed_files`
- `deleted_files`
- `assumptions`
- `rationale`
- `policy`
- `validation_report`

Hard rules:
- No markdown fences in file content.
- `changed_files` only within allowlisted paths.
- Size/file-count bounded per attempt.
- Reject output if schema invalid.

### Canonical adapter output contract
Use a stable envelope for all adapter executions:
- `contract` (name/version/schema_id)
- `run` (run_id/org/module/version/capability/timestamps)
- `status`
- `data_points[]` (typed payloads)
- `artifacts[]` (charts/files/logs)
- `errors[]` (standardized codes)
- `metering`
- `trace`

This contract becomes the single source for orchestrator, UI, LLM bridge, and analytics.

## Test Strategy (Final Taxonomy)

### Class A — Generic Contract Tests (host-side, fast)
- Registration contract
- Interface contract
- Schema contract
- Error handling contract
- Config/credential contract

### Class B — Feature-Specific Tests (sandbox runtime)
- Connectivity
- Authentication
- Data mapping
- Visualization rendering
- Orchestrator integration
- Dev-mode reload safety

### Quality gate for `VALIDATED`
Hard gate:
- All critical contract tests pass (A1–A5).
- Required feature suites for declared capability/auth type pass.
- No security violations (forbidden imports, secret leakage, SSRF policy breach).

Soft gate:
- Coverage target (>=80%).
- Orchestrator integration round-trip pass.
- Dev-mode hot-reload safety pass.

## API Connectivity & Credential Verification Patterns

Required behavior patterns:
- Connectivity checks support `200` or expected auth-challenge class.
- Auth checks classify `AUTH_INVALID` vs `AUTH_EXPIRED` where detectable.
- Retry policy handles `429/5xx/timeouts` only; no retry on invalid auth.
- Pagination must include loop safeguards (max pages + repeated cursor detection).
- Schema drift classified as additive vs breaking.

## Visualization Validation Framework

Visualization outputs are typed artifacts, not opaque blobs.

### Chart artifact envelope
Includes:
- file metadata (`mime`, `bytes`, `sha256`, dimensions)
- data summary (series names/points/ranges)
- semantic summary (title/labels)
- provenance (engine/version/backend)

### Validation tiers
1. Structural integrity (exists, decodes, metadata sane).
2. Semantic integrity (expected series/data binding present).
3. Optional deterministic rendering (strict image hash mode with pinned backend/fonts).

## Sandbox Security Policy

### Baseline isolation
- Ephemeral execution context per attempt.
- Non-root, read-only root fs, writable tmpfs workdir.
- Resource caps (CPU/memory/timeout/processes).

### Network modes
- Default: no network.
- Integration mode: strict domain allowlist only.

### Import policy
- Deny-by-default.
- Static AST + runtime import hook enforcement.
- Block dynamic/system/exec-risk modules by policy profile.

## Dev-Mode Safe Editing Workflow

### Lifecycle states
`PENDING -> VALIDATED -> INSTALLED -> EDITED -> VALIDATED_Vn -> INSTALLED`
with `FAILED` side-path and pointer-based rollback.

### Required governance
- Drafts are editable but never installable.
- Promotion requires successful revalidation + attested bundle.
- Rollback is version-pointer movement to prior validated version.
- Full audit trail for edit/validate/promote/install/rollback actions.

## Operational Blueprint (Gateway + Routing)

### LLM Gateway responsibilities
- auth token management
- org attribution routing
- model selection by purpose (`codegen`, `repair`, `critic`)
- retries/backoff on transient provider errors
- schema validation of outputs before returning to builder

### Orchestrator loop behavior
- max 10 attempts
- store immutable artifacts each attempt
- feed validator fix hints + logs into repair stage
- stop early on repeated failure fingerprints

## Risks and Mitigations

1. **Provider API instability** → fallback routing + pause/resume job state.
2. **Sandbox nondeterminism** → pinned deps, deterministic fixtures, no-network default.
3. **Secret leakage in logs** → multi-layer redaction (headers/body/url/artifacts).
4. **Contract drift** → single source contract module + schema tests in CI.
5. **Dev-mode bypass risk** → install guard requires validated attestation only.

## Acceptance Mapping

### REQ-013
- NL intent to module scaffolding + implementation + validation + install.
- bounded self-correction loop.
- supports REST/OAuth/pagination/rate-limit + visualization artifacts.

### REQ-016
- generated tests include generic and feature-specific suites.
- deterministic validation artifacts and reports.
- validated-only promotion/install with reproducible bundle identity.
