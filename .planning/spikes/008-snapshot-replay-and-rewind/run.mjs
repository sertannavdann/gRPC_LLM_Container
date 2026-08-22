// Spike 008 — rewind after rejection/undo, deterministic replay, redo, ECS-only field
// survival, ring memory cost.

import { writeFileSync, mkdirSync } from "node:fs";
import { makeFixture, makeStressFixture } from "./fixture.mjs";
import { canonicalize } from "./verbalize.mjs";
import { createMediatedWorld } from "./mediation.mjs";
import { createSnapshotRing, restoreSnapshot, createEventLog, replayEvents } from "./history.mjs";

const log = (...a) => console.log(...a);
const results = [];
function check(name, cond, detail = "") {
  results.push({ name, pass: !!cond, detail });
  log(`${cond ? "✓" : "✗"} ${name}${detail ? ` — ${detail}` : ""}`);
}
const snap = (w) => JSON.stringify(canonicalize(w.views()));

// ---------- T1: rewind after an applied-then-regretted proposal ----------
{
  const w = createMediatedWorld();
  w.syncFromPipeline(makeFixture());
  const ring = createSnapshotRing(8);

  // ECS-only/UI-only fields (the 002 gap): tag two entities.
  w.byId.get("svc-llm").hovered = true;
  w.byId.get("mod-mail-gmail").dragCount = 7;

  ring.push("pre-proposal", w.views());
  const before = snap(w);

  const r = w.propose([
    { op: "set_status", id: "svc-llm", value: "stopped" },
    { op: "remove_module", id: "mod-mail-gmail" },
  ]);
  w.approve(r.proposalId);
  check("T1a proposal applied (world drifted)", snap(w) !== before);

  restoreSnapshot(w, ring.get("pre-proposal").json);
  check("T1b rewind restores exact pre-proposal state", snap(w) === before);
  check("T1c no duplicate entities after same-world rewind", w.views().length === 26, `${w.views().length} entities`);
  check("T1d ECS-only fields survive rewind (002 gap closed)",
    w.byId.get("svc-llm").hovered === true && w.byId.get("mod-mail-gmail").dragCount === 7);
  check("T1e restore marks all entities dirty for downstream consumers", w.dirty.size === 26);
}

// ---------- T2: deterministic session replay from baseline + event log ----------
{
  const fixture = makeFixture();
  const w = createMediatedWorld();
  const eventLog = createEventLog();

  const doSync = (recs) => { eventLog.record("sync", recs); w.syncFromPipeline(recs); };
  const doApprovedOps = (ops) => {
    const r = w.propose(ops);
    const a = w.approve(r.proposalId);
    if (a.ok) eventLog.record("approve", ops);
    return a;
  };

  doSync(fixture);
  doApprovedOps([{ op: "set_status", id: "mod-fitness-strava", value: "stopped" }]);
  doSync(fixture.map((rec) => rec.id === "svc-chroma" ? { ...rec, status: "running" } : rec).filter((rec) => rec.id !== "mod-test-hello"));
  doApprovedOps([{ op: "add_module", rec: { id: "mod-notes-obsidian", label: "Obsidian Notes Adapter", kind: "module", status: "building", lifecycle: "installed", cpu: 0, mem: 0, x: 120, y: 860, credentials: [] } }]);
  doApprovedOps([{ op: "move", id: "mod-notes-obsidian", x: 300, y: 900 }]);

  const live = snap(w);
  const w2 = createMediatedWorld();
  replayEvents(w2, eventLog.slice());
  check("T2 replay from empty world + event log reproduces live state", snap(w2) === live, `${eventLog.length()} events`);
}

// ---------- T3: undo depth + redo via snapshot ring & log replay ----------
{
  const fixture = makeFixture();
  const w = createMediatedWorld();
  const ring = createSnapshotRing(8);
  const eventLog = createEventLog();
  const marks = []; // eventLog length at each snapshot

  const doApprovedOps = (ops) => {
    ring.push(`v${marks.length}`, w.views());
    marks.push(eventLog.length());
    const r = w.propose(ops);
    w.approve(r.proposalId);
    eventLog.record("approve", ops);
  };

  w.syncFromPipeline(fixture);
  eventLog.record("sync", fixture);
  doApprovedOps([{ op: "set_status", id: "svc-sandbox", value: "running" }]);   // v0 snap, then op A
  doApprovedOps([{ op: "move", id: "svc-sandbox", x: 999, y: 999 }]);           // v1 snap, then op B
  doApprovedOps([{ op: "set_credentials", id: "mod-tasks-todoist", list: ["TODOIST_API_KEY", "TODOIST_WEBHOOK"] }]); // v2, op C
  const head = snap(w);

  // Undo 2 steps → state as of v1 (after op A, before op B).
  restoreSnapshot(w, ring.get("v1").json);
  const sandbox = w.byId.get("svc-sandbox");
  check("T3a undo-2 lands on post-A/pre-B state", sandbox.status === "running" && sandbox.x !== 999);

  // Redo: replay logged events from mark v1 forward.
  replayEvents(w, eventLog.slice(marks[1]));
  check("T3b redo via log replay returns to head state", snap(w) === head);
}

// ---------- T4: ring memory cost ----------
{
  for (const N of [26, 400]) {
    const w = createMediatedWorld();
    w.syncFromPipeline(N === 26 ? makeFixture() : makeStressFixture(N));
    const ring = createSnapshotRing(20);
    for (let i = 0; i < 20; i++) ring.push(`v${i}`, w.views());
    log(`[mem] ring of 20 snapshots @ N=${N}: ${(ring.totalBytes() / 1024).toFixed(1)} KB (${(ring.totalBytes() / 20 / 1024).toFixed(1)} KB each)`);
  }
  check("T4 ring memory cost measured", true);
}

const passed = results.filter((r) => r.pass).length;
log(`\n${passed}/${results.length} checks passed`);
mkdirSync(new URL("./evidence/", import.meta.url), { recursive: true });
writeFileSync(new URL("./evidence/report.json", import.meta.url), JSON.stringify({ spike: "008", results }, null, 2));
if (passed !== results.length) process.exit(1);
