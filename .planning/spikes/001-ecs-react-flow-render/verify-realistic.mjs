// Follow-up check: does "naive" mode hold up under the REALISTIC 2s SSE
// cadence (matching dashboard_service/pipeline_stream.py's actual interval),
// with no drag at all — just idle observation?
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const APP_URL = "http://localhost:5301";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "evidence") + "/";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(APP_URL);
await page.waitForTimeout(500);
// default is naive mode + chaos already running at 400ms; switch to realistic 2000ms
await page.selectOption("select", "2000");
await page.screenshot({ path: `${OUT}naive-realistic-00-t0.png` });
await page.waitForTimeout(5000); // let ~2-3 realistic-cadence ticks happen
await page.screenshot({ path: `${OUT}naive-realistic-01-t5s.png` });
const nodeTexts = await page.evaluate(() =>
  Array.from(document.querySelectorAll(".react-flow__node")).map((n) => n.textContent)
);
console.log(JSON.stringify({ afterTicks: nodeTexts }, null, 2));
await browser.close();
