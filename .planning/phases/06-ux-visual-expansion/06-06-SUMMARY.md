---
phase: 06-ux-visual-expansion
plan: 06
subsystem: ui, orchestrator
tags: [adapter-credentials, env-vars, settings-ui, lock-unlock, docker-compose]
requires:
  - phase: 06-05
    provides: same-origin BFF proxy, capability contract with snapshot_source
provides:
  - env-var-based adapter lock/unlock in orchestrator capability contract
  - adapter key input fields in Settings page with .env persistence
  - unified credential flow — .env is single source of truth for adapter keys
  - correct admin proxy path prefix for dashboard reads
affects: [dashboard-adapter-cards, settings-page, orchestrator-capabilities]
tech-stack:
  added: [none]
  patterns: [env-var-credential-source, adapter-key-ui-fields, settings-api-env-persistence]
key-files:
  created: []
  modified: [orchestrator/admin_api.py, docker-compose.yaml, ui_service/src/app/settings/page.tsx, ui_service/src/app/api/settings/route.ts, ui_service/src/app/api/admin/[...path]/route.ts]
key-decisions:
  - "Adapter keys stored in .env as single source of truth, not CredentialStore SQLite"
  - "Orchestrator reads env vars for known adapters before falling back to CredentialStore"
  - "Settings API writes adapter keys to .env alongside provider keys"
  - "Admin proxy path must include /admin prefix for correct upstream routing"
patterns-established:
  - "Env-var-based adapter lock check: _has_adapter_env_credentials() in orchestrator"
  - "Adapter key fields in Settings page with same show/hide pattern as provider keys"
  - "Settings API POST writes both provider and adapter keys to .env in one flow"
duration: 20min
completed: 2026-02-17
---

# Phase 6 Plan 06: Unify Adapter Credentials to .env + Settings UI Summary

**Adapter keys configurable from Settings page, persisted to .env, driving orchestrator lock/unlock state — single source of truth**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-02-17T09:16:37Z
- **Completed:** 2026-02-17T09:35:14Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added `_ADAPTER_ENV_KEYS` mapping and `_has_adapter_env_credentials()` helper to orchestrator, enabling env-var-based adapter lock checks.
- Passed 7 adapter env vars to orchestrator service in docker-compose.yaml.
- Added adapter key section (OpenWeather, Clash Royale, Google Calendar) to Settings page with same show/hide pattern as provider keys.
- Modified Settings API to write adapter keys to .env and report presence booleans (`hasOpenweatherKey`, `hasClashRoyaleKey`, etc.).
- Fixed admin proxy upstream path prefix bug — proxy now correctly forwards `/api/admin/X` to `orchestrator:8003/admin/X`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire adapter env vars to orchestrator and use them for lock-state** — `a9eb2fc` (feat)
2. **Task 2: Add adapter key fields to Settings page and .env persistence** — `ec10cd8` (feat)
3. **Task 3: End-to-end verification + proxy path fix** — `83daf45` (fix)

## Files Modified

- `orchestrator/admin_api.py` — added `_ADAPTER_ENV_KEYS` dict, `_has_adapter_env_credentials()` function, rewrote `_gather_adapter_capabilities()` to check env vars before CredentialStore.
- `docker-compose.yaml` — added 7 adapter env vars (OPENWEATHER, CLASH_ROYALE, GOOGLE_CALENDAR) to orchestrator service block.
- `ui_service/src/app/settings/page.tsx` — added `ADAPTER_KEY_FIELDS` const, adapter key state, "Adapter Keys" UI section with show/hide toggle, adapter key status badges in config summary.
- `ui_service/src/app/api/settings/route.ts` — added adapter env vars to `EnvConfig`, writes adapter keys to .env in POST, reports adapter key presence in GET, replaced Admin API credential store flow.
- `ui_service/src/app/api/admin/[...path]/route.ts` — fixed upstream path prefix: `/admin/${pathParts.join('/')}`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed admin proxy upstream path prefix**
- **Found during:** Task 3     
- **Issue:** Proxy constructed upstream URL without `/admin` prefix — `/api/admin/capabilities` mapped to `orchestrator:8003/capabilities` (404) instead of `orchestrator:8003/admin/capabilities`.
- **Fix:** Changed `upstreamPath` from `/${pathParts.join('/')}` to `/admin/${pathParts.join('/')}`.
- **Files modified:** `ui_service/src/app/api/admin/[...path]/route.ts`
- **Commit:** `83daf45`

## Verification Results

- ✅ Capabilities endpoint: OpenWeather `locked=False` when `OPENWEATHER_API_KEY` is set
- ✅ Settings API GET: reports `hasOpenweatherKey: True` after key saved
- ✅ Settings API POST: writes adapter keys to .env (bind-mounted to host)
- ✅ Dashboard proxy: returns `source: live` with correct adapter lock states
- ✅ Other adapters correctly remain `locked=True` when keys not configured
- ✅ Build succeeds with all changes

## Self-Check: PASSED

All 5 modified files exist. All 3 task commits verified (a9eb2fc, ec10cd8, 83daf45).
