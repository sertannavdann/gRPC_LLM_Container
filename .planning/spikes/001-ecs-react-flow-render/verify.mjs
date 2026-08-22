// Automated verification for Spike 001 — ECS + React Flow render sync.
// Drives a real Chromium instance via Playwright, drags a node while the
// chaos system is actively mutating OTHER entities' status via touch(),
// and reads the on-page conflict counter + FPS + screenshots as evidence.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const APP_URL = "http://localhost:5301";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "evidence") + "/";
mkdirSync(OUT, { recursive: true });

async function dragNode(page, nodeId, dx, dy, steps = 20, stepDelayMs = 40) {
  const handle = await page.locator(`[data-id="${nodeId}"]`);
  const box = await handle.boundingBox();
  if (!box) throw new Error(`node ${nodeId} not found`);
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    const x = startX + (dx * i) / steps;
    const y = startY + (dy * i) / steps;
    await page.mouse.move(x, y);
    await page.waitForTimeout(stepDelayMs);
  }
  await page.mouse.up();

  const boxAfter = await handle.boundingBox();
  return { before: { x: startX, y: startY }, after: boxAfter };
}

async function readConflictCount(page) {
  return await page.locator("#conflict-count").innerText();
}

async function readUpdateCounts(page) {
  return await page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll(".react-flow__node"));
    return nodes.map((n) => n.textContent);
  });
}

async function runMode(browser, mode, label) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const logs = [];
  page.on("console", (msg) => logs.push(`[console] ${msg.type()}: ${msg.text()}`));
  page.on("pageerror", (err) => logs.push(`[pageerror] ${err.message}`));

  await page.goto(APP_URL);
  try {
    await page.waitForSelector(".react-flow__node", { state: "visible", timeout: 8000 });
  } catch (e) {
    await page.screenshot({ path: `${OUT}${label}-debug-timeout.png` });
    console.error("DEBUG: timeout waiting for node visibility, screenshot saved. Continuing anyway.");
  }

  if (mode === "buffered") {
    await page.getByText("buffered (RF-local + patch)").click();
    await page.waitForTimeout(300);
  }
  // stress chaos interval
  await page.selectOption("select", "400");
  await page.waitForTimeout(500);

  await page.screenshot({ path: `${OUT}${label}-00-before.png` });

  const before = await readConflictCount(page);

  // Drag the orchestrator node a good distance while chaos is actively
  // mutating the OTHER 7 entities every 400ms — this is the realistic
  // "user is dragging one node while live SSE status flows in" scenario.
  const dragResult = await dragNode(page, "orchestrator", 260, 180, 25, 40);

  await page.screenshot({ path: `${OUT}${label}-01-after-drag.png` });

  const after = await readConflictCount(page);
  const fpsText = await page.locator("#fps").innerText();

  await page.waitForTimeout(300);
  const nodeTexts = await readUpdateCounts(page);

  await page.close();

  return {
    mode,
    conflictsBefore: before,
    conflictsAfter: after,
    fps: fpsText,
    drag: dragResult,
    nodeTexts,
    logs: logs.slice(0, 30),
  };
}

const browser = await chromium.launch();
const results = [];
results.push(await runMode(browser, "naive", "naive"));
results.push(await runMode(browser, "buffered", "buffered"));
await browser.close();

console.log(JSON.stringify(results, null, 2));
