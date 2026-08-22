/**
 * Pipeline SSE E2E specs (REQ-018).
 *
 * These tests exercise the pipeline page's `pipelinePageMachine` `connection`
 * region (ui_service/src/machines/pipelinePage.ts) against the REAL
 * dashboard SSE endpoint (`GET /stream/pipeline-state`, 2s interval,
 * dashboard_service/pipeline_stream.py). Per RESEARCH.md Pitfall 4,
 * Playwright's request-interception API does not reliably deliver events
 * to `EventSource` connections — this suite never mocks the endpoint. The
 * toolbar text asserted below ("Live" / "Disconnected", green/red Wifi
 * icons) comes straight from ui_service/src/app/pipeline/page.tsx.
 *
 * Disruptive scenarios (dashboard restart/stop) are gated behind
 * `E2E_ALLOW_RESTART=1` so a routine `make ui-e2e` run never bounces a
 * developer's running stack. Run `E2E_ALLOW_RESTART=1 make ui-e2e-full` to
 * exercise the full disruptive path. Disruptive tests always restore the
 * dashboard service in a `finally` block even if an assertion fails.
 */

import { test, expect } from '@playwright/test';
import { execSync } from 'node:child_process';
import { DASHBOARD_COMPOSE_SERVICE } from './util';

const ALLOW_RESTART = Boolean(process.env.E2E_ALLOW_RESTART);

function dockerCompose(args: string): void {
  execSync(`docker compose ${args}`, { timeout: 60_000, stdio: 'pipe' });
}

test.describe('Pipeline SSE (REQ-018)', () => {
  test('initial connect: shows the Live indicator', async ({ page }) => {
    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    // Explicit-state contract — the canvas itself must also be present, not
    // just the toolbar text (no blank panel behind a stray "Live" label).
    await expect(page.locator('.react-flow')).toBeVisible();
  });

  test.describe(() => {
    test.skip(!ALLOW_RESTART, 'set E2E_ALLOW_RESTART=1 to run the disruptive restart test');

    test('reconnect after dashboard restart: Disconnected -> Live without a page reload', async ({ page }) => {
      await page.goto('/pipeline');
      await expect(page.getByText('Live')).toBeVisible();

      try {
        // `docker compose restart` stops then starts the container — no
        // separate start step needed on the happy path.
        dockerCompose(`restart ${DASHBOARD_COMPOSE_SERVICE}`);
        await expect(page.getByText('Disconnected')).toBeVisible({ timeout: 20_000 });
        // Native EventSource auto-retry brings it back once the dashboard's
        // healthcheck (10s interval, 15s start_period) reports healthy —
        // no page.reload() anywhere in this test.
        await expect(page.getByText('Live')).toBeVisible({ timeout: 40_000 });
      } finally {
        // Safety net: guarantee the shared dashboard container is left
        // running even if an assertion above threw mid-sequence.
        try {
          dockerCompose(`up -d ${DASHBOARD_COMPOSE_SERVICE}`);
        } catch {
          // best-effort restore; a failure here does not mask the real
          // test failure being reported above it
        }
      }
    });
  });

  test('error handling on SSE failure: explicit Disconnected, never blank or crashed', async ({
    page,
    context,
  }) => {
    if (ALLOW_RESTART) {
      // Real backend disruption — stop the dashboard container entirely so
      // the SSE endpoint is genuinely unreachable, matching REQ-018's
      // "dashboard unreachable" scenario at the network layer.
      await page.goto('/pipeline');
      await expect(page.getByText('Live')).toBeVisible();

      try {
        dockerCompose(`stop ${DASHBOARD_COMPOSE_SERVICE}`);
        await expect(page.getByText('Disconnected')).toBeVisible({ timeout: 20_000 });
        await expect(page.locator('.react-flow')).toBeVisible();
      } finally {
        try {
          dockerCompose(`start ${DASHBOARD_COMPOSE_SERVICE}`);
          await expect(page.getByText('Live')).toBeVisible({ timeout: 40_000 });
        } catch {
          // best-effort restore
        }
      }
      return;
    }

    // Non-disruptive default (E2E_ALLOW_RESTART unset): force a genuine
    // network-level disconnect scoped to this browser context via
    // `context.setOffline()`. This is NOT request interception/mocking —
    // RESEARCH Pitfall 4 rules out Playwright's route-interception API
    // faking EventSource traffic specifically; setOffline cuts the real
    // network path so the browser's native EventSource onerror handler
    // fires for real, without touching the shared dashboard container
    // other tests/developers rely on. Never falls back to skipping this
    // scenario entirely.
    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();

    await context.setOffline(true);
    try {
      await expect(page.getByText('Disconnected')).toBeVisible({ timeout: 20_000 });
      // No blank/crashed panel — the pipeline canvas stays mounted.
      await expect(page.locator('.react-flow')).toBeVisible();
    } finally {
      await context.setOffline(false);
    }
  });
});
