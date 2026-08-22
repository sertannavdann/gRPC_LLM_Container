---
phase: 08-co-evolution-approval
plan: 13
subsystem: ui
tags: [playwright, e2e, sse, pipeline, testing]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: "08-03's SSE payload contract and 08-08's pipelinePageMachine-driven pipeline page (connection region, Live/Disconnected toolbar text)"
provides:
  - "First test framework of any kind in ui_service/ — @playwright/test, chromium-only"
  - "ui_service/e2e/pipeline-sse.spec.ts — connect/reconnect/error specs against the real dashboard SSE endpoint"
  - "make ui-e2e / make ui-e2e-full Makefile targets"
affects: []

# Tech tracking
tech-stack:
  added: ["@playwright/test ^1.62.1 (devDependency, chromium browser only)"]
  patterns:
    - "Service-availability gate in Playwright globalSetup: short-timeout fetch probes fail the whole run fast and clearly instead of letting individual SSE tests hang"
    - "Disruptive-by-default-off E2E: E2E_ALLOW_RESTART=1 opt-in flag gates any test.skip()-guarded scenario that actually restarts/stops a docker-compose service, with a finally-block restore"
    - "context.setOffline() as a non-mocking way to force a real EventSource onerror in the browser, used as the safe-default fallback for the error-handling test when disruption is not opted into"

key-files:
  created:
    - ui_service/playwright.config.ts
    - ui_service/e2e/global-setup.ts
    - ui_service/e2e/util.ts
    - ui_service/e2e/pipeline-sse.spec.ts
  modified:
    - ui_service/package.json
    - ui_service/package-lock.json
    - Makefile
    - .gitignore

key-decisions:
  - "Base URL default corrected to http://localhost:5001 (not 3000): docker-compose.yaml maps ui_service host port 5001 -> container port 5000 (Dockerfile EXPOSE 5000/PORT=5000); the RESEARCH.md interfaces note assumed port 3000, which would make `make ui-e2e` fail against the actual compose stack every time. Still overridable via E2E_BASE_URL for local `npm run dev` iteration on 3000."
  - "docker compose service key is `dashboard`, not the container_name `dashboard_service` — confirmed by reading docker-compose.yaml's `dashboard:` service block directly; `docker compose restart/stop/start` take the compose service key."
  - "Non-disruptive error-handling fallback uses context.setOffline() instead of skipping coverage — this is a real network-layer disconnect (not EventSource mocking/page.route() interception, which RESEARCH Pitfall 4 specifically rules out), so REQ-018's error-handling scenario is exercised deterministically on every `make ui-e2e` run without ever touching the shared dashboard container."
  - "Deviation from RESEARCH.md's sketched tests/e2e/ root location: specs live in ui_service/e2e/ instead, per the plan's own <interfaces> note, because the npm dependency tree, tsconfig path aliases, and Playwright binary all live under ui_service/."

patterns-established:
  - "Comments referencing acceptance-criteria-checked literal strings (webServer, page.route() ) must avoid reproducing those exact substrings verbatim, or automated grep-based acceptance checks false-positive on prose, not code."

requirements-completed: ["REQ-018"]

# Metrics
duration: 45min
completed: 2026-08-22
---

# Phase 08 Plan 13: Pipeline SSE E2E Tests Summary

**Playwright installed fresh into `ui_service/` (first test framework in that package) with a service-availability gate and three real-service specs covering initial SSE connect, dashboard-restart reconnection, and SSE-failure error handling — no `EventSource` mocking anywhere, disruptive scenarios opt-in only.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 2/2 completed

## Accomplishments

- `@playwright/test ^1.62.1` (Microsoft-maintained, Approved in RESEARCH's Package Legitimacy Audit) installed as a devDependency with chromium-only browser binaries (`npx playwright install --with-deps chromium`, ~358MB download, completed cleanly on macOS)
- `ui_service/playwright.config.ts` — `testDir: './e2e'`, no dev-server-launcher entry (tests run against `make up`'s real stack), 60s test timeout / 15s expect timeout so a hung SSE connection fails fast, `retries: 0`, `reporter: 'list'`, `trace: 'retain-on-failure'`
- `ui_service/e2e/global-setup.ts` — probes the UI and the dashboard's `/health` with a 5s `AbortController` timeout each; verified live that with no services running it fails in ~5s with a single clear `Start the stack with make up` error rather than letting any test hang on its own 60s timeout
- `ui_service/e2e/pipeline-sse.spec.ts` — exactly three tests (verified via `playwright test --list`): initial connect (Live indicator + `.react-flow` canvas visible), reconnect after `docker compose restart dashboard` (gated by `E2E_ALLOW_RESTART`, restores the container in a `finally`), and SSE-failure error handling (real `docker compose stop dashboard` disruption when `E2E_ALLOW_RESTART` is set, or a non-disruptive `context.setOffline()` real network-level disconnect by default — REQ-018's error scenario is never skipped)
- `make ui-e2e` (safe default, non-disruptive) and `make ui-e2e-full` (`E2E_ALLOW_RESTART=1`) Makefile targets added, following the repo's `@printf` colour convention (verified zero `@echo` in the new target block)

## Task Commits

1. **Task 1: Install and configure Playwright with a service-availability gate** - `6525204` (feat)
2. **Task 2: Connect / reconnect / error specs against the real SSE stream** - `5522ec7` (feat)
3. **Fix: avoid literal `webServer` substring in a config comment** - `9567262` (fix, Rule 1 — see Deviations)

## Files Created/Modified

- `ui_service/playwright.config.ts` - Playwright root config: `testDir`, `globalSetup`, bounded timeouts, chromium-only project, baseURL from `E2E_BASE_URL`
- `ui_service/e2e/global-setup.ts` - Fetches UI + dashboard `/health` with a 5s timeout each; throws one clear, named error on failure
- `ui_service/e2e/util.ts` - Shared `E2E_BASE_URL`/`E2E_DASHBOARD_URL`/`DASHBOARD_COMPOSE_SERVICE`/`PROBE_TIMEOUT_MS` constants
- `ui_service/e2e/pipeline-sse.spec.ts` - Three specs: connect, reconnect (disruptive, opt-in), error handling (disruptive opt-in / non-disruptive `setOffline` fallback)
- `ui_service/package.json` / `ui_service/package-lock.json` - `@playwright/test` devDependency; `e2e`/`e2e:ui` npm scripts
- `Makefile` - `ui-e2e` and `ui-e2e-full` targets
- `.gitignore` - `ui_service/test-results/`, `ui_service/playwright-report/`, `ui_service/blob-report/`

## Decisions Made

- Set the default `E2E_BASE_URL` to `http://localhost:5001` rather than the plan interface's stated `3000`, after reading `docker-compose.yaml`'s `ui_service` block (`ports: "5001:5000"`) and the UI Dockerfile (`EXPOSE 5000` / `ENV PORT=5000`) — port 3000 is Next.js's `next dev` default, not the port the actual compose stack exposes, so a literal 3000 default would make `make ui-e2e` fail every time against `make up`, violating this plan's own verification bullet ("With the stack up: `make ui-e2e` passes"). Still fully overridable via `E2E_BASE_URL` for anyone iterating against `npm run dev` on 3000 directly.
- Used `docker compose` (v2 syntax, confirmed as the only invocation used elsewhere in the Makefile, e.g. `docker compose version`) with the compose service key `dashboard` (not the container_name `dashboard_service`) for all restart/stop/start commands, per direct inspection of `docker-compose.yaml`'s `dashboard:` service block.
- Chose `context.setOffline()` over skipping the error-handling scenario entirely when `E2E_ALLOW_RESTART` is unset — this forces a genuine browser-level network disconnect (not `page.route()` interception, which RESEARCH Pitfall 4 specifically identifies as unreliable for `EventSource`), so the "no silent blank state" contract is verified deterministically on every default `make ui-e2e` run without ever touching the shared dashboard container.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment text collided with an acceptance-criteria grep pattern**
- **Found during:** Task 1 self-verification (running the plan's own acceptance-criteria greps after committing)
- **Issue:** `playwright.config.ts`'s explanatory comment used the literal string `` `webServer` `` to explain why no dev-server-launcher key was configured. The acceptance criterion `grep -c "webServer" ui_service/playwright.config.ts` returns 0 expects zero occurrences of that substring anywhere in the file, including comments — the comment itself caused a false-positive match (count 1, not 0).
- **Fix:** Reworded the comment to describe the same intent ("no dev-server-launcher entry") without reproducing the literal `webServer` substring. Same fix pattern applied proactively to `pipeline-sse.spec.ts`'s comments referencing `page.route()`, which had the identical collision with that acceptance criterion's grep (caught before committing Task 2, so no separate fix commit was needed there).
- **Files modified:** `ui_service/playwright.config.ts`
- **Commit:** `9567262`

**2. [Rule 1 - Bug] RESEARCH-sourced default base URL did not match the actual docker-compose port mapping**
- **Found during:** Task 1, `<read_first>` review of `docker-compose.yaml`
- **Issue:** The plan's `<interfaces>` context (sourced from 08-RESEARCH.md) stated the UI runs "on port 3000", but `docker-compose.yaml`'s `ui_service` block maps host `5001` to container `5000`, and the UI's own `Dockerfile` sets `EXPOSE 5000` / `ENV PORT=5000`. A literal `3000` default would make every `make ui-e2e` run against the real compose stack fail at `global-setup`'s UI-reachability probe.
- **Fix:** Set `E2E_BASE_URL` default to `http://localhost:5001`, documented the discrepancy inline in `ui_service/e2e/util.ts`'s comment, still fully overridable via env var.
- **Files modified:** `ui_service/e2e/util.ts`
- **Commit:** `6525204`

## Issues Encountered

The worktree's initial HEAD was on an unrelated, much older commit (`6b2027b "Cohesion (#14)"`, no `.planning/` directory at all) despite being on the correct `worktree-agent-*` branch — the same pre-existing worktree-provisioning issue documented in the 08-03/08-07/08-08 summaries. The mandatory `worktree_branch_check` step's `git reset --hard 7cc4438...` corrected this before any plan file could be read; the working tree was clean beforehand, so nothing was lost.

`ui_service/node_modules` was absent; `npm ci` reproduced the existing lockfile's dependency tree (no `package.json`/lockfile changes from that step) before `@playwright/test` was added on top.

Docker was not running in this environment (`Cannot connect to the Docker daemon`), so `make ui-e2e` / `make ui-e2e-full` could not be executed against live services in this session. What WAS verified locally, without services running:
- `cd ui_service && npx tsc --noEmit -p tsconfig.json` — clean, no errors
- `cd ui_service && npx playwright test --list` — lists exactly the 3 required tests
- `cd ui_service && npx eslint e2e/ playwright.config.ts` — clean, no errors
- `cd ui_service && npx playwright test` (services down) — **fails in ~5 seconds** with the `global-setup.ts` message `[global-setup] ui_service is unreachable at http://localhost:5001. Start the stack with make up before running make ui-e2e.` — this directly confirms the plan's own `<verification>` bullet: "With the stack down: the suite fails immediately with the global-setup message naming the unreachable service, rather than hanging."

**Not verified in this session** (requires `make up` / a running docker-compose stack, per the coordination notes' documented exemption): actual pass/fail of the three specs against a live dashboard SSE stream, the real `docker compose restart dashboard` reconnection sequence, and the real `docker compose stop dashboard` disruption path. All three code paths were read against the actual `dashboard_service/pipeline_stream.py` (2s interval, `/health` public path) and `ui_service/src/machines/pipelinePage.ts` (`connection` region: `connecting -> connected -> reconnecting -> connected`) source to ensure the assertions match real behavior, but live execution is deferred to a services-up environment.

## User Setup Required

None for this plan's own deliverables. To run the suite live: `make up` (bring up the docker-compose stack), then `make ui-e2e` (safe default) or `E2E_ALLOW_RESTART=1 make ui-e2e-full` (exercises the disruptive restart/stop scenarios, service is always restored).

## Next Phase Readiness

- REQ-018 is satisfied: all three specified scenarios (initial connect, reconnect after dashboard restart, error handling on SSE failure) are implemented as real-service Playwright tests, none of which mock `EventSource`.
- No blockers for downstream plans. The suite is self-contained within `ui_service/` and does not change any runtime backend or frontend behavior — it is purely additive test infrastructure.
- Follow-up (not blocking, noted for whoever next has Docker access): run `make ui-e2e` and `E2E_ALLOW_RESTART=1 make ui-e2e-full` against a live `make up` stack at least once to confirm the specs pass for real, since this session could not do so.

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-22*
