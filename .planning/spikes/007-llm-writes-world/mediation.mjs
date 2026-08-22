// Spike 007 — world + the single mediation layer for BOTH writers (SSE sync + LLM ops).
//
// Ownership policy (from 002 + taxonomy's Check dimension):
// - SSE sync (XState-owned snapshots) is the ONLY writer that may add/remove
//   service/stage entities and the only source of truth for module existence too —
//   EXCEPT that approved LLM proposals may add/remove *module* entities (the Phase 8
//   build-a-module flow), which then round-trips through the backend and comes back in
//   later SSE snapshots.
// - LLM ops arrive as STAGED PROPOSALS. Nothing touches the live world until approval.
// - Every proposal is re-validated against the live world at approval time AND on every
//   SSE snapshot (the 002 clearSelectionIfMissing pattern generalized to proposals).

import { World } from "miniplex";
import { STATUSES, LIFECYCLES } from "./fixture.mjs";

// ---------- op schema (hand-rolled validator; zod in the real build) ----------
const OPS = {
  set_status:      { fields: { id: "string", value: "status" }, kinds: ["service", "module", "stage"] },
  set_credentials: { fields: { id: "string", list: "string[]" }, kinds: ["module"] },
  move:            { fields: { id: "string", x: "number", y: "number" }, kinds: ["service", "module", "stage"] },
  add_module:      { fields: { rec: "module_rec" }, kinds: ["module"] },
  remove_module:   { fields: { id: "string" }, kinds: ["module"] },
};

export function validateOp(op, byId) {
  const spec = OPS[op?.op];
  if (!spec) return { ok: false, error: `unknown op "${op?.op}"` };
  for (const [field, type] of Object.entries(spec.fields)) {
    const v = op[field];
    if (type === "string" && typeof v !== "string") return { ok: false, error: `${op.op}.${field}: expected string` };
    if (type === "number" && typeof v !== "number") return { ok: false, error: `${op.op}.${field}: expected number` };
    if (type === "status" && !STATUSES.includes(v)) return { ok: false, error: `${op.op}.${field}: "${v}" not in ${STATUSES.join("|")}` };
    if (type === "string[]" && (!Array.isArray(v) || v.some((s) => typeof s !== "string")))
      return { ok: false, error: `${op.op}.${field}: expected string[]` };
    if (type === "module_rec") {
      if (typeof v?.id !== "string" || !v.id.startsWith("mod-")) return { ok: false, error: `add_module.rec.id must be a "mod-" id` };
      if (typeof v?.label !== "string") return { ok: false, error: `add_module.rec.label: expected string` };
      if (!STATUSES.includes(v?.status)) return { ok: false, error: `add_module.rec.status invalid` };
      if (v.lifecycle !== null && !LIFECYCLES.includes(v.lifecycle)) return { ok: false, error: `add_module.rec.lifecycle invalid` };
    }
  }
  // Referential + policy checks against the LIVE world:
  if ("id" in spec.fields) {
    const target = byId.get(op.id);
    if (op.op === "add_module") { /* no target */ }
    else if (!target) return { ok: false, error: `${op.op}: entity "${op.id}" does not exist (stale proposal?)` };
    else if (!spec.kinds.includes(target.kind))
      return { ok: false, error: `${op.op}: not permitted on kind "${target.kind}" (ownership policy)` };
  }
  if (op.op === "add_module" && byId.has(op.rec.id)) return { ok: false, error: `add_module: "${op.rec.id}" already exists` };
  return { ok: true };
}

// ---------- world + two writers ----------
export function createMediatedWorld() {
  const world = new World();
  const byId = new Map();
  const dirty = new Set();
  const removedIds = new Set();
  const proposals = new Map(); // proposalId -> {ops, status: "staged"|"approved"|"rejected"|"invalidated", reason?}
  let proposalSeq = 0;

  const add = (rec) => {
    const e = world.add({ ...rec, credentials: [...rec.credentials] });
    byId.set(rec.id, e); dirty.add(rec.id); removedIds.delete(rec.id);
    return e;
  };
  const removeById = (id) => {
    const e = byId.get(id);
    if (!e) return;
    world.remove(e); byId.delete(id); dirty.delete(id); removedIds.add(id);
  };
  const views = () => [...world.entities].map((e) => ({ ...e, credentials: [...e.credentials] }));

  // Writer 1: SSE sync — the 002 syncFromPipeline contract, extended to re-validate
  // staged proposals in the SAME transition that removes entities.
  function syncFromPipeline(snapshotRecs) {
    const incoming = new Set(snapshotRecs.map((r) => r.id));
    for (const e of [...world.entities]) if (!incoming.has(e.id)) removeById(e.id);
    for (const rec of snapshotRecs) {
      const existing = byId.get(rec.id);
      if (existing) {
        if (existing.status !== rec.status) { existing.status = rec.status; dirty.add(rec.id); }
        if (existing.cpu !== rec.cpu || existing.mem !== rec.mem) { existing.cpu = rec.cpu; existing.mem = rec.mem; dirty.add(rec.id); }
      } else add(rec);
    }
    // Proposal re-validation (generalized clearSelectionIfMissing):
    for (const [pid, p] of proposals) {
      if (p.status !== "staged") continue;
      for (const op of p.ops) {
        const v = validateOp(op, byId);
        if (!v.ok) { p.status = "invalidated"; p.reason = v.error; break; }
      }
    }
  }

  // Writer 2: LLM ops — staged, never touching the live world.
  function propose(ops) {
    const errors = [];
    for (const op of ops) {
      const v = validateOp(op, byId);
      if (!v.ok) errors.push(v.error);
    }
    if (errors.length) return { accepted: false, errors };
    const pid = `prop-${++proposalSeq}`;
    proposals.set(pid, { ops, status: "staged" });
    return { accepted: true, proposalId: pid };
  }

  // Preview: overlay staged ops onto views WITHOUT touching the world (for the UI panel).
  function previewViews(pid) {
    const p = proposals.get(pid);
    if (!p || p.status !== "staged") return views();
    const overlay = new Map(views().map((v) => [v.id, v]));
    for (const op of p.ops) {
      if (op.op === "set_status") overlay.get(op.id) && (overlay.get(op.id).status = op.value);
      else if (op.op === "set_credentials") overlay.get(op.id) && (overlay.get(op.id).credentials = [...op.list]);
      else if (op.op === "move") { const t = overlay.get(op.id); if (t) { t.x = op.x; t.y = op.y; } }
      else if (op.op === "add_module") overlay.set(op.rec.id, { ...op.rec, credentials: [...op.rec.credentials] });
      else if (op.op === "remove_module") overlay.delete(op.id);
    }
    return [...overlay.values()];
  }

  // Approval gate: re-validate at approval time, then apply through the SAME primitives
  // the SSE writer uses (single mediation path).
  function approve(pid) {
    const p = proposals.get(pid);
    if (!p) return { ok: false, error: "unknown proposal" };
    if (p.status !== "staged") return { ok: false, error: `proposal is ${p.status}, not staged` };
    for (const op of p.ops) {
      const v = validateOp(op, byId);
      if (!v.ok) { p.status = "invalidated"; p.reason = v.error; return { ok: false, error: v.error }; }
    }
    for (const op of p.ops) {
      if (op.op === "set_status") { byId.get(op.id).status = op.value; dirty.add(op.id); }
      else if (op.op === "set_credentials") { byId.get(op.id).credentials = [...op.list]; dirty.add(op.id); }
      else if (op.op === "move") { const t = byId.get(op.id); t.x = op.x; t.y = op.y; dirty.add(op.id); }
      else if (op.op === "add_module") add({ ...op.rec, credentials: [...op.rec.credentials] });
      else if (op.op === "remove_module") removeById(op.id);
    }
    p.status = "approved";
    return { ok: true };
  }

  function reject(pid) {
    const p = proposals.get(pid);
    if (!p || p.status !== "staged") return { ok: false };
    p.status = "rejected";
    return { ok: true };
  }

  return { world, byId, dirty, removedIds, proposals, views, syncFromPipeline, propose, previewViews, approve, reject };
}
