'use client';

/**
 * History layer over the mediated ECS world (Phase 9, ported from spike 008 —
 * .planning/spikes/008-snapshot-replay-and-rewind/history.mjs).
 *
 * Two complementary records (the survey's context-management pairing: snapshots for
 * restore points, logs for reconstruction):
 * - SnapshotRing: bounded ring of canonical JSON snapshots (cheap per 005b: ~4KB/26
 *   entities). Snapshots capture FULL entities, including ECS-only/UI-only fields —
 *   which is what closes the 002 gap for rewind scenarios.
 * - EventLog: append-only list of semantic events ("sync" with snapshot recs, "approve"
 *   with ops). Replay = re-running events through a fresh mediated world; determinism
 *   comes from the mediation layer being the single write path.
 *
 * Rewind = clear-then-restore into the SAME world object (005a showed in-place restore
 * over a drifted world is unsafe; clearing first is the only safe mode).
 */

import type { EntityRecord } from './types';
import { canonicalize } from './verbalize';
import { canvasWorld, touch, type createPipelineWorld } from './world';
import { canvasMediation, type createMediation } from './mediation';
import { syncRecords } from './sync';

type World = ReturnType<typeof createPipelineWorld>;
type Mediation = ReturnType<typeof createMediation>;

export interface SnapshotEntry {
  label: string;
  json: string;
  bytes: number;
}

export function createSnapshotRing(capacity: number) {
  const ring: SnapshotEntry[] = [];
  return {
    push(label: string, entityRecords: EntityRecord[]) {
      const json = JSON.stringify(canonicalize(entityRecords));
      // Node's byte-length helper is unavailable in the browser; TextEncoder is the port.
      ring.push({ label, json, bytes: new TextEncoder().encode(json).length });
      if (ring.length > capacity) ring.shift();
    },
    get(label: string): SnapshotEntry | null {
      for (let i = ring.length - 1; i >= 0; i--) if (ring[i].label === label) return ring[i];
      return null;
    },
    at(offsetFromHead: number): SnapshotEntry | null {
      return ring[ring.length - 1 + offsetFromHead] ?? null;
    },
    totalBytes: () => ring.reduce((s, r) => s + r.bytes, 0),
    size: () => ring.length,
  };
}

export type SnapshotRing = ReturnType<typeof createSnapshotRing>;

// Restore a snapshot into a mediated world: clear everything, re-add records verbatim.
// NEVER restore in place over a drifted world — spike 005a proved this duplicates
// entities, and the clear step below is the entire mitigation.
export function restoreSnapshot(w: World, snapshotJson: string) {
  for (const e of [...w.world.entities]) {
    w.byId.delete(e.id);
    w.world.remove(e);
  }
  w.tracker.dirty.clear();
  w.tracker.removedIds.clear();
  for (const rec of JSON.parse(snapshotJson) as EntityRecord[]) {
    w.add(rec); // routes through the add() choke point, so every restored id lands in dirty
  }
  touch(); // NEW vs spike: browser port must call touch() so useSyncExternalStore observes restore
}

export interface HistoryEvent {
  seq: number;
  type: 'sync' | 'approve';
  payload: unknown;
}

export function createEventLog() {
  let events: HistoryEvent[] = [];
  let nextSeq = 0;
  return {
    record(type: HistoryEvent['type'], payload: unknown) {
      events.push({ seq: nextSeq++, type, payload });
    },
    slice: (from = 0, to = events.length) => events.slice(from, to),
    length: () => events.length,
    lastSeq: () => nextSeq - 1,
    // Checkpointing extension (beyond the spike): drop everything before
    // upToSeq so the log cannot grow unbounded across a session. seq is a
    // monotonic counter independent of array length, so this is safe to
    // call repeatedly without corrupting later seq assignments.
    dropPrefix(upToSeq: number) {
      events = events.filter((e) => e.seq >= upToSeq);
    },
  };
}

export type EventLog = ReturnType<typeof createEventLog>;

// Deterministic replay: run events through a mediated world (fresh or just-restored).
// Redo is log replay through the mediation layer — never inverse ops (locked decision D9-12).
export function replayEvents(w: World, m: Mediation, events: HistoryEvent[]) {
  for (const ev of events) {
    if (ev.type === 'sync') {
      syncRecords(w, m, ev.payload as EntityRecord[]);
    } else if (ev.type === 'approve') {
      const ops = ev.payload as Parameters<Mediation['propose']>[0];
      const r = m.propose(ops);
      if (!r.accepted) {
        throw new Error(`replay diverged: proposal rejected: ${r.errors?.join('; ')}`);
      }
      const a = m.approve(r.proposalId!);
      if (!a.ok) {
        throw new Error(`replay diverged: approve failed: ${a.error}`);
      }
    }
  }
}

// ── Composed history API ─────────────────────────────────────────────────

export interface UndoRedoResult {
  ok: boolean;
  label?: string;
}

export function createHistory(w: World, m: Mediation, { capacity = 20 }: { capacity?: number } = {}) {
  const ring = createSnapshotRing(capacity);
  const log = createEventLog();
  let syncSeq = 0;
  let cursor = 0; // 0 = at the newest ring entry; increases as undo() walks backward

  function currentRecords(): EntityRecord[] {
    return [...w.world.entities];
  }

  function recordSync(records: EntityRecord[]) {
    const label = `sync-${++syncSeq}`;
    ring.push(label, records);
    log.record('sync', records);
    // Checkpoint: drop the event-log prefix older than the oldest surviving
    // ring entry so the log cannot grow unbounded across a session (spike
    // 008's explicit carry-forward constraint). The ring's capacity bounds
    // how far back a snapshot can restore, so the log only ever needs to
    // retain events back to that same horizon.
    log.dropPrefix(Math.max(0, log.lastSeq() - capacity + 1));
    cursor = 0;
  }

  function approveWithHistory(pid: string): { ok: boolean; error?: string; label: string } {
    const label = `pre-approve:${pid}`;
    ring.push(label, currentRecords());
    const proposal = m.getProposal(pid);
    const result = m.approve(pid);
    if (result.ok && proposal) {
      log.record('approve', proposal.ops);
    }
    cursor = 0;
    return { ...result, label };
  }

  function rejectWithRewind(pid: string): { ok: boolean; rewound: boolean } {
    const proposal = m.getProposal(pid);
    if (!proposal) return { ok: false, rewound: false };

    if (proposal.status === 'staged') {
      const r = m.reject(pid);
      return { ok: r.ok, rewound: false };
    }

    if (proposal.status === 'approved') {
      const entry = ring.get(`pre-approve:${pid}`);
      if (!entry) return { ok: false, rewound: false };
      restoreSnapshot(w, entry.json);
      proposal.status = 'rejected';
      return { ok: true, rewound: true };
    }

    return { ok: false, rewound: false };
  }

  function undo(): UndoRedoResult {
    const target = ring.at(-1 - cursor);
    if (!target) return { ok: false };
    cursor++;
    restoreSnapshot(w, target.json);
    return { ok: true, label: target.label };
  }

  function redo(): UndoRedoResult {
    if (cursor <= 0) return { ok: false };
    cursor--;
    if (cursor === 0) {
      // At the newest ring entry: replay the tail of the event log instead
      // of restoring a snapshot (redo is log replay, not inverse ops).
      const tail = log.slice(Math.max(0, log.length() - 1));
      const newest = ring.at(0);
      if (newest) {
        restoreSnapshot(w, newest.json);
      }
      if (tail.length) replayEvents(w, m, tail);
      return { ok: true, label: newest?.label };
    }
    const target = ring.at(-1 - cursor);
    if (!target) return { ok: false };
    restoreSnapshot(w, target.json);
    return { ok: true, label: target.label };
  }

  function canUndo(): boolean {
    return ring.at(-1 - cursor) !== null;
  }

  function canRedo(): boolean {
    return cursor > 0;
  }

  return {
    ring,
    log,
    recordSync,
    approveWithHistory,
    rejectWithRewind,
    undo,
    redo,
    canUndo,
    canRedo,
  };
}

export type History = ReturnType<typeof createHistory>;

export const canvasHistory = createHistory(canvasWorld, canvasMediation);
