---
phase: 03-self-evolution-engine
plan: 01
subsystem: module-contracts
tags: [contracts, schema, validation, artifact-bundling]
dependency_graph:
  requires: []
  provides:
    - manifest_schema.json
    - contracts.py (AdapterContractSpec, GeneratorResponseContract)
    - artifacts.py (ArtifactBundleBuilder, ArtifactIndex)
    - output_contract.py (AdapterRunResult)
  affects:
    - tools/builtin/module_builder.py
    - orchestrator/orchestrator_service.py
    - tools/builtin/module_installer.py
tech_stack:
  added:
    - jsonschema (manifest validation)
    - Pydantic v2 (contract models)
    - hashlib.sha256 (content addressing)
  patterns:
    - AST-based static analysis
    - Content-addressed artifacts
    - Canonical envelope pattern
key_files:
  created:
    - shared/modules/manifest_schema.json
    - shared/modules/contracts.py
    - shared/modules/artifacts.py
    - shared/modules/output_contract.py
    - tests/unit/modules/test_manifest_schema.py
    - tests/unit/modules/test_contracts_static.py
    - tests/unit/modules/test_artifact_bundle.py
    - tests/unit/modules/test_output_contract.py
  modified: []
decisions:
  - decision: "Use JSON Schema for manifest validation instead of Pydantic"
    rationale: "JSON Schema provides versioned $id for schema evolution tracking and is language-agnostic"
  - decision: "Use ClassVar for Pydantic model constants instead of instance fields"
    rationale: "Pydantic v2 requires ClassVar annotation for class-level constants to avoid field conflicts"
  - decision: "Separate adapter contract (static validation) from generator contract (LLM output validation)"
    rationale: "Different validation contexts require different rules - adapter.py uses AST, generator uses Pydantic"
  - decision: "Content-address artifacts with SHA-256 before install"
    rationale: "Provides immutable identity for audit trail and enables diffing between attempts"
metrics:
  duration: 449s
  tasks_completed: 4
  files_created: 8
  tests_added: 106
  commits: 4
  completed_at: "2026-02-16T00:10:48Z"
---

# Phase 03 Plan 01: Core Contracts Summary

JWT-style contracts freeze module layout, generator output schema, artifact bundling, and canonical run-result envelope as single sources of truth.

## What Was Built

### 1. Manifest JSON Schema (Task 1)
- **File**: `shared/modules/manifest_schema.json`
- **Purpose**: Versioned schema for module `manifest.json` files
- **Features**:
  - Required fields: `module_id`, `version`, `category`, `platform`, `entrypoint`, `capabilities`
  - Optional fields: `auth`, `pagination`, `rate_limits`, `outputs`, `artifacts`, `description`
  - Strict `additionalProperties: false` enforcement
  - Versioned `$id`: `https://nexus.dev/schemas/module-manifest/v1.0.0`
  - Semantic version validation (`MAJOR.MINOR.PATCH`)
  - Module ID format validation (`category/platform`)
- **Tests**: 22 tests validate correct manifests pass, invalid are rejected

### 2. Builder & Adapter Contracts (Task 2)
- **File**: `shared/modules/contracts.py`
- **Purpose**: Contract specifications for adapter.py files and LLM generator outputs

**AdapterContractSpec**:
- Required methods: `fetch_raw`, `transform`, `get_schema`
- Forbidden imports: `subprocess`, `eval`, `exec`, `os.system`, `__import__`, `compile`
- Required decorator: `@register_adapter`
- AST-based static validation

**GeneratorResponseContract** (Pydantic):
- Required fields: `stage`, `module`, `changed_files`, `deleted_files`, `assumptions`, `rationale`, `policy`, `validation_report`
- **Critical rule**: No markdown fences (` ``` `) in file content
- Path allowlist enforcement (only module directory paths)
- Size limits: max 10 changed files, max 100KB per file
- Validation helper: `validate_generator_response()`

- **Tests**: 31 tests validate all contract invariants

### 3. Content-Addressed Artifact Bundles (Task 3)
- **File**: `shared/modules/artifacts.py`
- **Purpose**: Deterministic, immutable artifact bundling

**ArtifactBundleBuilder**:
- Deterministic file ordering (sorted by path)
- SHA-256 hash per file
- SHA-256 bundle hash from concatenated file hashes
- `build_from_dict()`: create bundle from file dictionary
- `build_from_directory()`: create bundle from directory
- `self_check()`: proves determinism (same content → same hash)
- `diff_bundles()`: compare two bundles (added/deleted/changed files)

**ArtifactIndex**:
- Persistent metadata: `job_id`, `attempt_id`, `bundle_sha256`, `files[]`, `created_at`
- Optional: `module_id`, `stage`
- Serializable to/from dictionary

- **Tests**: 26 tests validate determinism, comparison, and verification

### 4. Canonical Adapter Output Envelope (Task 4)
- **File**: `shared/modules/output_contract.py`
- **Purpose**: Single source of truth for adapter outputs consumed by orchestrator, bridge, UI, metering

**AdapterRunResult** (Pydantic):
- **Contract metadata**: `name`, `version`, `schema_id`
- **Run metadata**: `run_id`, `org_id`, `module_id`, `version`, `capability`, `started_at`, `completed_at`
- **Status**: `success` | `partial` | `error`
- **Data points**: typed payloads with `schema_ref` (e.g., `WeatherData`)
- **Artifacts**: charts, files, logs with MIME types, SHA-256 hashes
- **Errors**: standardized error codes (connectivity, auth, rate_limit, schema, internal, timeout, not_found, invalid_input)
- **Metering**: `run_units`, `tokens`, `duration_ms`, `api_calls`
- **Trace**: `trace_id`, `span_id`, `parent_span_id`

**Helper functions**:
- `create_success_result()`
- `create_partial_result()`
- `create_error_result()`

- **Tests**: 27 tests validate success/partial/error scenarios, serialization, real-world cases

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- ✅ All 106 tests pass (22 manifest + 31 contracts + 26 artifacts + 27 output)
- ✅ All modules importable with no circular dependencies
- ✅ `manifest_schema.json` validates correct manifests, rejects invalid ones
- ✅ `contracts.py` rejects markdown fences, path violations, missing fields
- ✅ `artifacts.py` produces stable hashes for identical inputs (determinism proven)
- ✅ `output_contract.py` serializes/deserializes without data loss
- ✅ REQ-013 foundation: module scaffold format is fixed (manifest.json + adapter.py + test_adapter.py)
- ✅ REQ-016 foundation: deterministic artifact identity enables auditable validation

## Success Criteria Met

- ✅ Contracts are "single source of truth" — tested and ready for downstream plans
- ✅ Manifest schema is versioned and strict (`$id` for evolution tracking)
- ✅ Generator contract enforces no markdown fences and path allowlist
- ✅ Artifact bundles are content-addressed and deterministic
- ✅ Output envelope is canonical for orchestrator, bridge, UI, metering

## Integration Points

### For Plan 02 (Module Generator Gateway)
- Import `GeneratorResponseContract` to validate LLM outputs
- Use `validate_generator_response()` to enforce contract compliance
- Path allowlist: `[f"modules/{category}/{platform}"]`

### For Plan 03 (Sandboxed Validation Loop)
- Import `AdapterContractSpec.validate_adapter_file()` for static checks
- Import `ArtifactBundleBuilder.build_from_dict()` to create bundles
- Use `verify_bundle_hash()` to validate bundle integrity

### For Plan 04 (Installer with Rollback)
- Import `ArtifactIndex` to track installed bundles
- Use `diff_bundles()` to compare versions
- Verify `bundle_sha256` before install

### For Orchestrator
- Import `AdapterRunResult` as canonical adapter output
- Use `create_success_result()`, `create_partial_result()`, `create_error_result()`
- Consume `metering` field for usage tracking

## Files Created

| File | Purpose | Lines | Tests |
|------|---------|-------|-------|
| `shared/modules/manifest_schema.json` | Module manifest validation schema | 142 | 22 |
| `shared/modules/contracts.py` | Adapter + generator contract specs | 366 | 31 |
| `shared/modules/artifacts.py` | Content-addressed artifact bundling | 338 | 26 |
| `shared/modules/output_contract.py` | Canonical adapter output envelope | 391 | 27 |

## Commits

| Hash | Message |
|------|---------|
| `9ec0fc0` | feat(03-01): add manifest JSON schema with versioned validation |
| `c5814e5` | feat(03-01): add builder and adapter contract specifications |
| `f764db4` | feat(03-01): add content-addressed artifact bundle system |
| `2cb6c7f` | feat(03-01): add canonical adapter output envelope |

## Next Steps

Plan 02 (Module Generator Gateway) can now proceed:
- Import `GeneratorResponseContract` for LLM output validation
- Import `AdapterContractSpec` for static adapter validation
- Import `ArtifactBundleBuilder` to create bundles before install
- All contracts are tested and ready for downstream consumption

---

**Duration**: 449 seconds (~7.5 minutes)
**Status**: Complete ✅

## Self-Check: PASSED

All files created:
- ✓ shared/modules/manifest_schema.json
- ✓ shared/modules/contracts.py
- ✓ shared/modules/artifacts.py
- ✓ shared/modules/output_contract.py
- ✓ tests/unit/modules/test_manifest_schema.py
- ✓ tests/unit/modules/test_contracts_static.py
- ✓ tests/unit/modules/test_artifact_bundle.py
- ✓ tests/unit/modules/test_output_contract.py

All commits exist:
- ✓ 9ec0fc0
- ✓ c5814e5
- ✓ f764db4
- ✓ 2cb6c7f
