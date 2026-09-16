/**
 * Pipeline canvas-ops E2E specs (Phase 9 plan 09).
 *
 * Automated proof of the ROADMAP Done Criterion: "LLM proposal -> preview ->
 * approve/reject flow works end-to-end; rejection rewinds cleanly; approved
 * ops appear in next delta." Follows pipeline-ecs-churn.spec.ts's structural
 * conventions: header-comment style, `./util` imports, a `page.on('pageerror')`
 * collector asserted empty at the end of each test, and no SSE mocking (no
 * `page.route`/`context.route` anywhere in this file).
 *
 * Drives the flow through the Task-1 dev seam (`window.__nexusCanvas`), which
 * the build-time NEXT_PUBLIC_CANVAS_DEV_SEAM flag makes available on the
 * compose stack's production ui_service image (see ui_service/Dockerfile +
 * docker-compose.yaml).
 */

import { test, expect, type Page } from '@playwright/test';

declare global {
  interface Window {
    __nexusCanvas?: {
      submitCanvasOps: (ops: unknown[]) => { accepted: boolean; proposalId?: string; errors?: string[] };
      delta: () => { text: string };
      cState: () => string;
      entityLine: (id: string) => string | null;
    };
  }
}

function collectPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

async function firstModuleId(page: Page): Promise<string | null> {
  const locator = page.locator('[data-id^="module-"]').first();
  for (let i = 0; i < 3; i++) {
    if ((await locator.count()) > 0) {
      return locator.getAttribute('data-id');
    }
    await page.waitForTimeout(2500);
  }
  return null;
}

test.describe('Pipeline canvas ops (09-09)', () => {
  test('propose -> overlay -> approve applies the op and it shows up in the next delta', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    await expect(page.locator('.react-flow')).toBeVisible();

    const moduleId = await firstModuleId(page);
    test.skip(!moduleId, 'No module node present in this stack to exercise canvas ops against');
    const domId = moduleId as string;
    const entityId = domId; // data-id equals the ECS logical id (module-<category>/<platform>)

    const result = await page.evaluate(
      (id) => window.__nexusCanvas!.submitCanvasOps([{ op: 'set_status', id, value: 'disabled' }]),
      entityId,
    );
    expect(result.accepted).toBe(true);

    const nodeLocator = page.locator(`[data-id="${domId}"]`);
    await expect(nodeLocator.getByText('status → disabled')).toBeVisible();

    await nodeLocator.click();
    const detailPanel = page.locator('.fixed.right-0.top-0.bottom-0');
    await expect(detailPanel.getByText('Proposed Change')).toBeVisible();
    await expect(detailPanel.getByText(/disabled/)).toBeVisible();

    await detailPanel.getByRole('button', { name: 'Approve Change' }).click();
    await expect(detailPanel).toBeHidden();

    // Proves the "approved ops appear in the next delta" half of the
    // Done Criterion by reading the ECS delta immediately (same render
    // cycle, via the touch() bridge) — read BEFORE the next real SSE tick
    // (2s), since dashboard_service's SSE stream is authoritative for
    // module status and will overwrite this local mutation on its next
    // snapshot (mediation.ts's documented ownership policy). A module
    // node's on-canvas rendering of `status` depends on `resolveLifecycle`,
    // which prioritizes the module's `lifecycle` field over raw `status`
    // for non-legacy modules — so the ECS delta (not the rendered label) is
    // the correct, un-derived source of truth to assert against here.
    const delta = await page.evaluate(() => window.__nexusCanvas!.delta());
    expect(delta.text).toContain(entityId);
    expect(delta.text).toContain('disabled');
    expect(delta.text).toContain('unchanged entities omitted');

    expect(pageErrors).toEqual([]);
  });

  test('reject after approve rewinds the canvas and shows the rewind toast', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    await expect(page.locator('.react-flow')).toBeVisible();

    const moduleId = await firstModuleId(page);
    test.skip(!moduleId, 'No module node present in this stack to exercise canvas ops against');
    const domId = moduleId as string;
    const entityId = domId;

    // Scoped to the target entity's own line, not the whole live cState():
    // the real docker-compose stack's SSE stream ticks every 2s and mutates
    // unrelated services' `latency_ms` independently of this test, which
    // would otherwise make a whole-world byte-identity assertion flaky for
    // reasons that have nothing to do with the rewind under test.
    const baseline = await page.evaluate((id) => window.__nexusCanvas!.entityLine(id), entityId);

    const result = await page.evaluate(
      (id) => window.__nexusCanvas!.submitCanvasOps([{ op: 'set_status', id, value: 'error' }]),
      entityId,
    );
    expect(result.accepted).toBe(true);

    const nodeLocator = page.locator(`[data-id="${domId}"]`);
    // Wait for the violet proposal annotation to actually attach before
    // clicking — annotations recompute on the ECS touch() bridge, which the
    // dev-seam's propose() call does not itself trigger; the next SSE tick
    // (up to 2s) drives the re-render that surfaces the badge.
    await expect(nodeLocator.getByText(/status → error/)).toBeVisible();
    await nodeLocator.click();
    const detailPanel = page.locator('.fixed.right-0.top-0.bottom-0');
    await expect(detailPanel.getByText('Proposed Change')).toBeVisible();
    await detailPanel.getByRole('button', { name: 'Approve Change' }).click();
    await expect(detailPanel).toBeHidden();

    const afterApprove = await page.evaluate((id) => window.__nexusCanvas!.entityLine(id), entityId);
    expect(afterApprove).not.toBe(baseline);

    // Re-open the SAME node — page.tsx remembers the just-approved proposal
    // id per node id even though `proposalAnnotations()` no longer badges an
    // approved proposal (D9-08: only staged proposals are annotated), so the
    // panel re-opens directly into canvasOpApproval for that proposal.
    await nodeLocator.click();
    await expect(detailPanel.getByText('Proposed Change')).toBeVisible();

    // Single click — no confirmation step (UI-SPEC deliberate departure from
    // Phase 8's double-click Reject Module pattern).
    await detailPanel.getByRole('button', { name: 'Reject Change' }).click();

    const toast = page.getByText('Change rejected — canvas rewound to the previous state.');
    await expect(toast).toBeVisible();
    await expect(toast).toBeHidden({ timeout: 4000 });

    const afterReject = await page.evaluate((id) => window.__nexusCanvas!.entityLine(id), entityId);
    expect(afterReject).toBe(baseline);

    expect(pageErrors).toEqual([]);
  });

  test('rejecting a merely staged proposal shows no rewind toast', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto('/pipeline');
    await expect(page.getByText('Live')).toBeVisible();
    await expect(page.locator('.react-flow')).toBeVisible();

    const moduleId = await firstModuleId(page);
    test.skip(!moduleId, 'No module node present in this stack to exercise canvas ops against');
    const domId = moduleId as string;
    const entityId = domId;

    const result = await page.evaluate(
      (id) => window.__nexusCanvas!.submitCanvasOps([{ op: 'set_status', id, value: 'disabled' }]),
      entityId,
    );
    expect(result.accepted).toBe(true);

    const nodeLocator = page.locator(`[data-id="${domId}"]`);
    await expect(nodeLocator.getByText(/status → disabled/)).toBeVisible();
    await nodeLocator.click();
    const detailPanel = page.locator('.fixed.right-0.top-0.bottom-0');
    await expect(detailPanel.getByText('Proposed Change')).toBeVisible();
    await detailPanel.getByRole('button', { name: 'Reject Change' }).click();
    await expect(detailPanel).toBeHidden();

    const toast = page.getByText('Change rejected — canvas rewound to the previous state.');
    await expect(toast).toHaveCount(0);
    await expect(nodeLocator.getByText('status → disabled')).toHaveCount(0);

    expect(pageErrors).toEqual([]);
  });
});
