/**
 * Shared constants for the Playwright E2E suite.
 *
 * Base URLs default to the docker-compose stack's host-mapped ports (see
 * docker-compose.yaml: `ui_service` maps host 5001 -> container 5000,
 * `dashboard` maps host 8001 -> container 8001). Override via env vars to
 * point at a different stack (e.g. `npm run dev` on 3000 for local UI-only
 * iteration against a stack started with `make up`).
 */

export const E2E_BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5001';

export const E2E_DASHBOARD_URL =
  process.env.E2E_DASHBOARD_URL ?? 'http://localhost:8001';

/** `docker compose` service key (docker-compose.yaml) for the dashboard, NOT its container_name. */
export const DASHBOARD_COMPOSE_SERVICE = 'dashboard';

/** Short fetch timeout (ms) used by the global-setup availability probe. */
export const PROBE_TIMEOUT_MS = 5000;
