# NEXUS ui_service — Redundancy & SRP Audit
Note: machines/pipelinePage.ts DOES NOT EXIST — pipeline page is Zustand + useEffect, inconsistent with finance/monitoring statecharts.

## 1. MACHINE LOGIC
M-1 HIGH monitoringPage.ts:129-172 vs 174-219 — health/latency regions structurally identical (loading→invoke→loaded/error + after timers) → createPollingRegion() factory.
M-2 HIGH three independent fetch/poll actors: nexusApp.ts:65-73, monitoringPage.ts:82-109, financePage.ts:101-134 → one shared fromPromise actor.
M-3 HIGH nexusApp.ts:38-44,102-132,262-290 — ENVELOPE_LOADED/ENVELOPE_ERROR/CONFIG_VERSION_CHANGED/PREFS_LOADED never sent by anything; actions storeEnvelope:103/storeConfigEtag:111/storeError:117/storePrefs:127 dead; guard configVersionChanged:97 dead; entire dataSource region permanently stuck "unknown"; guards hasLiveAdapter:77/allAdaptersLocked:82/isFallbackEnvelope:88 never run.
M-4 HIGH (fallout) useNexusApp.ts:81-84 isLive/isMock/isOffline always false, isUnknown always true → dashboard/page.tsx:28-33 always "unknown"; monitoring/page.tsx:207-208 always "Polling".
M-5 MED nexusApp.ts:92-95 + 186-202 re-implement lib/errors.ts isRetryable:109/errorMessage:118 (both unused).
M-6 MED clearError/storeError bodies dup nexusApp.ts:117-125 ≡ financePage.ts:161-169.
M-7 MED monitoringPage.ts:113-114 isHealthRetryable/isLatencyRetryable same predicate, both unreferenced (dead guards).
M-8 MED financePage.ts:171-179 storeFinanceData declared never referenced (inlined at :274-278); storeError:165 same.
M-9 MED adapter-locked logic in 3 places: financePage.ts:61-66, AdapterCard.tsx:23-45, pipeline/page.tsx:222 + AdapterNode.tsx:41 + NodeDetailPanel.tsx:92 (requiresAuth && !hasCredentials) → lib/capability-selectors.ts.
M-10 LOW hardcoded timings monitoringPage.ts:154,163,202,211 bypass lib/runtime-params.ts; CAPABILITY_POLL_INTERVAL_MS unused.

## 2. COMPONENTS/HOOKS
C-1 HIGH two ServiceNode components, same name, incompatible shapes: components/pipeline/ServiceNode.tsx:11-53 vs monitoring/ServiceTopology.tsx:52-127.
C-2 HIGH SettingsPanel.tsx (454 ln) superseded duplicate of app/settings/page.tsx (700 ln): dup loadSettings/saveSettings/provider grid/RestartStatus/provider meta; older version still mounted from ChatContainer.tsx:441 → delete, route to /settings.
C-3 HIGH AdaptersPanel.tsx:92-178 vs IntegrationsPanel.tsx:114-197 vs AdapterCard.tsx:64-180 — three adapter-management UIs on same endpoint; AdaptersPanel:58-60 redirects to /integrations for credentials (same flow split in two) → one AdapterConnectionCard + useAdapterConnection().
C-4 HIGH four status-badge implementations: monitoring/page.tsx:87-103, ServiceTopology.tsx:43-48+96, AdapterCard.tsx:23-45, NodeDetailPanel.tsx:55-64 + inline dots dashboard/page.tsx:143-160, Navbar.tsx:101 → one StatusBadge + STATUS_TOKENS.
C-5 HIGH two Zustand stores both named nexusStore: src/store/nexusStore.ts (pipeline/SSE) vs src/stores/nexusStore.ts (XState bridge); useNexusApp.ts:61,67 runtime import() to dodge circular dep → merge/rename.
C-6 MED six widgets duplicate header/expand/skeleton chrome (Calendar 152-162, Finance 222-230, Health 139-149, Navigation 182-192, Weather 101-107, Gaming 72-78) → WidgetShell.
C-7 MED four hand-rolled fetch/loading/error triples: useDashboard.ts:66-92, IntegrationsPanel.tsx:72-87, FinanceWidget.tsx:56-102, useUserPrefs.ts:60-79 → useApiResource().
C-8 MED degraded_reasons rendered 3 ways (monitoring/page.tsx:277-283, ServiceTopology.tsx:115-121, error-states.tsx:47-53); missing_fields 2 ways (AdapterCard.tsx:137-143, settings/page.tsx:352-356).
C-9 MED inline error banner copy-pasted 5+ places; TimeoutSkeleton (error-states.tsx:120) never used.
C-10 MED Recharts tooltip/legend config dup SpendingChart.tsx:65-73,150-157 ≡ LatencyChart.tsx:66-88 → chartTheme.ts.
C-11 MED date/number formatting 6-8 sites, mutually inconsistent relative-time impls → lib/format.ts.
C-12 MED transaction rendering dup TransactionTable.tsx:141-170 vs FinanceWidget.tsx:155-179.
C-13 LOW React Flow boilerplate 3x (ServiceTopology:280-305, PipelineStageFlow:197-215, pipeline/page:311-335).
C-14 LOW summary-card grid dup finance/page.tsx:294-340 vs FinanceWidget.tsx:308-338.

## 3. TYPES
T-1 HIGH NexusErrorType declared twice with different members: lib/errors.ts:20 (enum) vs nexusApp.ts:38-44 (union); aliased import + hand-mapping :189-201.
T-2 HIGH Transaction (financePage.ts:30-40) ≡ FinancialTransaction (types/dashboard.ts:8-18); imported from different sources by different components.
T-3 HIGH settings types redeclared: ProviderInfo, SettingsConfig (divergent), RestartStatus, ConnectionTestResult (3 copies), ProviderLockStatus.
T-4 HIGH IntegrationsPanel redeclares AuthField/AdapterInfo/CategoryInfo/AdaptersData duplicating types/dashboard.ts:213-238.
T-5 HIGH backend status enums mirrored 5×: FeatureStatus (adminClient.ts:105-110) bypassed by raw string maps in 4 files; state 'running'|'error'|'disabled' redeclared 5 places.
T-6 MED fallback contract fields declared twice (adminClient.ts:164-165 vs runtime-params.ts:15-16 + machine literals nexusApp.ts:89,161,166).
T-7 MED API DTOs (ServiceLatency/AgentRun) declared inside machines, imported by components → move to types/.
T-8 LOW FinanceSummary vs FinanceContext partial dup.

## 4. API CLIENT
A-1 HIGH adminClient.ts:181-192 adminFetch bypassed by getCapabilities:229-253 and getConfigVersion:257-282 (hand-rolled fetch+timeout dup for ETag) → etag option on adminFetch.
A-2 HIGH five base-URL derivations, conflicting defaults: adminClient 8003 + 8001, useUserPrefs.ts:38-41 (:8003 DIRECT bypassing /api/admin proxy), FinanceWidget :8001, monitoring/page :3001; server routes default orchestrator:8003 vs localhost:8003 → lib/endpoints.ts.
A-3 HIGH ~20 copies of catch(err){setError(err.message)}; none use classifyError.
A-4 MED two adapter API routes with two hardcoded registries (api/adapters/route.ts:43-48, api/dashboard/adapters/route.ts:23-107); /api/adapters accepts two incompatible POST payloads (financePage.ts:76 vs dashboard/page.tsx:59).
A-5 MED orchestrator-restart client logic 3 variants (SettingsPanel:80-144, IntegrationsPanel:199-216, settings/page:212-225).

## 5. SRP
S-1 HIGH app/settings/page.tsx 700 ln, 20 useState, fetch+forms+lock interpretation+console+render.
S-2 HIGH IntegrationsPanel.tsx 473 ln: fetch+mutation+restart orchestration+UI state+render+4 type decls.
S-3 HIGH ChatContainer.tsx 444 ln: transport+persistence/debounce+auto-summarise+tool-approval workflow+store mutation+layout+render (6 jobs).
S-4 HIGH Dashboard.tsx 395 ln: 6-branch focus switch :312-329 duplicated by 6-branch grid switch :334-381 → widget registry array.
S-5 HIGH pipeline/page.tsx:116-255 single 140-line useEffect doing layout algorithm+lock derivation+node/edge building → extract pure pipelineToFlow().
S-6 MED monitoring/page.tsx 387 ln: 4 components defined inline + Grafana config + tab ladder re-deriving machine state.
S-7 MED machines own display data: monitoringPage.ts:51-71 mock generators with display labels; nexusApp.ts:163-175 English strings in actions.
S-8 MED dashboard/page.tsx:47-109 page owns network calls, alert() validation :52.
S-9 MED AdapterCard owns async side-effects + formatting.
S-10 LOW envelopeToTopology (120 ln layout) in same file as presentational components.

## 6. DEAD CODE
D-1 HIGH ModuleNode.tsx (59 ln) zero references (not in nodeTypes).
D-2 HIGH SettingsPanel.tsx superseded (see C-2).
D-3 HIGH dead machine surface nexusApp.ts (4 events, 5 actions, 4 guards, dataSource region, UserPreferences dup).
D-4/5 MED dead guards/actions monitoringPage, financePage.
D-6 MED lib/errors.ts isRetryable/errorMessage exported never imported.
D-7 MED TimeoutSkeleton never used; skeletons hand-rolled everywhere.
D-8 MED CAPABILITY_POLL_INTERVAL_MS unused.
D-9 MED dashboard/index.ts barrel: only Dashboard imported through it.
D-10 MED mock generators in prod: SpendingChart.tsx:179-200 mock data is the ONLY source of finance charts (finance/page.tsx:266-267, real transactions ignored); monitoringPage mock-on-failure masks outages.
D-11 LOW app/page.tsx PAGES duplicates Navbar NAV_ITEMS with divergent labels.
D-12 LOW store enableModule/disableModule/reloadModule never called.

## 7. CONTRACT BYPASS
X-1 CRITICAL ServiceTopology.tsx:144-151 relabels contract features to unrelated service names (providers→"Orchestrator", modules→"LLM Gateway", adapters→"ChromaDB", billing→"UI Service", pipeline→"Dashboard"); :172-179 injects hardcoded-healthy Bridge node; :182-193 substitutes 7-node fake topology. Health graph does not represent contract.
X-2 HIGH monitoringPage.ts:86-94,102-108 fabricates healthy/degraded statuses on fetch failure.
X-3 HIGH Navbar.tsx:99-104 hardcoded green "Connected" dot, ignores dataSource/auth regions.
X-4 HIGH two hardcoded adapter registries served to UI instead of envelope.adapters; alwaysConnected asserts connectivity unchecked.
X-5 HIGH financePage.ts:61-66 lock inference by category string-match, default locked:true when absent.
X-6 MED locked re-derived client-side from SSE PipelineState while envelope exposes authoritative locked+missing_fields — two sources of truth, two transports.
X-7 MED monitoring/page.tsx:197 prefers possibly-mocked machine features over envelope.
X-8 MED settings/page.tsx:58-79 hardcodes provider/adapter roster + env-var names client-side; envelope providers[] carries this.
X-9 MED dashboard/page.tsx:143-158 raw status strings — new contract status silently disappears.
X-10 LOW Grafana UIDs/port hardcoded.

## Priority
1. Fix/remove dead dataSource region + never-sent events (M-3, M-4, D-3)
2. Delete SettingsPanel, ModuleNode (C-2, D-1, D-2, T-3)
3. One contract types module (T-1..T-8, X-9)
4. lib/http.ts + endpoints.ts + classifyError everywhere (A-1..A-5)
5. createPollingRegion + shared data-source actor (M-1, M-2, M-6, M-10)
6. StatusBadge/ReasonList/WidgetShell/chartTheme (C-4, C-6, C-8..C-10)
7. Remove mock-on-failure + fake topology (X-1, X-2, D-10)
8. capability-selectors.ts single lock derivation (M-9, X-5, X-6)
