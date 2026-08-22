// Spike 005a — bitECS world-snapshot-as-context test rig.
// Measures: (1) binary snapshot round-trip fidelity, (2) determinism under churn
// (binary + text), (3) snapshot cost at realistic + stress scale, (4) c_state token
// counts per format, (5) glue LOC.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { encode } from "gpt-tokenizer"; // default o200k_base
import { makeFixture, makeStressFixture, CHURN_REMOVE_IDS, CHURN_READD_ORDER } from "./fixture.mjs";
import { FORMATS, canonicalize } from "./verbalize.mjs";
import { createPipelineWorld } from "./world.mjs";

const report = { spike: "005a-bitecs", results: {} };
const log = (...a) => console.log(...a);

function eq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

// ---------- 1. Round-trip fidelity (binary snapshot) ----------
{
  const fixture = makeFixture();
  const w = createPipelineWorld();
  fixture.forEach(w.add);
  const before = canonicalize(w.views());
  const buf = w.serialize();

  // Restore into a FRESH world (the real restore scenario: rewind/replay).
  const w2 = createPipelineWorld();
  w2.deserialize(buf);
  const after = canonicalize(w2.views());

  const ok = eq(before, after);
  report.results.roundTrip = { ok, entities: before.length, bufferBytes: buf.byteLength };
  log(`[round-trip] fresh-world restore: ${ok ? "OK" : "MISMATCH"} (${before.length} entities, ${buf.byteLength} bytes)`);
  if (!ok) {
    for (let i = 0; i < before.length; i++) {
      if (!eq(before[i], after[i])) { log("  first mismatch:", JSON.stringify(before[i]), "vs", JSON.stringify(after[i])); break; }
    }
  }
}

// ---------- 2. Determinism under churn ----------
{
  const fixture = makeFixture();
  const w = createPipelineWorld();
  fixture.forEach(w.add);

  const textBefore = FORMATS["compact-dsl"](w.views());
  const binBefore = new Uint8Array(w.serialize()).slice();

  // Churn: remove 3, re-add same logical entities in different order + revert a mutation.
  const recs = new Map(fixture.map((r) => [r.id, r]));
  CHURN_REMOVE_IDS.forEach((id) => w.remove(id));
  CHURN_READD_ORDER.forEach((id) => w.add(recs.get(id)));
  const eidDegrade = w.byId.get("svc-chroma");
  const prev = w.C.Status.value[eidDegrade];
  w.C.Status.value[eidDegrade] = 1; // running
  w.C.Status.value[eidDegrade] = prev; // revert

  const textAfter = FORMATS["compact-dsl"](w.views());
  const binAfter = new Uint8Array(w.serialize()).slice();

  const textStable = textBefore === textAfter;
  const binStable = binBefore.length === binAfter.length && binBefore.every((b, i) => b === binAfter[i]);
  report.results.determinism = { textStableAfterChurn: textStable, binaryStableAfterChurn: binStable };
  log(`[determinism] c_state text stable after churn: ${textStable ? "OK" : "UNSTABLE"}`);
  log(`[determinism] binary snapshot byte-stable after churn: ${binStable ? "OK (surprising)" : "UNSTABLE (expected — eid recycling)"}`);

  // Restore-into-fresh-world after churn should still verbalize identically (idMap remaps).
  const w3 = createPipelineWorld();
  w3.deserialize(w.serialize());
  const textRestored = FORMATS["compact-dsl"](w3.views());
  const restoredStable = textRestored === textAfter;
  report.results.determinism.textStableAfterRestore = restoredStable;
  log(`[determinism] c_state text stable after binary restore: ${restoredStable ? "OK" : "UNSTABLE"}`);
}

// ---------- 3. Snapshot cost ----------
function bench(label, fn, iters) {
  fn(); fn(); // warmup
  const t0 = performance.now();
  for (let i = 0; i < iters; i++) fn();
  const ms = (performance.now() - t0) / iters;
  log(`[bench] ${label}: ${ms.toFixed(4)} ms/op (${iters} iters)`);
  return ms;
}
{
  const w = createPipelineWorld();
  makeFixture().forEach(w.add);
  const msRealistic = bench("binary snapshot, 26 entities", () => w.serialize(), 2000);
  const msText = bench("views()+compact-dsl, 26 entities", () => FORMATS["compact-dsl"](w.views()), 2000);

  const ws = createPipelineWorld();
  makeStressFixture(5000).forEach(ws.add);
  const msStress = bench("binary snapshot, 5000 entities", () => ws.serialize(), 100);
  const msTextStress = bench("views()+compact-dsl, 5000 entities", () => FORMATS["compact-dsl"](ws.views()), 100);
  report.results.bench = { msRealistic, msText, msStress, msTextStress };
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

  // Also: raw binary snapshot is NOT LLM-legible; record size for the wire/replay story only.
  report.results.binarySnapshotBytes = w.serialize().byteLength;
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
