// Spike 005b — miniplex world-snapshot-as-context test rig. Mirrors 005a exactly.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { encode } from "gpt-tokenizer";
import { makeFixture, makeStressFixture, CHURN_REMOVE_IDS, CHURN_READD_ORDER } from "./fixture.mjs";
import { FORMATS, canonicalize } from "./verbalize.mjs";
import { createPipelineWorld } from "./world.mjs";

const report = { spike: "005b-miniplex", results: {} };
const log = (...a) => console.log(...a);
function eq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

// ---------- 1. Round-trip fidelity (JSON snapshot into fresh world) ----------
{
  const fixture = makeFixture();
  const w = createPipelineWorld();
  fixture.forEach(w.add);
  const before = canonicalize(w.views());
  const json = w.serialize();

  const w2 = createPipelineWorld();
  w2.deserialize(json);
  const after = canonicalize(w2.views());

  const ok = eq(before, after);
  report.results.roundTrip = { ok, entities: before.length, bufferBytes: Buffer.byteLength(json, "utf8") };
  log(`[round-trip] fresh-world restore: ${ok ? "OK" : "MISMATCH"} (${before.length} entities, ${Buffer.byteLength(json, "utf8")} bytes JSON)`);
}

// ---------- 2. Determinism under churn ----------
{
  const fixture = makeFixture();
  const w = createPipelineWorld();
  fixture.forEach(w.add);

  const textBefore = FORMATS["compact-dsl"](w.views());
  const snapBefore = w.serialize();

  const recs = new Map(fixture.map((r) => [r.id, r]));
  CHURN_REMOVE_IDS.forEach((id) => w.remove(id));
  CHURN_READD_ORDER.forEach((id) => w.add(recs.get(id)));
  const chroma = w.byId.get("svc-chroma");
  const prev = chroma.status;
  chroma.status = "running";
  chroma.status = prev;

  const textAfter = FORMATS["compact-dsl"](w.views());
  const snapAfter = w.serialize();

  const textStable = textBefore === textAfter;
  const snapStable = snapBefore === snapAfter;
  report.results.determinism = { textStableAfterChurn: textStable, snapshotStableAfterChurn: snapStable };
  log(`[determinism] c_state text stable after churn: ${textStable ? "OK" : "UNSTABLE"}`);
  log(`[determinism] JSON snapshot stable after churn: ${snapStable ? "OK" : "UNSTABLE"}`);

  const w3 = createPipelineWorld();
  w3.deserialize(w.serialize());
  const restoredStable = FORMATS["compact-dsl"](w3.views()) === textAfter;
  report.results.determinism.textStableAfterRestore = restoredStable;
  log(`[determinism] c_state text stable after snapshot restore: ${restoredStable ? "OK" : "UNSTABLE"}`);
}

// ---------- 3. Snapshot cost ----------
function bench(label, fn, iters) {
  fn(); fn();
  const t0 = performance.now();
  for (let i = 0; i < iters; i++) fn();
  const ms = (performance.now() - t0) / iters;
  log(`[bench] ${label}: ${ms.toFixed(4)} ms/op (${iters} iters)`);
  return ms;
}
{
  const w = createPipelineWorld();
  makeFixture().forEach(w.add);
  const msRealistic = bench("JSON snapshot, 26 entities", () => w.serialize(), 2000);
  const msClone = bench("structuredClone snapshot, 26 entities", () => w.snapshotClone(), 2000);
  const msText = bench("views()+compact-dsl, 26 entities", () => FORMATS["compact-dsl"](w.views()), 2000);

  const ws = createPipelineWorld();
  makeStressFixture(5000).forEach(ws.add);
  const msStress = bench("JSON snapshot, 5000 entities", () => ws.serialize(), 100);
  const msCloneStress = bench("structuredClone snapshot, 5000 entities", () => ws.snapshotClone(), 100);
  const msTextStress = bench("views()+compact-dsl, 5000 entities", () => FORMATS["compact-dsl"](ws.views()), 100);
  report.results.bench = { msRealistic, msClone, msText, msStress, msCloneStress, msTextStress };
}

// ---------- 4. c_state token counts per format ----------
{
  const w = createPipelineWorld();
  makeFixture().forEach(w.add);
  const tokens = {};
  for (const [name, fmt] of Object.entries(FORMATS)) {
    const text = fmt(w.views());
    tokens[name] = { tokens: encode(text).length, chars: text.length };
  }
  report.results.tokens = tokens;
  log("[tokens] c_state cost by format (26 entities):");
  for (const [name, t] of Object.entries(tokens)) log(`  ${name.padEnd(12)} ${String(t.tokens).padStart(5)} tokens  (${t.chars} chars)`);
}

// ---------- 5. Glue LOC ----------
{
  const loc = readFileSync(new URL("./world.mjs", import.meta.url), "utf8")
    .split("\n").filter((l) => l.trim() && !l.trim().startsWith("//")).length;
  report.results.glueLoc = loc;
  log(`[loc] world adapter glue: ${loc} non-comment lines`);
}

mkdirSync(new URL("./evidence/", import.meta.url), { recursive: true });
writeFileSync(new URL("./evidence/report.json", import.meta.url), JSON.stringify(report, null, 2));
log("\nreport → evidence/report.json");
