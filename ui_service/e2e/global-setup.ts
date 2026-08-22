/**
 * Playwright global setup — service-availability gate.
 *
 * These specs run against the REAL docker-compose stack (RESEARCH Pitfall 4:
 * Playwright's `page.route()` interception does not reliably deliver events
 * to `EventSource` connections, so SSE tests must never mock the endpoint).
 * If the UI or the dashboard SSE origin is unreachable, fail fast with a
 * single clear error naming the missing service and the command to start it,
 * instead of letting every test hang on its own timeout.
 */

import { E2E_BASE_URL, E2E_DASHBOARD_URL, PROBE_TIMEOUT_MS } from './util';

async function probe(name: string, url: string): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    await fetch(url, { signal: controller.signal });
  } catch (err) {
    throw new Error(
      `[global-setup] ${name} is unreachable at ${url}. ` +
        `Start the stack with \`make up\` before running \`make ui-e2e\`. ` +
        `(${err instanceof Error ? err.message : String(err)})`
    );
  } finally {
    clearTimeout(timer);
  }
}

export default async function globalSetup(): Promise<void> {
  await probe('ui_service', E2E_BASE_URL);
  await probe('dashboard_service SSE origin', `${E2E_DASHBOARD_URL}/health`);
}
