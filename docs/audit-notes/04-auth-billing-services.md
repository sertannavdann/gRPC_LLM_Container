# NEXUS auth/billing/observability/services — Redundancy & SRP Audit

## 1. CROSS-SERVICE BOILERPLATE
1.1 HIGH dashboard_service/main.py:67-101 private setup_observability() re-implements shared/observability/setup.py:36-167 (divergent fork: no idempotency guard, no Prometheus reader, no configure_logging, hardcodes version + 15000ms vs 30000ms). Only orchestrator uses shared one. → delete, call shared.
1.2 HIGH per-service logging.basicConfig instead of shared configure_logging: dashboard main.py:56-59, bridge mcp_server.py:50, sandbox sandbox_service.py:43-46 (+orchestrator:133, llm_service:43, airllm:34, openai_wrapper:37, chroma:20). No correlation IDs/trace ids in 3/3 in-scope services.
1.3 HIGH auth+audit+CORS middleware wiring copy-pasted: dashboard main.py:331-367 ≡ orchestrator admin_api.py:2064-2100 (byte-identical comment block) ≡ tests/integration/admin/conftest.py:739-750. shared/auth/middleware.py:80-96 create_auth_middleware exists, ZERO production callers. → create_nexus_app() factory.
1.4 MED health endpoints: 4 different implementations; sandbox has TWO (grpc_health servicer :252-258 + HealthCheck RPC :305-310, both hardcoded healthy); 2 independent health-probe aggregators (pipeline_stream.py:62-75, mcp_server.py:869-908).
1.5 MED metrics exposition 3 ways: dashboard raw prometheus_client /metrics :416-426; shared OTel PrometheusMetricReader start_http_server setup.py:136-144; bridge hand-rolled JSON dicts :232-233/710-720. Sandbox: none.
1.6 MED gRPC server bootstrap dup 5×: sandbox:313-342, chroma:87-97, llm_service:341-351, airllm:258-268, orchestrator:1795-1822; only orchestrator attaches ObservabilityServerInterceptor; create_server_interceptors() (grpc_interceptor.py:217-219) called by nobody. → shared serve().
1.7 MED config = raw os.getenv scattered (dashboard 13 sites; bridge MCPServerConfig duplicates defaults; sandbox dup clamp constants); config/ package unused by all three.
1.8 LOW sys.path.insert hacks; sandbox shells to protoc at import time :29-41.

## 2. AUTH ENFORCEMENT SCATTER
2.1 HIGH bridge_service ZERO auth on code-execution surface: mcp_server.py:235-250 routes incl POST /tools/execute_code (:820-841) and /rpc tools/call (:614-621); only per-tool-global rate limiting :219-225.
2.2 HIGH sandbox gRPC no auth/identity: sandbox_service.py:264-303 ExecuteCode no metadata/org; core/graph.py:491-511 attributes to "default" org.
2.3 HIGH dashboard credential endpoints weaker than orchestrator equivalents: main.py:847,866,909,962 gated only by get_current_user (any viewer can write/delete credentials); :878-883 check_module_credentials NO dependency at all; orchestrator gates same ops with require_permission(MANAGE_CREDENTIALS) (admin_api.py:537,571). require_permission used 40+× in admin_api, 0× in dashboard.
2.4 MED public-path allowlists hand-maintained 4 places, divergent; DEFAULT_PUBLIC_PATHS (middleware.py:18-25) never used; dashboard's "/context" entry makes per-user /context/summary/{user_id} PUBLIC.
2.5 MED org scoping re-derived inline ~10× in admin_api (1607,1636,1660,1674,1687,1460,1496); OWNER cross-org rule only in _audit_query_filters :2150-2154; request.state.org_id set but unread by handlers. → Depends(org_scope).
2.6 MED QuotaManager._resolve_plan (quota_manager.py:45-53) reaches into APIKeyStore.get_organization — billing→auth schema dependency. → OrgDirectory port.
2.7 LOW auth-header construction dup client-side; bridge sends NO key calling dashboard (mcp_server.py:766-772).

## 3. PERSISTENCE DUPLICATION
3.1 HIGH nine near-identical _connect() impls, divergent pragmas: api_keys.py:35-39 (WAL+busy), usage_store.py:26-30 (byte-identical), otc_policy_store.py:33-37 (byte-identical), audit/store.py:128-133, user_prefs.py:69-75 (no busy_timeout, +foreign_keys), modules/registry.py:64-65 (no WAL), credentials.py:108-109 (no WAL), versioning.py:132-134 (no WAL), core/checkpointing.py:72-86. Docstrings acknowledge 4 generations of copy-paste ("Follows the SQLite pattern from ..."). → shared/storage/sqlite_base.py.
3.2 HIGH constructor boilerplate identical across 5 stores (mkdir+init+log; user_prefs gratuitously uses _db_path).
3.3 HIGH no schema migration mechanism anywhere — CREATE TABLE IF NOT EXISTS only, no PRAGMA user_version; ALTER silently impossible.
3.4 MED row_factory per-query in 3 stores (7 sites) vs on-connection in 2.
3.5 MED dynamic-filter query builder dup: usage_store.py:127-142, otc_policy_store.py:361-377, audit/store.py:57 _FILTERABLE_COLUMNS.
3.6 MED aggregation query 4× in usage_store (107-110,162-165,172-176,182-187); get_period_total subsumed by get_usage_summary; QuotaManager.check_quota calls BOTH → 2 connections+4 queries per check.
3.7 LOW validate_key opens 2 connections per request (api_keys.py:120-137) on the hot path.

## 4. METRICS/METERING/LATENCY
4.1 HIGH two parallel metric systems: dashboard 6 raw prometheus instruments (main.py:109-152) vs shared create_request_metrics (metrics.py:142-181) — same signals, different names/backend/port.
4.2 HIGH run-unit pipeline split with no owner: compute run_units.py:33-87 (3 entry points); compute+persist inline in core/graph.py:496-511; accumulate state :520; emit metrics in orchestrator_service.py:1732-1739; otc_reward.py:78 4th interpretation; otc_policy_store trajectory_log 2nd table. → MeteringService.meter().
4.3 HIGH latency measured 5+ independent ways (grpc_interceptor perf_counter; metrics TimerContext; dashboard time.time() wall clock :386-404; pipeline_stream perf_counter; latency_snapshot black-box HTTP probing p50/95/99 duplicating server-side histograms; sandbox 2 more).
4.4 MED metrics.py = 8 near-identical create_*_metrics factories, 615 lines ~85% boilerplate; 5 module-level mutable gauge globals with bespoke updaters. → declarative MetricSpec list.
4.5 MED bridge _tool_calls/_tool_errors dicts re-implement create_tool_metrics.
4.6 LOW dashboard instruments defined never written: AGGREGATOR_FETCH_DURATION/CACHE_HITS/CACHE_MISSES/CONTEXT_ITEMS — permanently-zero series.

## 5. SRP VIOLATIONS
5.1 HIGH dashboard_service/main.py 1105 lines, 9 jobs (observability, instruments, schemas, aggregator factory, lifespan, middleware, metrics middleware, 5 endpoint families, uvicorn main). → app_factory + routers.
5.2 HIGH metrics_middleware :383-409 also mutates business gauge ACTIVE_USERS on every request incl 404s.
5.3 HIGH QuotaManager computes+resolves plan+reads persistence; enforcement lives in orchestrator_service.py:1536-1555 (hand-written message, fail-open except) + 2nd site admin_api.py:1282 (hardcoded "default" org!) and :1687. → QuotaPolicy/QuotaReader/enforce_quota.
5.4 HIGH core/graph.py:490-511 tool node does execution+metering+SQLite persistence inline, swallow-all except; constructs own UsageStore (graph.py:100-101) — 2nd instance beside orchestrator_service.py:1113.
5.5 HIGH sandbox_service.py 346-line file: 56-line Python source template f-string :121-195 with embedded restricted-builtins table; 3 dup os.unlink blocks; servicer+bootstrap same file.
5.6 MED MCPServer god object: routing, 270-line inline tool-schema literal :252-521, rate limiting, 2 TTL caches, metrics, handlers, dispatch, 8 tool impls, lifecycle; _execute_tool rebuilds handlers+validators dicts ON EVERY CALL :654-673.
5.7 MED dashboard handlers mix query/format/shape: get_context_summary ≡ get_context_briefing (651-699); /context/relevance vs /relevance/{user_id} same data 2 shapes; try/except→HTTPException(500) copy-pasted 16×.
5.8 MED alert/presentation rules in 4 layers with DRIFTED thresholds: HRV <40 (formatters.py:92,251) vs <30 (relevance.py:198); traffic/temp rules stated twice; tools/builtin/user_context.py:118 imports dashboard_service.formatters ACROSS SERVICE BOUNDARY with silent ImportError fallback. → alert_rules.py.
5.9 MED bank_service filter chain copy-pasted 3× (126-160, 194-224, 296-303; identical date_to_end line at :142,:212; /bank/search matches different fields than ?search=).
5.10 MED DashboardAggregator fetch+health+normalize+summarize+cache; health-mutation block 3×, success mirror 2×.
5.11 LOW APIKeyStore owns Organization+User CRUD (3 entities).

## 6. DEAD CODE
6.1 MED never called: create_auth_middleware; create_server_interceptors/create_client_interceptors/ObservabilityClientInterceptor; _wrap_streaming_handler (documented no-op — streaming never observed); quota get_remaining/would_exceed; estimate_request_cost; otc_reward.py ENTIRE (86 ln) + otc_policy_store.py ENTIRE (378 ln) — zero prod callers, not exported; latency_snapshot.py (144 ln, only __main__); aggregator probe_all_adapters + get_user_context; relevance get_context_summary_for_llm; logging LogContext/clear_context; user_prefs delete_prefs; runner execute_with_timeout (ignores own timeout contract).
6.2 HIGH sandbox_service/runner.py (405 ln) = orphaned SECOND sandbox engine (in-process exec() vs subprocess), used only by module_validator.py:421-422; gRPC servicer uses execute_in_sandbox instead. Import allowlists duplicated+divergent: sandbox_service.py:56-60 (15 modules) vs policy.py:33-38 (22, adds os/sys/time/asyncio/pathlib/hashlib); policy.py (357 ln) NEVER guards real gRPC traffic. Resource clamps duplicated (52-53/269-270 vs policy 231-249). runner imports StaticImportChecker, never calls it (hand-rolls AST walk :113-186). NetworkViolation plumbing present, never populated; success branches on always-empty field.
6.3 MED dead symbols sandbox_service.py: multiprocessing, StringIO, signal imports; TimeoutError/MemoryExceededError classes; module-level restricted_import :73-79 (real one re-defined in generated wrapper string :136-139).
6.4 MED redundant duplicate endpoints: /context/briefing alias; /context/relevance vs /relevance; bridge tools/list built twice; list_available_tools hardcoded stale static list :858-867; sandbox 2 health surfaces.
6.5 LOW silent swallowing: bridge bare except pass :854-855; :645 'if "body" in dir()' bug loses JSON-RPC id; sandbox except:pass ×2; user_prefs except (JSONDecodeError, Exception); core/graph.py:510-511 fail-OPEN metering vs audit fail-CLOSED — opposite failure contracts, no shared policy.
6.6 LOW datetime.utcnow() (deprecated) in api_keys 5 sites + bridge 2 sites vs correct now(timezone.utc) elsewhere.

## Priority
1. shared/storage/sqlite_base.py (kills 3.1-3.4, 3.6; adds migrations)
2. create_nexus_app / serve_grpc factory (kills 1.1-1.6, 1.8)
3. MeteringService + QuotaPolicy split (4.2, 5.3, 5.4)
4. Delete/wire orphans: otc_reward, otc_policy_store, latency_snapshot, runner.py ≈1000 ln (6.1, 6.2)
5. SECURITY: bridge auth (2.1), sandbox identity (2.2), dashboard credential RBAC (2.3)
6. alert_rules.py — fixes live HRV 30/40 threshold conflict (5.8)
