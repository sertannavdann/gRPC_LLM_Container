// Spike 006 — delta-context streaming, main rig (miniplex world, hand-rolled dirty set).
//
// Simulates the taxonomy's Iterative pattern (AutoDroid-style): a 40-tick SSE churn
// session with an "LLM invocation" every 5 ticks. Each invocation's c_state is either
// a full snapshot or a delta (changed/added entities + removed ids since last invocation).
//
// Correctness proof: an "LLM mental model" mirror (plain map, fed ONLY by the delta
// texts' underlying records) must equal the true world state at every invocation.
//
// The dirty tracker is the choke-point pattern: all world mutations flow through
// mutate()/add()/remove() helpers that record logical ids. This is the same discipline
// the 002 sync-system contract already imposes, so it costs nothing new architecturally.

import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { encode } from "gpt-tokenizer";
import { World } from "miniplex";
import { makeFixture } from "./fixture.mjs";
import { FORMATS, canonicalize, toCompactDsl } from "./verbalize.mjs";
import { makeChurnScript } from "./churn.mjs";

const log = (...a) => console.log(...a);
const report = { spike: "006-delta-context-streaming", results: {} };

// ---------- world + dirty tracking (the ENTIRE tracker is ~20 lines) ----------
const world = new World();
const byId = new Map();
const dirty = new Set();     // logical ids changed/added since last invocation
const removedIds = new Set(); // logical ids removed since last invocation

function add(rec) {
  const e = world.add({ ...rec, credentials: [...rec.credentials] });
  byId.set(rec.id, e);
  dirty.add(rec.id);
  removedIds.delete(rec.id);
  return e;
}
function remove(id) {
  const e = byId.get(id);
  if (!e) return;
  world.remove(e);
  byId.delete(id);
  dirty.delete(id);
  removedIds.add(id);
}
function mutate(id, patch) {
  const e = byId.get(id);
  if (!e) return;
  Object.assign(e, patch);
  dirty.add(id);
}
function views() {
  return [...world.entities].map((e) => ({ ...e, credentials: [...e.credentials] }));
}
function viewOf(id) {
  const e = byId.get(id);
  return e ? { ...e, credentials: [...e.credentials] } : null;
}

// ---------- delta context rendering ----------
function renderDeltaContext(version) {
  const changed = [...dirty].map(viewOf).filter(Boolean);
  const lines = [`# pipeline_state DELTA since v${version} — unchanged entities omitted`];
  if (removedIds.size) lines.push(`removed: ${[...removedIds].sort().join(",")}`);
  if (changed.length) lines.push(toCompactDsl(changed).split("\n").slice(1).join("\n")); // drop verbalizer header
  else if (!removedIds.size) lines.push("(no changes)");
  return { text: lines.join("\n"), changed, removed: [...removedIds] };
}

// ---------- the session ----------
const fixture = makeFixture();
fixture.forEach(add);
const script = makeChurnScript(fixture, 40, 1337);

// LLM mental-model mirror: fed only by full-snapshot text equivalents or delta records.
const mirror = new Map(); // id -> view record
function applyFullToMirror(vs) { mirror.clear(); for (const v of vs) mirror.set(v.id, v); }
function applyDeltaToMirror(delta) {
  for (const id of delta.removed) mirror.delete(id);
  for (const v of delta.changed) mirror.set(v.id, v);
}
function mirrorEquals(vs) {
  const a = JSON.stringify(canonicalize(vs));
  const b = JSON.stringify(canonicalize([...mirror.values()]));
  return a === b;
}

const INVOKE_EVERY = 5;
let version = 0;
let fullTokensTotal = 0;
let deltaTokensTotal = 0;
const perInvocation = [];
let allCorrect = true;

// Invocation 0: both strategies start with a full snapshot (the LLM needs a baseline).
{
  const fullText = FORMATS["compact-dsl"](views());
  const t = encode(fullText).length;
  fullTokensTotal += t;
  deltaTokensTotal += t;
  applyFullToMirror(views());
  dirty.clear(); removedIds.clear();
  perInvocation.push({ invocation: 0, full: t, delta: t, changedCount: "baseline" });
  version = 1;
}

for (let tick = 0; tick < script.length; tick++) {
  for (const op of script[tick]) {
    if (op.op === "metrics") mutate(op.id, { cpu: op.cpu, mem: op.mem });
    else if (op.op === "status") mutate(op.id, { status: op.value });
    else if (op.op === "remove") remove(op.id);
    else if (op.op === "add") add(op.rec);
  }
  if ((tick + 1) % INVOKE_EVERY === 0) {
    const fullText = FORMATS["compact-dsl"](views());
    const fullT = encode(fullText).length;

    const delta = renderDeltaContext(version);
    const deltaT = encode(delta.text).length;

    applyDeltaToMirror(delta);
    const correct = mirrorEquals(views());
    if (!correct) allCorrect = false;

    fullTokensTotal += fullT;
    deltaTokensTotal += deltaT;
    perInvocation.push({
      invocation: version, full: fullT, delta: deltaT,
      changedCount: delta.changed.length, removedCount: delta.removed.length,
      mirrorCorrect: correct,
    });
    version++;
    dirty.clear(); removedIds.clear();
  }
}

log("[session] 40 ticks, invocation every 5 ticks, 26-entity world");
log("inv | full-snap tokens | delta tokens | changed | removed | mirror-ok");
for (const r of perInvocation) {
  log(
    `${String(r.invocation).padStart(3)} | ${String(r.full).padStart(16)} | ${String(r.delta).padStart(12)} | ` +
    `${String(r.changedCount).padStart(7)} | ${String(r.removedCount ?? "-").padStart(7)} | ${r.mirrorCorrect ?? "-"}`
  );
}
const savings = 1 - deltaTokensTotal / fullTokensTotal;
log(`\n[tokens] full-snapshot strategy total: ${fullTokensTotal}`);
log(`[tokens] delta strategy total:         ${deltaTokensTotal}  (${(savings * 100).toFixed(1)}% saved)`);
log(`[correctness] mirror reconstruction from deltas: ${allCorrect ? "OK at every invocation" : "FAILED"}`);

// Dirty-tracker LOC (the add/remove/mutate choke points).
const self = readFileSync(new URL("./run.mjs", import.meta.url), "utf8").split("\n");
const trackerLoc = self
  .slice(self.findIndex((l) => l.includes("world + dirty tracking")), self.findIndex((l) => l.includes("delta context rendering")))
  .filter((l) => l.trim() && !l.trim().startsWith("//")).length;
log(`[loc] world+dirty-tracker section: ${trackerLoc} non-comment lines`);

report.results = { perInvocation, fullTokensTotal, deltaTokensTotal, savingsPct: savings * 100, allCorrect, trackerLoc };
mkdirSync(new URL("./evidence/", import.meta.url), { recursive: true });
writeFileSync(new URL("./evidence/report.json", import.meta.url), JSON.stringify(report, null, 2));
log("\nreport → evidence/report.json");
