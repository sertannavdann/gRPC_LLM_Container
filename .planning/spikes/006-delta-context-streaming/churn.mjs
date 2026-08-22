// Deterministic SSE-like churn script for spike 006. Seeded LCG — no Math.random, so
// every run and both implementations replay the identical session.

import { STATUSES } from "./fixture.mjs";

export function makeRng(seed = 1337) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

// Generates `ticks` ticks. Each tick is a list of ops:
//   {op:"status", id, value} | {op:"metrics", id, cpu, mem} | {op:"remove", id} | {op:"add", rec}
// Mirrors real pipeline-stream behavior: mostly metric jitter + status flips on a few
// entities per tick, occasional module uninstall/reinstall.
export function makeChurnScript(fixture, ticks, seed = 1337) {
  const rng = makeRng(seed);
  const ids = fixture.map((r) => r.id);
  const removable = fixture.filter((r) => r.kind === "module").map((r) => r.id);
  const recsById = new Map(fixture.map((r) => [r.id, r]));
  const removed = new Set();
  const script = [];

  for (let t = 0; t < ticks; t++) {
    const ops = [];
    // 2-4 metric jitters
    const jitters = 2 + Math.floor(rng() * 3);
    for (let j = 0; j < jitters; j++) {
      const id = ids[Math.floor(rng() * ids.length)];
      if (removed.has(id)) continue;
      ops.push({
        op: "metrics", id,
        cpu: Math.round(rng() * 1000) / 10,
        mem: Math.round(rng() * 50000) / 10,
      });
    }
    // ~50% chance of one status flip
    if (rng() < 0.5) {
      const id = ids[Math.floor(rng() * ids.length)];
      if (!removed.has(id)) {
        ops.push({ op: "status", id, value: STATUSES[1 + Math.floor(rng() * (STATUSES.length - 1))] });
      }
    }
    // ~10% chance of remove; ~10% chance of re-adding a previously removed module
    if (rng() < 0.1 && removable.length) {
      const id = removable[Math.floor(rng() * removable.length)];
      if (!removed.has(id)) { removed.add(id); ops.push({ op: "remove", id }); }
    }
    if (rng() < 0.1 && removed.size) {
      const id = [...removed][0];
      removed.delete(id);
      ops.push({ op: "add", rec: recsById.get(id) });
    }
    script.push(ops);
  }
  return script;
}
