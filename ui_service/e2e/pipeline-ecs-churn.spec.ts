/**
 * Pipeline ECS churn E2E specs (09-07, VAL-W0-CHURN-E2E).
 *
 * Plan 07 re-plumbed the pipeline canvas onto the ECS world using the
 * buffered React Flow pattern (see canvasGraph.ts / page.tsx / ecs/sync.ts).
 * Spike 001 confirmed that deriving React Flow's `nodes` prop fresh from
 * `world.entities.map()` on every ECS `touch()` does not degrade rendering —
 * it BREAKS it outright (blank canvas). These specs exercise the REAL
 * dashboard SSE endpoint (`GET /stream/pipeline-state`, 2s interval,
 * dashboard_service/pipeline_stream.py) against the running docker-compose
 * stack, following `pipeline-sse.spec.ts`'s structural conventions:
 * `ALLOW_RESTART` gating for disruptive scenarios, always-restore `finally`
 * blocks, and asserting BOTH the toolbar text and the canvas DOM element.
 *
 * Per RESEARCH.md Pitfall 4, Playwright's request-interception API does not
 * reliably deliver events to `EventSource` connections — this suite never
 * mocks or intercepts the SSE endpoint (no request-routing helpers of any
 * kind appear below).
 */

import { test, expect, type Page } from '@playwright/test';
import { execSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { DASHBOARD_COMPOSE_SERVICE } from './util';

const ALLOW_RESTART = Boolean(process.env.E2E_ALLOW_RESTART);

// SSE stream ticks every 2s (dashboard_service/pipeline_stream.py) — allow a
// little slack per poll so a slow tick doesn't flake the assertion.
const SSE_TICK_MS = 2000;
const POLL_MS = 2500;

function dockerCompose(args: string): void {
  execSync(`docker compose ${args}`, { timeout: 60_000, stdio: 'pipe' });
}

// Repo root, resolved relative to this file (via __dirname) rather than
// process.cwd() so the probe module lands in the SAME modules/ directory
// that's bind-mounted into the dashboard container regardless of where
// `playwright test` is invoked from.
//
// E2E_MODULES_ROOT override: when this suite runs from a git worktree (a
// separate working directory from the docker-compose checkout), the
// worktree's own `modules/` directory is NOT the one bind-mounted into the
// dashboard container — the compose-file checkout's is. Set
// E2E_MODULES_ROOT to that checkout's path in that scenario; defaults to
// this file's own repo root for the single-checkout (CI/production) case.
const REPO_ROOT = process.env.E2E_MODULES_ROOT ?? path.resolve(__dirname, '..', '..');
const PROBE_DIR = path.join(REPO_ROOT, 'modules', 'e2e_probe');
const PROBE_MANIFEST = path.join(PROBE_DIR, 'probe', 'manifest.json');

function writeProbeManifest(): void {
  fs.mkdirSync(path.dirname(PROBE_MANIFEST), { recursive: true });
  const manifest = {
    name: 'probe',
    version: '1.0.0',
    category: 'e2e_probe',
    platform: 'probe',
    display_name: 'E2E Probe',
    description: 'Throwaway module for pipeline-ecs-churn.spec.ts stale-selection test',
    icon: '🧪',
    entry_point: 'adapter.py',
    class_name: 'ProbeAdapter',
    test_file: 'test_adapter.py',
    requires_api_key: false,
    api_key_instructions: '',
    python_dependencies: [],
    auth_type: 'none',
    auth_url: null,
    status: 'pending',
    health_status: 'healthy',
    created_by: 'e2e',
    build_provider: 'manual',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    validation_results: {
      syntax_check: 'pass',
      unit_tests: 'pass',
      integration_test: 'skip',
      test_coverage: 1.0,
      error_details: null,
      validated_at: null,
    },
    failure_count: 0,
    success_count: 0,
    last_used: null,
  };
  fs.writeFileSync(PROBE_MANIFEST, JSON.stringify(manifest, null, 2));
}

function removeProbeModule(): void {
  fs.rmSync(PROBE_DIR, { recursive: true, force: true });
}

/** Waits for `predicate` to become true, polling every `POLL_MS` up to `ticks` SSE cycles. */
async function waitForTicks(predicate: () => Promise<boolean>, ticks: number): Promise<boolean> {
  const deadline = Date.now() + ticks * SSE_TICK_MS + POLL_MS;
  while (Date.now() < deadline) {
    if (await predicate()) return true;
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
  return false;
}

function collectPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

test.describe('Pipeline ECS churn (09-07, VAL-W0-CHURN-E2E)', () => {
  test('canvas survives sustained SSE churn without going blank', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    await expect(page.locator('.react-flow')).toBeVisible();

    let lastCount = -1;
    // Re-assert inside a loop across at least 5 real SSE ticks (~12s) rather
    // than one sleep + one assertion — a blank canvas and a thrashing canvas
    // are different failures and both must be caught here.
    for (let i = 0; i < 5; i++) {
      await expect(page.locator('.react-flow')).toBeVisible();
      const count = await page.locator('.react-flow__node').count();
      expect(count).toBeGreaterThan(0);
      if (lastCount !== -1) {
        expect(count).toBe(lastCount);
      }
      lastCount = count;
      await page.waitForTimeout(SSE_TICK_MS + 400);
    }

    await expect(page.locator('.react-flow')).toBeVisible();
    await expect(page.getByText('Live')).toBeVisible();
    expect(pageErrors).toEqual([]);
  });

  test('dragged node keeps its position across the next SSE tick', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    await expect(page.locator('.react-flow')).toBeVisible();

    const target = page.locator('.react-flow__node').first();
    await expect(target).toBeVisible();
    const nodeId = await target.getAttribute('data-id');
    expect(nodeId).toBeTruthy();

    const startBox = await target.boundingBox();
    expect(startBox).not.toBeNull();
    const startX = startBox!.x + startBox!.width / 2;
    const startY = startBox!.y + startBox!.height / 2;
    const offsetX = 80;
    const offsetY = 40;

    // Real drag gesture: down, multiple intermediate moves (React Flow needs
    // more than one move event to register a drag), then up.
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + offsetX / 2, startY + offsetY / 2, { steps: 5 });
    await expect(page.locator('.react-flow')).toBeVisible();
    await page.mouse.move(startX + offsetX, startY + offsetY, { steps: 5 });
    await expect(page.locator('.react-flow')).toBeVisible();
    await page.mouse.up();

    const afterDragNode = page.locator(`[data-id="${nodeId}"]`);
    const afterDragBox = await afterDragNode.boundingBox();
    expect(afterDragBox).not.toBeNull();
    expect(Math.abs(afterDragBox!.x - (startBox!.x + offsetX))).toBeLessThanOrEqual(10);
    expect(Math.abs(afterDragBox!.y - (startBox!.y + offsetY))).toBeLessThanOrEqual(10);

    // Wait at least two SSE ticks, then re-read the same node by data-id
    // (never `.first()` — topology order can shift across a snapshot).
    await page.waitForTimeout(2 * SSE_TICK_MS + 800);
    const settledBox = await page.locator(`[data-id="${nodeId}"]`).boundingBox();
    expect(settledBox).not.toBeNull();
    expect(Math.abs(settledBox!.x - afterDragBox!.x)).toBeLessThanOrEqual(10);
    expect(Math.abs(settledBox!.y - afterDragBox!.y)).toBeLessThanOrEqual(10);

    expect(pageErrors).toEqual([]);
  });

  test('hovering a node leaves the canvas stable under churn', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    await expect(page.locator('.react-flow')).toBeVisible();

    const target = page.locator('.react-flow__node').first();
    const nodeId = await target.getAttribute('data-id');
    expect(nodeId).toBeTruthy();
    const nodeLocator = page.locator(`[data-id="${nodeId}"]`);

    const startBox = await nodeLocator.boundingBox();
    const startCount = await page.locator('.react-flow__node').count();

    // 09-UI-SPEC.md's Interaction Contracts LOCK hover as visually unchanged
    // this phase — this asserts stability under hover, not a new hover
    // treatment; do not invent a hover visual to assert against here.
    await nodeLocator.hover();

    // Hold the hover across two SSE ticks by re-asserting in a loop.
    for (let i = 0; i < 2; i++) {
      await page.waitForTimeout(SSE_TICK_MS + 400);
      await expect(nodeLocator).toBeVisible();
      const box = await nodeLocator.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeCloseTo(startBox!.x, 0);
      expect(box!.y).toBeCloseTo(startBox!.y, 0);
      const count = await page.locator('.react-flow__node').count();
      expect(count).toBe(startCount);
    }

    expect(pageErrors).toEqual([]);
  });

  // Drives the e2e_probe module through its full lifecycle: create the
  // manifest on the host, wait for it to appear via the dashboard's manifest
  // scan, delete it, and always clean it up in a `finally` block.
  test('selection clears in the DOM when the selected module disappears from a snapshot', async ({ page }) => {
    const pageErrors = collectPageErrors(page);
    removeProbeModule(); // pre-clean any stray e2e_probe from a prior failed run

    try {
      writeProbeManifest(); // create the e2e_probe manifest

      await page.goto('/pipeline');
      await expect(page.getByText('Live')).toBeVisible();

      const probeNode = page.locator('[data-id="module-e2e_probe/probe"]');
      const appeared = await waitForTicks(async () => (await probeNode.count()) > 0, 3);
      expect(appeared).toBe(true);
      await expect(probeNode).toBeVisible();

      await probeNode.click();
      // Panel-scoped assertion — the node's label ("probe", from the
      // manifest's `name` field, which is what the panel header renders —
      // NOT `display_name`, which this app never surfaces) inside the
      // detail panel's own container, not merely any panel-ish element.
      const detailPanel = page.locator('.fixed.right-0.top-0.bottom-0');
      // header-scoped exact match: `probe` alone (not the `e2e_probe`
      // category badge, which also contains the substring).
      const panelLabel = detailPanel.locator('span.font-semibold', { hasText: 'probe' });
      await expect(panelLabel).toBeVisible();

      // Delete the module from the host filesystem — the dashboard's
      // manifest scan re-reads MODULES_DIR every 2s, no restart, no auth.
      removeProbeModule();

      const disappeared = await waitForTicks(async () => (await probeNode.count()) === 0, 3);
      expect(disappeared).toBe(true);

      // clearSelectionIfMissing firing in the real page: the detail panel
      // showing the probe's label must also be gone (not just the node).
      const panelGone = await waitForTicks(async () => (await panelLabel.count()) === 0, 3);
      expect(panelGone).toBe(true);

      // The clear is SILENT per UI-SPEC — no visible error text anywhere on
      // the page (a pre-existing, always-mounted empty toast region with
      // role="alert" is unrelated app chrome, not asserted against here).
      await expect(page.getByText(/error/i)).toHaveCount(0);

      expect(pageErrors).toEqual([]);
    } finally {
      // Always remove the probe module — a failed assertion must not leave
      // a stray module in the developer's stack.
      removeProbeModule();
    }
  });

  test.describe(() => {
    test.skip(!ALLOW_RESTART, 'set E2E_ALLOW_RESTART=1 to run the disruptive restart test');

    test('canvas recovers from a dashboard restart without a blank canvas', async ({ page }) => {
      await page.goto('/pipeline');
      await expect(page.getByText('Live')).toBeVisible();
      await expect(page.locator('.react-flow')).toBeVisible();

      try {
        dockerCompose(`restart ${DASHBOARD_COMPOSE_SERVICE}`);
        await expect(page.getByText('Disconnected')).toBeVisible({ timeout: 20_000 });
        await expect(page.locator('.react-flow')).toBeVisible();
        await expect(page.getByText('Live')).toBeVisible({ timeout: 40_000 });
        await expect(page.locator('.react-flow')).toBeVisible();
      } finally {
        try {
          dockerCompose(`up -d ${DASHBOARD_COMPOSE_SERVICE}`);
        } catch {
          // best-effort restore; a failure here does not mask the real
          // test failure being reported above it
        }
      }
    });
  });
});
