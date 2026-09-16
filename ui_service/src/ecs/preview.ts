'use client';

/**
 * Pure proposal -> node-annotation derivation, plus the pending-confirmation
 * registry for optimistic `add_module` approvals (Phase 9 plan 08).
 *
 * Mirrors the overlay semantics of `mediation.ts`'s `previewViews()` (which
 * overlays a COPY of the live views for the review panel's diff) but targets
 * a different consumer: `page.tsx`'s buffered React Flow patch effect, which
 * needs a per-node-id annotation object it can attach to `data.proposal`
 * without ever touching the live world (locked decision D9-08 — preview is a
 * pure overlay on views, never a mutation).
 *
 * `createPendingConfirmations()` is the separate, DoS-mitigating (T-09-03)
 * grace-period registry for optimistically-approved `add_module` ops: the
 * entity is live in the ECS world immediately on approval, but the canvas
 * shows a distinct "confirming" treatment until the next SSE snapshot proves
 * the backend actually persisted it, or the grace window elapses and the
 * optimistic entity is removed through the ECS choke point.
 */

import type { Proposal } from './mediation';

export type ProposalAnnotation = {
  proposalId: string;
  kind: 'field' | 'ghost' | 'removal';
  deltaLines: string[];
};

/**
 * Pure function: proposals map -> entity id -> annotation. Only `staged`
 * proposals produce an annotation; `approved`/`rejected`/`invalidated`
 * proposals are either live state already (approved) or dead (the other
 * two) and must not annotate anything. Never reads or writes the live
 * world — the input is a plain Map, the output is a plain Map.
 */
export function proposalAnnotations(proposals: Map<string, Proposal>): Map<string, ProposalAnnotation> {
  const out = new Map<string, ProposalAnnotation>();

  for (const [proposalId, p] of proposals) {
    if (p.status !== 'staged') continue;

    for (const op of p.ops) {
      if (op.op === 'add_module') {
        // ghost: no live state to diff against, delta lines stay empty.
        out.set(op.rec.id, { proposalId, kind: 'ghost', deltaLines: [] });
        continue;
      }

      if (op.op === 'remove_module') {
        out.set(op.id, { proposalId, kind: 'removal', deltaLines: [] });
        continue;
      }

      // Field-level ops: set_status / set_credentials / move. Exact UI-SPEC
      // arrow notation "{field} → {value}". set_credentials NEVER renders
      // credential names (T-09-06) — a count only.
      const line =
        op.op === 'set_status'
          ? `status → ${op.value}`
          : op.op === 'set_credentials'
            ? `credentials → ${op.list.length} items`
            : `position → (${op.x}, ${op.y})`;

      const existing = out.get(op.id);
      if (existing && existing.kind === 'field' && existing.proposalId === proposalId) {
        existing.deltaLines.push(line);
      } else {
        out.set(op.id, { proposalId, kind: 'field', deltaLines: [line] });
      }
    }
  }

  return out;
}

export interface PendingConfirmations {
  mark(id: string): void;
  resolve(id: string): void;
  expired(nowMs: number): string[];
  pendingIds(): string[];
  clear(): void;
}

export interface CreatePendingConfirmationsOptions {
  /**
   * [DEFAULT] 4000ms — 2x the existing 2s SSE tick interval, giving one full
   * missed-tick buffer before treating a non-confirmation as failure. Not a
   * CONTEXT.md-locked number; adjustable if the SSE interval changes.
   */
  graceMs?: number;
}

/**
 * Registry of optimistically-approved entity ids awaiting SSE confirmation.
 * `mark(id)` records the approval time; `resolve(id)` clears it once the id
 * shows up in a real SSE snapshot; `expired(nowMs)` returns ids whose grace
 * window elapsed without confirmation, so the caller can remove them through
 * the ECS choke point (T-09-03).
 */
export function createPendingConfirmations(
  { graceMs = 4000 }: CreatePendingConfirmationsOptions = {},
): PendingConfirmations {
  const marks = new Map<string, number>();

  return {
    mark(id: string) {
      marks.set(id, Date.now());
    },
    resolve(id: string) {
      marks.delete(id);
    },
    expired(nowMs: number): string[] {
      const ids: string[] = [];
      for (const [id, markedAt] of marks) {
        if (nowMs - markedAt > graceMs) ids.push(id);
      }
      return ids;
    },
    pendingIds(): string[] {
      return [...marks.keys()];
    },
    clear() {
      marks.clear();
    },
  };
}

/**
 * Module-scope singleton so plan 09's approval flow (`add_module` approval
 * -> `pending.mark(id)`) and `page.tsx`'s ingestion effect (`pending.resolve`
 * / `pending.expired`) share the same registry without prop drilling —
 * mirrors the `canvasMediation`/`canvasWorld` singleton pattern already used
 * elsewhere in `ecs/`.
 */
export const pendingConfirmations = createPendingConfirmations();
