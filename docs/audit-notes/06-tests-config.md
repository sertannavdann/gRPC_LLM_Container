# NEXUS tests/scripts/config/modules — Redundancy & SRP Audit

## 1. TEST INFRA DUPLICATION (top patterns)
1. test_environment+llm_warmup session fixtures: real in tests/integration/conftest.py:57,162 + 4 no-op overrides (install, self_evolution, cross_feature conftest) + 5th differently-named skip_docker_check (sandbox/conftest.py:10) — HIGH
2. mock_loader identical MagicMock 4×: cross_feature/conftest.py:128-137, install/test_validated_only_guard.py:38-45, unit/modules/test_installer_approval_guard.py:35-42, unit/test_module_tools.py:47-55 — HIGH
3. module-on-disk factory 5×: admin/test_audit_capture.py:24 ≡ test_approval_gate.py:24 (byte-identical), cross_feature/conftest.py:144, install:81, unit/modules:66 — HIGH
4. tmp_db→store SQLite pair 8+ sites (test_auth, test_audit_store, test_audit_decorator, test_billing, admin/conftest 6-DB dict, auth/ 2 files, root temp_checkpoint_db) — HIGH
5. temp_workspace 3 mutually incompatible shapes (cross_feature:39-56, dev_mode/test_rollback_pointer:23-38 mkdtemp, dev_mode/test_draft_diff:26-46) — HIGH
6. setup_installer_deps (env patch + importlib.reload + set_installer_deps) 3× — HIGH
7. sample_schema generator-response JSON schema byte-identical in test_llm_gateway.py:77 vs test_fallback_chain.py:58 — HIGH
8. docker_manager+agent_client harness re-derived 4× with different scopes — HIGH
9. grpc client construction 6 sites (AgentTestClient, raw stubs, raw insecure_channel) — HIGH
10. httpx AsyncClient async-CM mock 8-line block ×22 (feature tests + generated module tests) — HIGH
Runners-up: mock_registry 3×; usage_store/quota_manager 3×; modules_dir SAME NAME different contract (admin/conftest:697 returns dir vs unit/test_module_tools:26 patches globals) — trap; proto-stub sys.modules mock 4 variants; sys.path.insert ×11.

HIGH tests/integration/admin/conftest.py:43-599 — 557-line hand-rewrite of ~26 production Admin API endpoints ("avoid importing orchestrator package" :38). Drift guaranteed. → extract create_admin_app(deps) factory from admin_api.py.
HIGH tests/auth/test_billing_integration.py:33-68 third copy of billing endpoints; test_auth_integration.py:41-86 fourth hand-rolled app.
MED tests/unit/test_capability_contract.py vs ui_service/tests/unit/... — 294/330 lines identical; ui copy older → delete.
MED observability/conftest TestScenarios duplicates grpc_test_client.AgentTestClient.query in async form.
MED verify_service_health (observability/conftest:465-510) reimplements Makefile:327-343 + showroom_test.sh health matrix.
MED cross_feature `from conftest import create_test_module` rootdir-relative import fragility.
LOW __init__.py convention inconsistent across tests/; markers only registered in integration/conftest (no pytest.ini anywhere).
LOW root conftest docker_services_up unused and contradicts integration conftest assumption.

## 2. TEST/PROD LOGIC DUPLICATION
HIGH test_capability_contract.py:202-234 recomputes ETag instead of importing admin_api._compute_etag (misses sort_keys branch).
HIGH admin/conftest.py:482-510 reimplements audit filtering + CSV-injection escaping from admin_api.py:2185-2287 — prod CSV fix wouldn't be caught.
MED generator_response schema hand-copied in 2 test files; no canonical export from contracts.py.
MED contract tier re-declares envelope fixtures already in unit/modules/test_output_contract.py.
HIGH tests-that-assert-nothing: feature/test_auth_api_key, test_rate_limit_429, test_oauth_refresh, test_pagination_cursor — 19 tautological assertions on mock's own configured values; no prod code executed; duplicate 8-line mock scaffold ×22 → point at real BaseAdapter paths or delete tier.
NOTE prod-side: hashing.py:47, drafts.py:158,251, audit.py:79 bypass compute_sha256.

## 3. SCRIPT DUPLICATION
HIGH scripts/track_{a..e}_*.sh (484 ln total) — five copies of file-exists/grep/✅❌ TODO trackers; referenced by nothing → delete. track_e:22 stale port 50055 (actual 50057).
MED verify.sh:120-171 vs Makefile:757-806 — test-tier orchestration in 3 places, different invocation/flags → Makefile thin wrapper over verify.sh --tier.
MED Makefile health checks duplicated 4×: :815-826 health ≡ :317-328 status loop; observability-health :1048-1057; bridge-health :1086-1091 → one _health_probe recipe.
MED showroom_test.sh check() vs verify.sh run_step() — two pass/fail harnesses + dup ANSI blocks → scripts/lib/report.sh.
MED scripts/test_inference_speed.py — hardcodes localhost:50051, wrong import path, duplicates warmup probe + latency_snapshot; no Makefile target → delete.
LOW verify.sh 5 identical if-dir blocks → loop.

## 4. CONFIG DUPLICATION
HIGH Makefile PORT_* vars defined :31-37 then same numbers hardcoded 50+ times (50054, 50051, 50052, 50057, 5001 ×9 not even a var, 8001, 8100, 3001, 9090) → add vars, substitute.
HIGH PORT_UI := 3000 self-conflict: :206 prints 3000 but UI on 5001 (:366,499,709,1144,1171; compose "5001:5000"); 3000 is Vite dev port → split PORT_UI_DEV/PORT_UI.
HIGH orphaned compose env: BRIDGE_PORT/BRIDGE_HOST (docker-compose:210-211) never read; reader uses MCP_PORT (mcp_server.py:1019).
HIGH default model name declared 4+ ways, 2 contradictory in same file: orchestrator/config.py:54 (3b) vs :153 (0.5b default in SAME dataclass loader); compose:100; core/state.py:88,116 (Mistral-24B!); llm_service/config.py:35; routing_config.json:85 (no .gguf) → config/models.json.
HIGH AUDIT_DIR default drift: module_builder:54 + module_pipeline:31 "/app/data/audit" vs module_installer:30 "data/audit" (relative) — builder and installer write to different dirs when unset.
MED MODULES_DIR global declared 4× (builder:53, installer:29, pipeline:30, validator:37); tests must patch 3 globals individually → shared/modules/paths.py.
MED model catalogue dup: routing_config.json:78-111 vs model_registry.py:37-70; and .gguf/no-.gguf inconsistency WITHIN routing_config.
MED provider default models dup 3 places (routing_config:86-101, orchestrator/config.py:123-129 if/elif, provider __init__ defaults).
MED tier endpoints declared 3× (routing_config:56,62; orchestrator/config:73-74; :165-166).
MED hardcoded localhost URLs in tests: ui/test_settings_provider_lock.py:17 no env override; conftest hardcoded channels/ports; verify.sh:169 hardcoded admin URL while showroom_test.sh overridable → tests/endpoints.py.
LOW dashboard vs dashboard_service DNS names (compose service vs container_name) across bridge config + prometheus.yaml.
LOW mcp_server.py:849 derives metrics port by string-replacing ':50054'→':8888' in configured address.

## 5. GENERATED MODULE / TEMPLATE DRIFT
HIGH broken f-string escaping in 2 of 5 generated adapters: modules/gaming/testgame/adapter.py:44,48,53,65 and modules/test/srccheck/adapter.py:44,48,53,66 — headers = {{}} parses as set-of-dict → TypeError at runtime; f"Bearer {{api_key}}" emits literal. weather/open-meteo correct. Template itself correct — LLM-supplied body double-escaped, nothing validated → ast.parse + smoke-instantiate gate in validator; regenerate/delete both modules.
HIGH template emits get_schema() (adapter_template.py:76-91); ZERO of 5 on-disk modules have it — all predate current template → regenerate or version-stamp.
HIGH get_capabilities() boilerplate copy-pasted into all 5 adapters → default on BaseAdapter.
HIGH __init__/transform boilerplate byte-identical ×3 (~35 ln each) → HttpJsonAdapter(BaseAdapter) in shared.
HIGH generated test_adapter.py 90 ln pure boilerplate ×3, asserts only interface conformance that AdapterContractSpec already checks → 5-line parametrized shared testkit.assert_adapter_contract.
MED generated tests use bare `from adapter import X` — only importable in sandbox runner; NO repo harness ever collects modules/ tests.
MED showroom/hello test files hand-written, diverge from template.
MED asyncio.get_event_loop().run_until_complete in template :100 → propagated to all; deprecated, breaks 3.12+.
LOW CONTRACT_TEST_TEMPLATE (test_template.py:110-183) + generate_contract_test_code dead (not in __all__, no caller).
LOW two generation entry points (nexus_dev.py:37,66 and module_builder.py:27,251).

## 6. OBSOLETE ARTIFACTS
HIGH manifest_schema.json dead + incompatible: required keys have ZERO overlap with real manifests (module_id/entrypoint/capabilities vs entry_point etc.); validator never loads it; only a test with hand-written fixtures matching no real manifest → delete both or regenerate + wire.
HIGH tests/evals/eval_runner.py non-functional: _call_orchestrator returns hardcoded mock (:163-175, real call commented out); every YAML case scores 0; 404 ln + corpus dead → wire to AgentTestClient or delete.
HIGH scripts/track_*.sh 484 ln → delete.
MED modules/_registry.json "{}" while 5 modules on disk — stale or write-only.
MED compose airllm service fully commented out (:402-404) but 3 live Makefile targets + PORT_LLM_AIRLLM still point at it.
MED Makefile:796 `make-test-metering:` alias (invoked as `make make-test-metering`); alias sprawl (9 one-letter, restart-all≡restart, start/all, stop/down, fix-* family) — 126 targets in 1300 lines.
LOW grpc_test_server fixture returns Mock() "will be implemented"; vestigial comments; docker_manager start_/stop_/kill_ variants duplicate up/down/restart in same class, unused.
NOTE prod-side: admin_api registers 7 routes twice (:722/:1739 etc.); second block :1713-1913 unreachable — this is WHY the test double was hand-written.

## Consolidation summary
1. tests/conftest.py + tests/helpers/ absorb ~40 fixture redeclarations.
2. create_admin_app(deps) factory; delete 557-ln test double + 2 smaller copies.
3. HttpJsonAdapter + testkit.assert_adapter_contract; shrink templates to ~15 ln delta.
4. Fix/regenerate 2 runtime-broken generated modules; ast.parse gate in validator.
5. Single port/URL source (Makefile vars, tests/endpoints.py, PORT_UI split, BRIDGE_PORT→MCP_PORT).
6. Delete ~1400 ln: track_*.sh, test_inference_speed.py, tests/evals (or wire), manifest_schema.json+test, ui copy of capability test, CONTRACT_TEST_TEMPLATE, Makefile:796.
7. Root pytest.ini + normalize __init__.py.
