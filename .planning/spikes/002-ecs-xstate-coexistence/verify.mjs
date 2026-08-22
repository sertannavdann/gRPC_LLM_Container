// Automated verification for Spike 002 — ECS + XState coexistence.
// Tests three things a real integration would need to get right:
//  1. Hover (ECS-only component) survives repeated XState-driven SSE syncs.
//  2. Drag position/count stays correct while other entities churn.
//  3. THE coexistence conflict: what happens to XState's selectedNodeId
//     when the ECS entity it points at is removed by the sync system —
//     compared with guardStaleSelection ON vs OFF.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const APP_URL = "http://localhost:5302";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "evidence") + "/";
mkdirSync(OUT, { recursive: true });

async function setStressInterval(page) {
  await page.selectOption("select", "600");
  await page.waitForTimeout(300);
}

async function firstNodeId(page) {
  const el = await page.locator(".react-flow__node").first();
  return el.getAttribute("data-id");
}

async function selectNode(page, id) {
  await page.locator(`[data-id="${id}"]`).click();
  await page.waitForTimeout(150);
}

async function hoverNode(page, id) {
  await page.locator(`[data-id="${id}"]`).hover();
  await page.waitForTimeout(150);
}

async function testHoverSurvivesSync(page) {
  const id = await firstNodeId(page);
  await hoverNode(page, id);
  const before = await page.locator(`[data-id="${id}"]`).textContent();
  await page.waitForTimeout(2000); // ~3 churn ticks at 600ms
  const stillThere = (await page.locator(`[data-id="${id}"]`).count()) > 0;
  const after = stillThere ? await page.locator(`[data-id="${id}"]`).textContent() : null;
  return { id, before, after, survivedAsEntity: stillThere, hoveredAfter: after?.includes("hovered (ecs-only)") ?? null };
}

async function testDragWhileChurning(page) {
  const id = await firstNodeId(page);
  const handle = page.locator(`[data-id="${id}"]`);
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  for (let i = 1; i <= 15; i++) {
    await page.mouse.move(box.x + box.width / 2 + i * 8, box.y + box.height / 2 + i * 4);
    await page.waitForTimeout(60); // ~1.5s total, spans 2 churn ticks at 600ms
  }
  await page.mouse.up();
  await page.waitForTimeout(200);
  const stillThere = (await page.locator(`[data-id="${id}"]`).count()) > 0;
  const text = stillThere ? await page.locator(`[data-id="${id}"]`).textContent() : "GONE";
  return { id, text, survived: stillThere };
}

async function testStaleSelection(page, guardOn) {
  await page
    .locator("label", { hasText: "guard stale selection" })
    .locator("input")
    .evaluate((el, want) => {
      if (el.checked !== want) el.click();
    }, guardOn);
  await page.waitForTimeout(400);
  await setStressInterval(page);

  const id = await firstNodeId(page);
  await selectNode(page, id);
  let selectedIdText = await page.locator("#selected-id").innerText();

  let droppedAtTick = null;
  for (let tick = 1; tick <= 20; tick++) {
    await page.waitForTimeout(650);
    const exists = (await page.locator(`[data-id="${id}"]`).count()) > 0;
    if (!exists) {
      droppedAtTick = tick;
      break;
    }
  }

  await page.waitForTimeout(300);
  const selectedIdAfterDrop = await page.locator("#selected-id").innerText();

  return {
    guardOn,
    selectedNode: id,
    droppedAtTick,
    selectedIdBeforeDrop: selectedIdText,
    selectedIdAfterDrop,
    danglingReference: droppedAtTick !== null && selectedIdAfterDrop === id,
    correctlyCleared: droppedAtTick !== null && selectedIdAfterDrop === "none",
  };
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(APP_URL);
await page.waitForSelector(".react-flow__node", { timeout: 8000 }).catch(() => {});
await setStressInterval(page);

const hoverResult = await testHoverSurvivesSync(page);
await page.screenshot({ path: `${OUT}01-hover-survives.png` });

const dragResult = await testDragWhileChurning(page);
await page.screenshot({ path: `${OUT}02-drag-while-churn.png` });

// Reload for a clean world before each stale-selection trial.
await page.reload();
await page.waitForSelector(".react-flow__node", { timeout: 8000 }).catch(() => {});
const staleGuardOn = await testStaleSelection(page, true);
await page.screenshot({ path: `${OUT}03-guard-on.png` });

await page.reload();
await page.waitForSelector(".react-flow__node", { timeout: 8000 }).catch(() => {});
const staleGuardOff = await testStaleSelection(page, false);
await page.screenshot({ path: `${OUT}04-guard-off.png` });

await browser.close();

console.log(JSON.stringify({ hoverResult, dragResult, staleGuardOn, staleGuardOff }, null, 2));
