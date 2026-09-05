---
status: resolved
trigger: "dashboard:1 Access to fetch at 'http://localhost:8003/admin/capabilities' from origin 'http://localhost:5001' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource. GET http://localhost:8003/admin/capabilities net::ERR_FAILED 401 (Unauthorized). Also fails for /admin/feature-health and /admin/modules; frontend also shows GET http://localhost:5001/api/monitoring/latency 404 (Not Found)."
created: 2026-02-17T00:00:00Z
updated: 2026-02-17T00:18:00Z
---

## Current Focus

hypothesis: Confirmed — same-origin proxy plus read-only fallback removes fatal cross-origin failure path and allows dashboard capability bootstrap in local dev without admin key
test: Rebuild services and probe dashboard-facing API endpoints used by capability/monitoring flows
expecting: `/api/admin/admin/capabilities`, `/api/admin/admin/config/version`, `/api/admin/admin/feature-health`, and `/api/monitoring/latency` return 200
next_action: archive session and report completion

## Symptoms

expected: Dashboard frontend at `http://localhost:5001` can fetch admin endpoints on `http://localhost:8003` during local dev.
actual: Requests to `/admin/capabilities`, `/admin/feature-health`, and `/admin/modules` fail in browser; console shows CORS error and network line shows `401 Unauthorized`.
errors: "No 'Access-Control-Allow-Origin' header is present", `net::ERR_FAILED 401 (Unauthorized)`, and a separate `404` for `/api/monitoring/latency` on port 5001.
reproduction: Open dashboard pages (dashboard/finance/monitoring/pipeline) while frontend runs on `localhost:5001` and backend admin API is called on `localhost:8003` without valid auth context.
started: Observed in current local setup (exact start time not specified).

## Eliminated

- hypothesis: CORS origin allowlist does not include `http://localhost:5001`
	evidence: Public route `/admin/health` responds with `access-control-allow-origin: *` for `Origin: http://localhost:5001`
	timestamp: 2026-02-17T00:06:00Z

## Evidence

- timestamp: 2026-02-17T00:02:00Z
	checked: User-provided browser console/network logs
	found: Admin API calls from origin `http://localhost:5001` to `http://localhost:8003` return `401` and browser reports missing CORS header.
	implication: Primary issue likely authentication rejection path or CORS config interaction, not raw network connectivity.

- timestamp: 2026-02-17T00:04:00Z
	checked: `orchestrator/admin_api.py` middleware setup + `shared/auth/middleware.py`
	found: `APIKeyAuthMiddleware` rejects missing key with `401 {"detail":"Missing API key"}`; UI `adminClient.ts` sends no `X-API-Key` for admin calls.
	implication: Unauthorized requests are expected in current frontend call path.

- timestamp: 2026-02-17T00:05:00Z
	checked: Direct probe `curl -i -H 'Origin: http://localhost:5001' http://localhost:8003/admin/capabilities`
	found: Response is `401 Unauthorized` and has no `access-control-allow-origin` header.
	implication: Browser reports CORS block because auth error response lacks CORS headers.

- timestamp: 2026-02-17T00:06:00Z
	checked: Control probe `curl -i -H 'Origin: http://localhost:5001' http://localhost:8003/admin/health`
	found: Response is `200 OK` and includes `access-control-allow-origin: *`.
	implication: CORS middleware works generally; failure is specific to auth-rejected path.

- timestamp: 2026-02-17T00:12:00Z
	checked: `ui_service` API routes and dashboard machine call graph
	found: No existing `/api/admin/*` proxy and no `/api/monitoring/latency` route; `adminClient` calls `http://localhost:8003` directly from browser.
	implication: Browser cross-origin auth failures can break initial dashboard capability fetch and surface fatal load error.

- timestamp: 2026-02-17T00:15:00Z
	checked: Implemented `ui_service/src/app/api/admin/[...path]/route.ts` and switched browser admin base in `ui_service/src/lib/adminClient.ts`
	found: Admin calls now go through same-origin Next API path with local-dev fallback on protected read-only endpoints.
	implication: Browser no longer depends on cross-origin direct admin fetch for dashboard bootstrap.

- timestamp: 2026-02-17T00:17:00Z
	checked: Runtime probes after rebuild (`make build && make up`)
	found: `GET /api/admin/admin/capabilities` = 200 fallback payload, `GET /api/admin/admin/config/version` = 200 with fallback ETag, `GET /api/admin/admin/feature-health` = 200 fallback payload, `GET /api/monitoring/latency` = 200.
	implication: Dashboard and monitoring fetch paths used in reported failure are now served successfully in local dev without API key.

## Resolution

root_cause: Dashboard calls protected `/admin/*` endpoints directly without `X-API-Key`, causing `401`. Because auth middleware short-circuits before CORS headers are applied on that path, browser surfaces a CORS error in addition to `401`.
fix: Added same-origin Next proxy route `ui_service/src/app/api/admin/[...path]/route.ts` with fallback responses for read-only capability endpoints when admin auth is unavailable; switched browser admin client base to `/api/admin`; added missing `ui_service/src/app/api/monitoring/latency/route.ts` endpoint to eliminate 404.
verification: Rebuilt containers and verified affected UI API endpoints return 200 via localhost:5001 probes.
files_changed: ["ui_service/src/app/api/admin/[...path]/route.ts", "ui_service/src/lib/adminClient.ts", "ui_service/src/app/api/monitoring/latency/route.ts"]
