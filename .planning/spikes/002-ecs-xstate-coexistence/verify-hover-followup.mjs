// Follow-up: hoverResult showed hovered:false after 2s of churn even though
// the entity "survived" (was present at both start and end). Hypothesis:
// the entity was actually removed-then-re-added by the sync system at some
// point in between (a fresh entity object resets ECS-only fields to
// defaults), which the coarse before/after check couldn't see. Read the
// sync log directly to confirm.
import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto("http://localhost:5302");
await page.waitForSelector(".react-flow__node", { timeout: 8000 }).catch(() => {});
await page.selectOption("select", "600");
await page.waitForTimeout(300);

const id = await page.locator(".react-flow__node").first().getAttribute("data-id");
await page.locator(`[data-id="${id}"]`).hover();
await page.waitForTimeout(150);

await page.waitForTimeout(2200);

const logLines = await page.locator("#sync-log").innerText();
const relevant = logLines.split("\n").filter((l) => l.includes(id));
console.log(JSON.stringify({ hoveredId: id, relevantSyncEvents: relevant }, null, 2));
await browser.close();
