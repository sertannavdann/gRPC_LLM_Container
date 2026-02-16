Here is Claude's plan:

Phase 03 Cross-Feature Integration Test Plan
Goal
Build integration tests that verify Phase 03 components working together across boundaries — not just in isolation. The existing ~320+ unit/integration tests verify individual plans; these tests verify the wiring between them.

Current State
06 plans complete with passing unit/integration tests per plan
3 wiring gaps identified in 03-VERIFICATION.md:
build_module not registered as orchestrator tool
repair_module does not call gateway.generate(purpose=REPAIR) (line 416 has # TODO)
No dashboard chart serving endpoint
No cross-feature integration tests exist — this plan fills that gap
Structure
```
tests/integration/cross_feature/
├── conftest.py                              # Shared fixtures, Docker override
├── test_hash_chain_integrity.py             # Artifact SHA-256 flows through pipeline
├── test_contract_enforcement_pipeline.py    # Contracts enforced at every boundary
├── test_repair_loop_feedback.py             # Validator → FixHints → Builder → Audit
├── test_devmode_full_lifecycle.py           # Draft → Validate → Promote → Rollback
├── test_policy_propagation.py               # Sandbox violations → terminal stop
├── test_feature_test_gating.py              # Manifest capabilities → suite selection
└── test_audit_completeness.py               # Every stage produces audit records
```
Run command: pytest tests/integration/cross_feature/ -v --tb=short
Wiring gap tests only: pytest tests/integration/cross_feature/ -v -m "wiring_gap"

Files to Create (8 files)
File 0: tests/integration/cross_feature/conftest.py
Shared fixtures. Same pattern as tests/integration/install/conftest.py.

Key fixtures:

test_environment / llm_warmup — override parent Docker fixtures (session, autouse)
temp_workspace(tmp_path) — returns dict with modules_dir, drafts_dir, audit_dir, artifacts_dir, db_path
valid_adapter_code() — compliant adapter string (has @register_adapter, fetch_raw, transform, get_schema, no forbidden imports)
forbidden_import_adapter_code() — adapter with import subprocess
sample_manifest_dict() — dict for manifest construction
create_test_module(modules_dir, module_id, adapter_code, test_code, status) — writes module to disk, returns (manifest, bundle_sha256) via ArtifactBundleBuilder.build_from_dict
setup_builder_env(temp_workspace) — patches os.environ for MODULES_DIR/AUDIT_DIR, reloads module_builder and module_installer
Register wiring_gap marker via pytest_configure
Imports needed: pytest, tempfile, Path, MagicMock, patch, ModuleManifest, ModuleStatus, ArtifactBundleBuilder

File 1: test_hash_chain_integrity.py — SHA-256 hash flows through the pipeline
Components integrated: artifacts.py → module_validator.py → module_installer.py → audit.py

Tests (5):

Test	What's real	What's mocked	Proves
test_bundle_hash_stable_across_build_validate_install	ArtifactBundleBuilder, verify_bundle_hash, install_module	_module_loader, _module_registry	Hash computed at build time survives to install attestation
test_single_byte_change_breaks_hash_chain	ArtifactBundleBuilder, install_module	_module_loader, _module_registry	Post-validation tampering detected — install rejected with "hash mismatch"
test_hash_determinism_across_recomputation	ArtifactBundleBuilder.build_from_dict, self_check	nothing	Identical inputs always produce identical hashes
test_bundle_diff_detects_file_changes	ArtifactBundleBuilder, diff_bundles	nothing	diff_bundles identifies exactly which files changed
test_audit_record_captures_bundle_hash	BuildAuditLog, AttemptRecord, ArtifactBundleBuilder	nothing	AttemptRecord round-trips bundle_sha256 through to_dict/from_dict
File 2: test_contract_enforcement_pipeline.py — Contracts enforced at every boundary
Components integrated: llm_gateway.py → contracts.py → module_validator.py → sandbox_service/runner.py

Tests (5):

Test	Proves
test_gateway_validated_code_passes_validator_static_checks	Code valid per GeneratorResponseContract also passes AdapterContractSpec — boundaries are consistent
test_forbidden_imports_caught_at_both_boundaries	AdapterContractSpec.check_forbidden_imports AND StaticImportChecker.check_imports both catch subprocess
test_markdown_fences_rejected_by_contract	GeneratorResponseContract pydantic validator rejects content with triple-backtick fences
test_path_allowlist_enforced_across_gateway_and_contract	validate_contract(allowed_dirs=[...]) rejects files outside allowlist with PATH_NOT_ALLOWED
test_build_module_not_registered_as_orchestrator_tool	@pytest.mark.wiring_gap — documents Gap 1. Import build_module, assert callable. When wiring added, flip assertion
File 3: test_repair_loop_feedback.py — Repair feedback across components
Components integrated: module_validator.py (FixHint) → module_builder.py (repair_module) → audit.py (FailureFingerprint, classify_failure_type)

Tests (7):

Test	Proves
test_fix_hints_flow_from_validator_to_repair_module	repair_module receives fix_hints from ValidationReport, records them in audit
test_failure_fingerprint_stable_for_identical_failures	Same FixHints → same FailureFingerprint.hash (deterministic)
test_thrash_detection_stops_repair_loop	2 consecutive identical fingerprints → repair_module returns "Thrashing detected"
test_terminal_failure_stops_immediately	fix_hint category='policy_violation' → repair_module returns "Terminal failure" without adding attempt
test_max_attempts_boundary	10 pre-loaded attempts → repair_module returns "Max repair attempts reached"
test_repair_module_does_not_call_gateway_generate	@pytest.mark.wiring_gap — documents Gap 2. Mock _llm_gateway, call repair_module, assert generate NOT called. Returns repair_pending.
test_fix_hints_include_correct_categories	FixHint categories align with classify_failure_type outcomes (import_violation → IMPORT_VIOLATION)
Key implementation detail: repair_module uses env-based MODULES_DIR/AUDIT_DIR — must patch.dict('os.environ', ...) and importlib.reload(module_builder) in fixture (same pattern as test_validated_only_guard.py:56-78).

File 4: test_devmode_full_lifecycle.py — Draft through rollback
Components integrated: drafts.py → module_validator.py → artifacts.py → versioning.py → audit.py

Tests (5):

Test	Proves
test_draft_edit_validate_promote_version_record	Full lifecycle: create → edit → validate(mock passes) → promote → version recorded with correct bundle_sha256
test_promote_then_rollback_restores_prior_version	v1 installed → v2 promoted → rollback to v1 → active version is v1, v2 preserved
test_validation_failure_prevents_promotion	Failed validation keeps draft in non-VALIDATED state, promote rejected
test_bundle_sha256_consistency_across_draft_and_version	Hash from validate_draft matches VersionManager recorded hash matches recomputed hash
test_discarded_draft_cannot_be_promoted_or_validated	Discarded draft operations fail gracefully
Key: DraftManager takes validator_func and installer_func callables — mock these to control validation/install outcomes without Docker.

File 5: test_policy_propagation.py — Sandbox policy → validator → builder
Components integrated: sandbox_service/policy.py → sandbox_service/runner.py → module_validator.py → module_builder.py → audit.py

Tests (6):

Test	Proves
test_sandbox_import_violation_becomes_validator_fix_hint	StaticImportChecker violation → AdapterContractSpec error → FixHint with category='import_violation'
test_policy_violation_classified_as_terminal	fix_hint category='policy_violation' → classify_failure_type → POLICY_VIOLATION → repair_module stops
test_security_block_classified_as_terminal	fix_hint category='security_block' → POLICY_VIOLATION (same terminal handling)
test_retryable_failure_allows_repair_attempt	fix_hint category='test_failure' → TEST_FAILURE → repair_module records attempt and returns repair_pending
test_sandbox_policy_merge_preserves_forbidden_enforcement	ExecutionPolicy.merge keeps enforce_forbidden=True across profiles
test_different_policy_profiles_produce_consistent_violations	default, module_validation, integration_test profiles all block subprocess
File 6: test_feature_test_gating.py — Manifest capabilities → correct tests
Components integrated: feature_test_harness.py → chart_validator.py → output_contract.py → artifacts.py

Tests (6):

Test	Proves
test_manifest_auth_type_selects_correct_suites	auth_type='api_key' → auth_api_key suite; 'oauth2' → oauth_refresh suite
test_capability_flags_select_additional_suites	pagination+rate_limited capabilities → pagination_cursor+rate_limit_429 suites
test_schema_drift_always_included	schema_drift suite selected regardless of manifest capabilities
test_chart_validation_with_artifact_envelope	Chart bytes → validate_chart → Artifact → AdapterRunResult.artifacts[0].sha256 matches
test_chart_artifacts_have_no_dashboard_serving_endpoint	@pytest.mark.wiring_gap — documents Gap 3. validate_chart works, no dashboard route exists
test_json_chart_metadata_extraction	Plotly-style JSON chart → tier-2 validation passes with correct series_names and data_point_count
File 7: test_audit_completeness.py — Every stage audited with correct hashes
Components integrated: audit.py → artifacts.py → drafts.py → versioning.py → module_installer.py

Tests (7):

Test	Proves
test_build_audit_log_captures_all_stages	BuildAuditLog with scaffold/implement/tests/repair records — all stages preserved through to_dict/from_dict
test_draft_lifecycle_audit_trail_complete	Every DraftManager action (create/edit/diff/validate/discard) produces DevModeAuditLog event
test_version_rollback_audit_includes_from_and_to	Rollback event has from_version, to_version, reason, bundle_sha256
test_install_success_and_rejection_produce_audit_entries	install_success.jsonl and install_rejections.jsonl populated correctly
test_audit_events_have_monotonic_timestamps	All events within a lifecycle have non-decreasing timestamps
test_failure_fingerprint_in_audit_matches_validation_report	Fingerprint hash stored in AttemptRecord matches recomputed hash from same report
test_audit_log_save_and_load_round_trip	BuildAuditLog survives save() → load() with all data intact
Verification
After implementation, run:
```
# All cross-feature tests
pytest tests/integration/cross_feature/ -v --tb=short

# Wiring gap tests only (should all pass — they document gaps)
pytest tests/integration/cross_feature/ -v -m "wiring_gap"

# Full Phase 03 suite (existing + new)
make test-self-evolution
```
Expected: 41 passing tests (38 standard + 3 wiring_gap). All green.

Makefile Update
Add to existing test-self-evolution target:
```
@printf '$(YELLOW)Cross-feature integration tests...$(RESET)\n'
@python -m pytest tests/integration/cross_feature/ -v --tb=short
```
Critical Implementation Notes
repair_module env patching — Must reload module_builder after patching MODULES_DIR/AUDIT_DIR (line 40-41 are module-level). Follow exact pattern from tests/integration/install/test_validated_only_guard.py:56-78.

DraftManager validator/installer callables — DraftManager accepts validator_func and installer_func as constructor args or method params. Mock these to control outcomes without Docker.

Wiring gap tests — Designed to pass NOW (assert gap exists). When each gap is fixed, flip the assertion. Each test has a comment indicating what to change.

No Docker required — All tests are in-process. conftest.py overrides parent Docker fixtures. Tests use tmp_path for all filesystem operations