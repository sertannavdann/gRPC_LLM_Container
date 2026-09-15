'use client';

/**
 * Choke-point dirty tracker for the ECS world (Phase 9, spike 006 run.mjs
 * lines 24-57 — the ENTIRE tracker is ~20 lines by design).
 *
 * The delta version counter lives HERE, not in XState context, per
 * CONTEXT.md's Claude's-Discretion note.
 */

export interface DirtyTracker {
  dirty: Set<string>;
  removedIds: Set<string>;
  version: () => number;
  markDirty: (id: string) => void;
  markRemoved: (id: string) => void;
  clearSinceLastInvocation: () => number;
}

export function createDirtyTracker(): DirtyTracker {
  const dirty = new Set<string>();
  const removedIds = new Set<string>();
  let version = 0;

  function markDirty(id: string) {
    dirty.add(id);
    removedIds.delete(id);
  }

  function markRemoved(id: string) {
    dirty.delete(id);
    removedIds.add(id);
  }

  function clearSinceLastInvocation() {
    dirty.clear();
    removedIds.clear();
    version++;
    return version;
  }

  return {
    dirty,
    removedIds,
    version: () => version,
    markDirty,
    markRemoved,
    clearSinceLastInvocation,
  };
}
