// Spike 007 — LLM writes world: staged proposals, approval gates, two-writer safety.

import { writeFileSync, mkdirSync } from "node:fs";
import { makeFixture } from "./fixture.mjs";
import { canonicalize } from "./verbalize.mjs";
import { createMediatedWorld } from "./mediation.mjs";

const log = (...a) => console.log(...a);
const results = [];
function check(name, cond, detail = "") {
  results.push({ name, pass: !!cond, detail });
  log(`${cond ? "✓" : "✗"} ${name}${detail ? ` — ${detail}` : ""}`);
}
const snap = (w) => JSON.stringify(canonicalize(w.views()));

// ---------- T1: valid proposal → staged (live world untouched) → approve → applied ----------
{
  const w = createMediatedWorld();
  w.syncFromPipeline(makeFixture());
  w.dirty.clear();

  const before = snap(w);
  const r = w.propose([
    { op: "set_status", id: "mod-fitness-strava", value: "stopped" },
    { op: "set_credentials", id: "mod-fitness-strava", list: ["STRAVA_ACCESS_TOKEN", "STRAVA_REFRESH_TOKEN"] },
  ]);
  check("T1a valid proposal accepted", r.accepted);
  check("T1b live world untouched while staged", snap(w) === before);

  const preview = w.previewViews(r.proposalId);
  const pv = preview.find((v) => v.id === "mod-fitness-strava");
  check("T1c preview shows staged values", pv.status === "stopped" && pv.credentials.length === 2);
  check("T1d preview did not mutate live world", snap(w) === before);

  const a = w.approve(r.proposalId);
  const live = w.views().find((v) => v.id === "mod-fitness-strava");
  check("T1e approve applies ops", a.ok && live.status === "stopped" && live.credentials.length === 2);
  check("T1f approved ops feed 006 dirty set", w.dirty.has("mod-fitness-strava"), "delta streaming integration");
}

// ---------- T2: schema/policy rejections with structured errors ----------
{
  const w = createMediatedWorld();
  w.syncFromPipeline(makeFixture());

  const bad = [
    [{ op: "explode_world" }, "unknown op"],
    [{ op: "set_status", id: "mod-mail-gmail", value: "on-fire" }, "bad enum"],
    [{ op: "set_status", id: "mod-ghost", value: "running" }, "unknown id"],
    [{ op: "move", id: "svc-llm", x: "left", y: 10 }, "wrong type"],
    [{ op: "remove_module", id: "svc-orchestrator" }, "ownership policy: remove_module on a service"],
    [{ op: "set_credentials", id: "svc-llm", list: ["X"] }, "ownership policy: credentials on a service"],
    [{ op: "add_module", rec: { id: "svc-fake", label: "x", status: "running", lifecycle: null, kind: "module", cpu: 0, mem: 0, x: 0, y: 0, credentials: [] } }, "add_module with non-mod id"],
  ];
  let allRejected = true;
  for (const [op, label] of bad) {
    const r = w.propose([op]);
    if (r.accepted) { allRejected = false; log(`  !! accepted: ${label}`); }
  }
  check("T2 all invalid/policy-violating ops rejected with errors", allRejected);
  const sample = w.propose([{ op: "set_status", id: "mod-ghost", value: "running" }]);
  check("T2b error messages are structured/actionable", sample.errors?.[0]?.includes("does not exist"), JSON.stringify(sample.errors));
}

// ---------- T3: reject discards cleanly ----------
{
  const w = createMediatedWorld();
  w.syncFromPipeline(makeFixture());
  const before = snap(w);
  const r = w.propose([{ op: "remove_module", id: "mod-test-hello" }]);
  w.reject(r.proposalId);
  check("T3 rejected proposal leaves no trace on world", snap(w) === before);
  check("T3b proposal state is rejected", w.proposals.get(r.proposalId).status === "rejected");
}

// ---------- T4: stale proposal — SSE removes target before approval ----------
{
  const w = createMediatedWorld();
  const fixture = makeFixture();
  w.syncFromPipeline(fixture);

  const r = w.propose([{ op: "set_status", id: "mod-music-spotify", value: "running" }]);
  check("T4a proposal staged while target exists", r.accepted);

  // Next SSE snapshot: spotify module uninstalled server-side.
  w.syncFromPipeline(fixture.filter((rec) => rec.id !== "mod-music-spotify"));
  const p = w.proposals.get(r.proposalId);
  check("T4b snapshot sync invalidates stale proposal in same transition", p.status === "invalidated", p.reason);

  const a = w.approve(r.proposalId);
  check("T4c approving an invalidated proposal is refused", !a.ok);
}

// ---------- T5: race at approval time (target vanishes between staging and approve, no sync ran) ----------
{
  const w = createMediatedWorld();
  const fixture = makeFixture();
  w.syncFromPipeline(fixture);
  const r = w.propose([{ op: "set_credentials", id: "mod-notes-notion", value: undefined, list: ["NOTION_API_KEY_V2"] }]);
  // Simulate a direct removal (e.g. another approved proposal removed it) without full sync:
  const a0 = w.approve(w.propose([{ op: "remove_module", id: "mod-notes-notion" }]).proposalId);
  const a = w.approve(r.proposalId);
  check("T5 approval-time re-validation catches vanished target", a0.ok && !a.ok, a.error);
}

// ---------- T6: LLM-added module round-trips through SSE ----------
{
  const w = createMediatedWorld();
  const fixture = makeFixture();
  w.syncFromPipeline(fixture);
  const rec = { id: "mod-notes-obsidian", label: "Obsidian Notes Adapter", kind: "module", status: "building", lifecycle: "installed", cpu: 0, mem: 0, x: 120, y: 860, credentials: [] };
  const r = w.propose([{ op: "add_module", rec }]);
  const a = w.approve(r.proposalId);
  check("T6a approved add_module creates entity", a.ok && w.byId.has("mod-notes-obsidian"));

  // Backend confirms it in the next snapshot → no duplicate, no flicker-removal.
  w.syncFromPipeline([...fixture, rec]);
  const count = w.views().filter((v) => v.id === "mod-notes-obsidian").length;
  check("T6b next SSE snapshot converges without duplicate", count === 1);

  // But if backend does NOT include it (build failed server-side), sync removes it:
  w.syncFromPipeline(fixture);
  check("T6c snapshot without the module removes it (XState/SSE stays existence authority)", !w.byId.has("mod-notes-obsidian"));
}

const passed = results.filter((r) => r.pass).length;
log(`\n${passed}/${results.length} checks passed`);
mkdirSync(new URL("./evidence/", import.meta.url), { recursive: true });
writeFileSync(new URL("./evidence/report.json", import.meta.url), JSON.stringify({ spike: "007", results }, null, 2));
if (passed !== results.length) process.exit(1);
