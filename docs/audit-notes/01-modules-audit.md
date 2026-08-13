# NEXUS Module/Audit Subsystem — Redundancy & SRP Audit
Scope: shared/modules/** (39 files, 6612 LOC), shared/audit/**, shared/schemas/**, shared/contracts/**, cross-boundary call sites in tools/builtin/** and orchestrator/admin_api.py.

## 1. DUPLICATED FUNCTIONALITY

### D1 — Bundle-hash computation implemented 4× (HIGH)
- Canonical helper unused: shared/modules/hashing.py:23-47 compute_bundle_hash
- artifacts.py:144-165 (build_from_dict) imports it at L16, never uses; re-implements sort→hash→concat→hash
- artifacts.py:309-318 verify_bundle_hash third copy
- drafts.py:158,251 raw hashlib.sha256 instead of compute_sha256
- audit.py:79 + audit/redaction.py:29 identical truncated-fingerprint idiom ([:16])
- audit/store.py:83-84 _canonical_hash fourth entry point
→ Route all hashing through hashing.py; add fingerprint16().

### D2 — "Collect 3 module files, build bundle" repeated 3× verbatim (HIGH)
- approval.py:36-54, drafts.py:520-531, tools/builtin/module_installer.py:123-140 (plus redundant re-import L136)
- File triple ["adapter.py","test_adapter.py","manifest.json"] hardcoded at drafts.py:152,239; approval.py:40; module_installer.py:123-131
→ ArtifactBundleBuilder.build_for_module(module_id, modules_dir) + MODULE_BUNDLE_FILES constant.

### D3 — module_id parsing: parser exists (identifiers.py:29-76 parse_module_id) but 8 call sites re-split inline (MED)
- Only module_installer.py:25, module_validator.py:31 use it
- Inline: gc.py:46; approval.py:21,36; drafts.py:129-133,305-306,492-493,635-636 (3 without length check); loader.py:264-266; tools/nexus_dev.py:184
- Path construction Path(modules_dir)/category/platform open-coded at approval.py:22,37; gc.py:47; drafts.py:134,307,637; loader.py:120,249-252; manifest.py:116; module_installer.py:78
→ ModuleIdentifier.dir()/manifest_path(); forbid raw split.

### D4 — Adapter class-name derivation duplicated (LOW): manifest.py:97 ≡ templates/adapter_template.py:160 → identifiers.py::derive_class_name.

### D5 — Timestamps 25+ sites, 3 incompatible formats (HIGH — correctness bug)
- isoformat()+"Z" → invalid "+00:00Z": drafts.py:162,254,380,486,542,653,674; approval.py:103,157; audit.py:140,188,413; versioning.py:165,354; artifacts.py:173; gc.py:52; validation_types.py:65,118
- Correct isoformat(): manifest.py:82,83,119; audit/store.py:216
- Naive utcnow(): registry.py:69,117,134,194; credentials.py:129; loader.py:158
- output_contract.py:55-63 validator rejects "+00:00Z" (does replace('Z','+00:00') → "+00:00+00:00" → raises); round-trip broken
→ shared timeutil.py::utc_now_iso(); delete +"Z" everywhere.

### D6 — SQLite store boilerplate duplicated across 4 stores (MED)
- audit/store.py:120-133 (WAL yes); registry.py:31-65 (no WAL, org_id migration :56-62); versioning.py:69-134 (no WAL, migrations :117-130; JSON rehydration dup 3×: 243-249,292-297,418-423 vs store.py:345-351 generic _row_to_dict); credentials.py:63-109 (table-rebuild migration :69-106)
- org_id branch SQL dup 9×: registry.py:93-101,146-154,196-205; versioning.py:222-239,270-287,404-413; credentials.py:146-155,177-185,194-202,208-214
→ shared/persistence/SqliteStore base (connect+PRAGMA+migrate+_row_to_dict+_build_where).

### D7 — _client_ip copy-pasted: audit/context.py:62-68 ≡ audit/decorator.py:28-34 (LOW).
### D8 — from_dict filter idiom 6×: manifest.py:43,128; drafts.py:79; audit.py:165,290; versioning.py:57; artifacts.py:73-81 (LOW) → serde.py mixin.
### D9 — Two forbidden-import checkers (MED): static_analysis.py:24-85 emits strings; contracts.py:49-76 string-parses them back ("Import '" split); sandbox_service/runner.py:115 third consumer → return structured ValidationEntry, delete parser.

## 2. SRP VIOLATIONS

### S1 — DraftManager (drafts.py:82-700) god-class (HIGH)
6 responsibilities: FS mgmt (create 109-201, discard 358-401), hashing (:158,251), diffing (get_diff 282-356, import difflib inside :293), validation orch (validate_draft 445-577, 133 lines), install orch (promote_draft 579-700), audit emission (7 inline blocks :180,261,342,387,547,679).
validate_draft writes scratch into LIVE modules tree (:496 modules_dir/f"{category}_draft_{draft_id}") — crash leaves phantom tree that manifest.discover() (manifest.py:138 rglob) picks up. Late imports :293,512,520,662.
→ Split DraftStore/DraftValidator/DraftPromoter; scratch outside modules_dir; audit via decorator.

### S2 — approval.py:120-231 reject_module conflates 3 decisions (HIGH)
Branches on truthiness of free-text feedback (:160); drives LLM repair incl. job minting + synthetic validation report (:169-185); queues GC (:211); emits audit twice with different shapes (:187-197 vs :213-222). Repair block swallows all exceptions (:184-185) with manifest already persisted VALIDATING (:161-162) — partial transition, no compensation.
→ reject_for_repair()/reject_terminal(); repair via event handler on ModuleRejected.

### S3 — AuditStore.record() 101 lines (store.py:193-293) (MED): redaction+manual BEGIN IMMEDIATE/COMMIT/ROLLBACK+id via SELECT MAX+hash+INSERT+OTel → extract _next_chain_link + @with_metrics.

### S4 — DevModeAuditLog.log_action dual-writer (audit.py:384-443) (MED): JSONL write :420 then differently-shaped SQLite write :425-441; no atomicity — stores diverge permanently (acknowledged :365-368) → AuditStore single write path; JSONL derived from iter_events().

### S5 — ModuleManifest DTO+repository+discovery (manifest.py:46-146) (MED): save():114-121 writes FS + silently mutates updated_at :119; discover():132-146 walks tree, import logging inside :142 → extract ManifestRepository.

### S6 — ModuleLoader mutates lifecycle state on import (loader.py:97-182) (HIGH): load_module overwrites status → INSTALLED :163 / FAILED :177 — read path rewriting write-path state.

### S7 — audit_action decorator couples audit to FastAPI (decorator.py:80-165, HTTPException :135) (LOW) — why DevModeAuditLog exists as parallel path.

## 3. STATE-MACHINE FRAGMENTATION (HIGH)
No declared transition table. ModuleStatus (manifest.py:16-25) 8 states; transitions only in prose.

Guards: G1 approval.py:89 (doubled enum/value compare — status typed str at manifest.py:78); G2 module_installer.py:91 FAILED; G3 module_installer.py:98 (doubled compare copy-paste); G4 loader.py:84; G5/G6 drafts.py:232,478; G7 drafts.py:616; G8 versioning.py:340 (string literal, 3rd vocabulary); G9 module_validator.py:280 (string, 4th vocabulary).

Unguarded writes: W1 approval.py:100 →APPROVED (guarded); W2 approval.py:161 →VALIDATING unguarded from any state; W3 approval.py:208 →FAILED; W4 loader.py:163 →INSTALLED (loader bypasses approval!); W5 loader.py:177 →FAILED; W6 loader.py:216 →UNINSTALLED; W7 loader.py:246 →DISABLED; W8 loader.py:272 →PENDING (enable resets APPROVED to PENDING); W9 registry.py:70 →INSTALLED (mutates caller's manifest inside install()); W10 registry.py:109/113 via _update_status :192-206 raw SQL; W11 module_validator.py:264 ternary; W12 module_installer.py:185; W13 :248; W14 module_builder.py:246,386 →PENDING; W15 tools/nexus_dev.py:239 writes VALIDATED directly — documented guard bypass.

Status stored redundantly: manifest.json (manifest.py:78) AND modules.status SQLite (registry.py:46), no reconciliation — registry updates DB not manifest; loader updates manifest not DB. NO SINGLE SOURCE OF TRUTH.
→ One TRANSITIONS table + transition(module_id, to_status, actor) that validates, persists to ONE store, emits audit; all 15 writers call it; delete 9 guards.

## 4. DEAD / REDUNDANT CODE
- MED: validation_types.py entire module 119 LOC — zero prod importers (only tests/unit/test_shared_modules_dedup.py)
- MED: compute_bundle_hash (hashing.py:23-47) imported, never called
- MED: scenarios/** entire package ~250 LOC (rest_api, oauth2_flow, paginated_api, file_parser, rate_limited_api, registry) — no external importer
- MED: policy.py ApprovalPolicy/DEFAULT_APPROVAL_POLICY — zero importers (self-declared scaffold)
- LOW: contracts.py:323-347 validate_generator_response; artifacts.py:296-320 verify_bundle_hash; :229-253 self_check; :256-293 diff_bundles; :109-121 hash_file; security_policy.py:26-35 SAFE_BUILTINS; identifiers.py:79-93 validate_module_id; :50-52 legacy "_" branch (manifest_schema forbids it)
- HIGH: manifest_schema.json — the "schema check" module_validator.py:381-393 never opens the file; assigns manifest = load() unused, returns passed=True; only a test reads the JSON
- LOW: output_contract.py:154-161 no-op field_validator; module_validator.py:397 module_id.replace("/","/") self-replace no-op
- LOW: audit.py:445-485 get_events returns OLDEST not most recent (breaks at first limit matches :482-483; events[-limit:] no-op)

## 5. CONTRACT DRIFT

### C1 — Four overlapping validation-result types (HIGH)
- ValidationResults (manifest.py:29-43, "legacy" per module_validator.py:252-253)
- ValidationResult/Entry (validation_types.py:19-119, DEAD)
- ValidationReport + StaticCheckResult/RuntimeCheckResult/FixHint (module_validator.py:49-120, the real one)
- ad-hoc {"valid": bool, "errors":[...]} (contracts.py:147-151, 297-300)
- module_validator.py:252-276 translation layer #3→#1; :280-330 second translation to legacy dict
→ Promote ValidationReport to shared/modules/, delete rest + both translation layers.

### C2 — Two parallel lifecycle enums, no mapping (MED)
ModuleStatus vs DraftState (drafts.py:27-34). promote_draft crosses FSMs by calling install_module which requires APPROVED — a status draft FSM can't produce → validated draft can NEVER install without out-of-band edit (= nexus_dev.py:239 bypass). Third vocabulary versioning.py:33,92 VALIDATED/ACTIVE/ARCHIVED; fourth ValidationReport.status.
→ Map DraftState→ModuleStatus at boundary; shared enum for version status.

### C3 — Two ErrorCode enums, same name, disjoint members (MED)
contracts.py:19-29 vs output_contract.py:25-35. test_template.py:120 imports from output_contract but generated body :155-159 references ErrorCode.MISSING_METHOD which exists only in contracts.py → generated tests AttributeError.
→ Rename ContractErrorCode / AdapterErrorCode; fix template import.

### C4 — Three overlapping result envelopes; "canonical" unused (HIGH)
AdapterRunResult (output_contract.py:113-190, claimed canonical L10, NO adapter imports it — only test_template string) vs AdapterResult (adapters/base.py:63-88, the real one) vs ToolResult (tools/base.py:53-92); fourth ad-hoc {"status": ...} dicts throughout drafts/approval/versioning/module_installer.
→ Wire AdapterRunResult into BaseAdapter.run() or delete output_contract.py.

### C5 — manifest_schema.json incompatible with ModuleManifest (HIGH)
Schema requires module_id/entrypoint/capabilities, additionalProperties:false. to_dict() emits NONE of those (module_id is @property absent from asdict; field named entry_point; no capabilities) and ~20 forbidden fields. Every real manifest fails its own schema; nothing catches it (check doesn't load schema).
→ Generate schema from ModuleManifest or delete; make check actually validate.

### C6 — Two AuditEvent shapes (MED)
audit.py:317-345 (JSONL: event_id/action/actor/module_id/draft_id) vs audit/store.py:139-153 (SQLite: 13 fields, hash chain). Lossy inline mapping audit.py:428-441; actor can differ between the two rows for same action; JSONL no hash chain.
→ One AuditEvent in shared/audit/; JSONL = serialization format.

## Event-Driven / CQRS Assessment
- Append-only event sourcing: PARTIAL — audit store triggers+chain correct (store.py:174-189) but is a side-log, not source of truth; nothing replays; iter_events (store.py:370) no caller.
- Idempotency: ABSENT — no idempotency key on any mutation; retried approve appends duplicate row; record_version strftime id (versioning.py:162) → retry duplicates; gc.py:57 overwrites marker.
- Single source of truth: VIOLATED — status in 2 places, 15 writers; hash 4 ways; validation 4 types.
- CQRS: VIOLATED — loader (read path) writes status :163,177; registry.install mutates caller manifest; drafts.get_diff (read) emits audit :342-348.
- Fail-closed audit: INCONSISTENT — store.record fail-closed :290; decorator → HTTP 500 AFTER mutation applied (decorator.py:135-141); DevModeAuditLog fail-closed only on SQLite leg.

## Consolidation Priority
1. One ModuleStatus transition table + transition() writer; collapse 9 guards/15 writers/2 stores.
2. One validation result type (ValidationReport); delete validation_types.py + 2 translation layers.
3. One bundle-hash entry point + build_for_module(); delete 3 inline copies.
4. utc_now_iso(); fix 18 invalid "+00:00Z" sites.
5. Split DraftManager; move scratch dirs out of modules_dir.
6. AuditStore single audit writer; JSONL derived.
7. Delete dead code (~450 LOC): validation_types, scenarios/**, policy.py, verify_bundle_hash, self_check, diff_bundles, hash_file, SAFE_BUILTINS, validate_generator_response, validate_module_id.
8. Reconcile or delete manifest_schema.json + output_contract.py.
