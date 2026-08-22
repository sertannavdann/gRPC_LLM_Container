// Automated verification for Spike 004 — ECS "systems" vs plain ad-hoc React
// for a cross-entity canvas behavior (hover a node -> highlight it + its
// graph neighbors, dim everything else). Runs the identical stress test
// against both implementations and compares render counts / correctness.
import { chromium } from "playwright";

const APP_URL = "http://localhost:5304";

async function runImpl(page, impl) {
  await page.goto(APP_URL);
  await page.waitForSelector(".react-flow__node", { timeout: 8000 }).catch(() => {});
  if (impl === "adhoc") {
    await page.locator("label", { hasText: "adhoc-react" }).locator("input").check();
    await page.waitForTimeout(300);
  }

  // Correctness check: hover "orchestrator" (connects to dashboard, sandbox),
  // confirm exactly those 3 nodes are highlighted, not module-0..3.
  await page.locator('[data-id="orchestrator"]').hover();
  await page.waitForTimeout(150);
  const highlightedAfterHover = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".react-flow__node")).map((n) => ({
      id: n.getAttribute("data-id"),
      dimmed: n.querySelector("div")?.style.opacity === "0.55",
    }))
  );

  await page.mouse.move(10, 10); // move off any node
  await page.waitForTimeout(150);

  // Stress test: 10x full sweep across all 7 nodes, then measure total
  // render count and elapsed time.
  await page.click("#stress-button");
  await page.waitForTimeout(10 * 7 * 5 + 500); // rounds * nodes * per-step delay + margin
  const renderSumText = await page.locator("#render-sum").innerText();
  const stressElapsedText = await page.locator("#stress-elapsed").innerText().catch(() => "n/a");

  return { impl, highlightedAfterHover, renderSumText, stressElapsedText };
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

const ecsResult = await runImpl(page, "ecs");
const adhocResult = await runImpl(page, "adhoc");

await browser.close();
console.log(JSON.stringify({ ecsResult, adhocResult }, null, 2));
