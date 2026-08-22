// Spike 008 — history layer over the 007 mediation world.
//
// Two complementary records (the survey's context-management pairing: snapshots for
// restore points, logs for reconstruction):
// - SnapshotRing: bounded ring of canonical JSON snapshots (cheap per 005b: ~4KB/26
//   entities). Snapshots capture FULL entities, including ECS-only/UI-only fields —
//   which is what closes the 002 gap for rewind scenarios.
// - EventLog: append-only list of semantic events ("sync" with snapshot recs, "approve"
//   with ops). Replay = re-running events through a fresh mediated world; determinism
//   comes from the mediation layer being the single write path.
//
// Rewind = clear-then-restore into the SAME world object (005a showed in-place restore
// over a drifted world is unsafe; clearing first is the only safe mode).

export function createSnapshotRing(capacity) {
  const ring = [];
  return {
    push(label, worldViews) {
      const json = JSON.stringify(
        [...worldViews].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
      );
      ring.push({ label, json, bytes: Buffer.byteLength(json, "utf8") });
      if (ring.length > capacity) ring.shift();
    },
    get(label) {
      for (let i = ring.length - 1; i >= 0; i--) if (ring[i].label === label) return ring[i];
      return null;
    },
    at(offsetFromHead) {
      return ring[ring.length - 1 + offsetFromHead] ?? null;
    },
    totalBytes: () => ring.reduce((s, r) => s + r.bytes, 0),
    size: () => ring.length,
  };
}

// Restore a snapshot into a mediated world: clear everything, re-add records verbatim.
export function restoreSnapshot(w, snapshotJson) {
  for (const e of [...w.world.entities]) {
    w.byId.delete(e.id);
    w.world.remove(e);
  }
  w.dirty.clear();
  w.removedIds.clear();
  for (const rec of JSON.parse(snapshotJson)) {
    const entity = w.world.add({ ...rec, credentials: [...rec.credentials] });
    w.byId.set(rec.id, entity);
    w.dirty.add(rec.id); // downstream consumers (006 deltas, React Flow patch) must see the restore
  }
}

export function createEventLog() {
  const events = [];
  return {
    record(type, payload) { events.push({ seq: events.length, type, payload }); },
    slice: (from = 0, to = events.length) => events.slice(from, to),
    length: () => events.length,
  };
}

// Deterministic replay: run events through a mediated world (fresh or just-restored).
export function replayEvents(w, events) {
  for (const ev of events) {
    if (ev.type === "sync") w.syncFromPipeline(ev.payload);
    else if (ev.type === "approve") {
      const r = w.propose(ev.payload);
      if (!r.accepted) throw new Error(`replay diverged: proposal rejected: ${r.errors?.join("; ")}`);
      const a = w.approve(r.proposalId);
      if (!a.ok) throw new Error(`replay diverged: approve failed: ${a.error}`);
    }
  }
}
