'use client';

/**
 * The single mediation layer for LLM-authored writes to the ECS world
 * (Phase 9, ported from spike 007 — .planning/spikes/007-llm-writes-world/mediation.mjs).
 *
 * Ownership policy (from spike 007 + 09-CONTEXT.md LOCKED decision):
 * - SSE sync (sync.ts) is the ONLY writer that may add/remove service/stage
 *   entities and the only source of truth for module existence too — EXCEPT
 *   that approved LLM proposals may add/remove *module* entities (the Phase 8
 *   build-a-module flow), which then round-trips through the backend and
 *   comes back in later SSE snapshots.
 * - LLM ops arrive as STAGED PROPOSALS. Nothing touches the live world until
 *   a human calls approve().
 * - Every proposal is re-validated against the live world at THREE points:
 *   1. propose() — at staging time.
 *   2. revalidateStagedProposals() — inside sync.ts's syncRecords(), in the
 *      SAME transition that performs SSE-driven removals (the
 *      clearSelectionIfMissing pattern generalized to proposals).
 *   3. approve() — immediately before applying, against the LIVE world.
 *
 * Widening OWNERSHIP requires a CONTEXT.md decision update, not a code edit.
 */

import { z } from 'zod';
import { STATUSES, LIFECYCLES, type EntityRecord, type CanvasView, type Status, type Lifecycle } from './types';
import { canvasWorld, touch, type createPipelineWorld } from './world';

// ── Op schema (zod) ─────────────────────────────────────────────────────────

const StatusEnum = z.enum(STATUSES as unknown as [Status, ...Status[]]);
const LifecycleEnum = z.enum(LIFECYCLES as unknown as [Lifecycle, ...Lifecycle[]]);

const SetStatusOp = z
  .object({ op: z.literal('set_status'), id: z.string(), value: StatusEnum })
  .strict();

const SetCredentialsOp = z
  .object({ op: z.literal('set_credentials'), id: z.string(), list: z.array(z.string()) })
  .strict();

const MoveOp = z
  .object({ op: z.literal('move'), id: z.string(), x: z.number(), y: z.number() })
  .strict();

const AddModuleRec = z
  .object({
    id: z.string().startsWith('module-'),
    label: z.string(),
    status: StatusEnum,
    lifecycle: LifecycleEnum.nullable(),
    category: z.string().optional(),
  })
  .strict();

const AddModuleOp = z
  .object({ op: z.literal('add_module'), rec: AddModuleRec })
  .strict();

const RemoveModuleOp = z
  .object({ op: z.literal('remove_module'), id: z.string() })
  .strict();

export const MutationOp = z.discriminatedUnion('op', [
  SetStatusOp,
  SetCredentialsOp,
  MoveOp,
  AddModuleOp,
  RemoveModuleOp,
]);

export type MutationOpT = z.infer<typeof MutationOp>;

// Ownership policy — checked against the LIVE world, separate from schema
// validity. Widening this map requires a CONTEXT.md decision update.
export const OWNERSHIP: Record<MutationOpT['op'], EntityRecord['kind'][]> = {
  set_status: ['service', 'module', 'stage'],
  set_credentials: ['module'],
  move: ['service', 'module', 'stage'],
  add_module: ['module'],
  remove_module: ['module'],
};

export interface ValidationResult {
  ok: boolean;
  error?: string;
}

/**
 * Two sequential passes: schema validity (zod), then referential + ownership
 * validity against the live world. Ported from mediation.mjs lines 25-52.
 */
export function validateOp(op: unknown, byId: Map<string, EntityRecord>): ValidationResult {
  const parsed = MutationOp.safeParse(op);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const path = issue?.path?.length ? issue.path.join('.') : '(root)';
    return { ok: false, error: `invalid op: ${path}: ${issue?.message ?? 'schema validation failed'}` };
  }

  const validOp = parsed.data;

  if (validOp.op === 'add_module') {
    if (byId.has(validOp.rec.id)) {
      return { ok: false, error: `add_module: "${validOp.rec.id}" already exists` };
    }
    return { ok: true };
  }

  const target = byId.get(validOp.id);
  if (!target) {
    return { ok: false, error: `${validOp.op}: entity "${validOp.id}" does not exist (stale proposal?)` };
  }
  if (!OWNERSHIP[validOp.op].includes(target.kind)) {
    return { ok: false, error: `${validOp.op}: not permitted on kind "${target.kind}" (ownership policy)` };
  }
  return { ok: true };
}

// ── Staged proposals ─────────────────────────────────────────────────────────

export type ProposalStatus = 'staged' | 'approved' | 'rejected' | 'invalidated';

export interface Proposal {
  ops: MutationOpT[];
  status: ProposalStatus;
  reason?: string;
}

export interface ProposeResult {
  accepted: boolean;
  proposalId?: string;
  errors?: string[];
}

export interface ApproveResult {
  ok: boolean;
  error?: string;
}

type World = ReturnType<typeof createPipelineWorld>;

export function createMediation(w: World) {
  const proposals = new Map<string, Proposal>();
  let seq = 0;

  function propose(ops: MutationOpT[]): ProposeResult {
    // Re-validation point 1 of 3: validateOp() runs MutationOp.safeParse(op) below.
    const errors: string[] = [];
    for (const op of ops) {
      const v = validateOp(op, w.byId); // safeParse pass, then referential/ownership pass
      if (!v.ok && v.error) errors.push(v.error);
    }
    if (errors.length) return { accepted: false, errors };
    const proposalId = `prop-${++seq}`;
    proposals.set(proposalId, { ops, status: 'staged' });
    // Staging a proposal changes what `proposalAnnotations()` derives for the
    // target node (the violet badge/ghost/removal treatment) — touch() the
    // ECS bridge so page.tsx's version-keyed patch effect picks it up on the
    // very next render, rather than silently waiting for the next real SSE
    // tick (up to 2s) to happen to also call touch(). Never touches the live
    // world itself (D9-08) — this is purely a reactivity notification.
    touch();
    return { accepted: true, proposalId };
  }

  /**
   * Overlay staged ops onto a COPY of the current views. Must never touch
   * the live world — preview is a pure overlay (locked decision D9-08).
   */
  function previewViews(proposalId: string): CanvasView[] {
    const p = proposals.get(proposalId);
    if (!p || p.status !== 'staged') return w.views();
    const overlay = new Map<string, CanvasView>(w.views().map((v) => [v.id, v]));
    for (const op of p.ops) {
      if (op.op === 'set_status') {
        const t = overlay.get(op.id);
        if (t) overlay.set(op.id, { ...t, status: op.value });
      } else if (op.op === 'set_credentials') {
        const t = overlay.get(op.id);
        if (t) overlay.set(op.id, { ...t, creds: [...op.list] });
      } else if (op.op === 'move') {
        // move affects x/y which are excluded from CanvasView by design;
        // nothing to overlay in the view projection.
      } else if (op.op === 'add_module') {
        const { id, label, status, lifecycle } = op.rec;
        overlay.set(id, {
          id,
          label,
          kind: 'module',
          status,
          lifecycle,
          detail: null,
          latency: null,
          creds: [],
          flags: [],
        });
      } else if (op.op === 'remove_module') {
        overlay.delete(op.id);
      }
    }
    return [...overlay.values()];
  }

  function approve(proposalId: string): ApproveResult {
    const p = proposals.get(proposalId);
    if (!p) return { ok: false, error: 'unknown proposal' };
    if (p.status !== 'staged') return { ok: false, error: `proposal is ${p.status}, not staged` };

    // Re-validation point 3 of 3: against the LIVE world (safeParse + referential/ownership), immediately before applying.
    for (const op of p.ops) {
      const v = validateOp(op, w.byId); // safeParse pass, then referential/ownership pass
      if (!v.ok) {
        p.status = 'invalidated';
        p.reason = v.error;
        return { ok: false, error: v.error };
      }
    }

    for (const op of p.ops) {
      if (op.op === 'set_status') {
        w.mutate(op.id, { status: op.value });
      } else if (op.op === 'set_credentials') {
        w.mutate(op.id, { creds: [...op.list] });
      } else if (op.op === 'move') {
        w.mutate(op.id, { x: op.x, y: op.y });
      } else if (op.op === 'add_module') {
        w.add({
          id: op.rec.id,
          label: op.rec.label,
          kind: 'module',
          status: op.rec.status,
          lifecycle: op.rec.lifecycle,
          detail: null,
          latency: null,
          creds: [],
          flags: [],
          x: 0,
          y: 0,
        });
      } else if (op.op === 'remove_module') {
        w.removeById(op.id);
      }
    }

    p.status = 'approved';
    // Same reactivity note as propose(): the mutation choke points above
    // (w.mutate/w.add/w.removeById) mark entities dirty but do not
    // themselves notify React — only sync.ts's syncRecords() and
    // restoreSnapshot() called touch() before this. Without this call, the
    // canvas would visibly lag the approval by up to one real SSE tick.
    touch();
    return { ok: true };
  }

  function reject(proposalId: string): ApproveResult {
    const p = proposals.get(proposalId);
    if (!p || p.status !== 'staged') return { ok: false };
    p.status = 'rejected';
    touch(); // clears the staged-proposal badge immediately — see propose()'s note.
    return { ok: true };
  }

  function getProposal(proposalId: string): Proposal | undefined {
    return proposals.get(proposalId);
  }

  /**
   * Re-validation point 2 of 3. Called by sync.ts's syncRecords() in the SAME
   * transition that performs SSE-driven removals — the generalized
   * clearSelectionIfMissing pattern applied to proposals.
   */
  function revalidateStagedProposals(): void {
    for (const p of proposals.values()) {
      if (p.status !== 'staged') continue;
      for (const op of p.ops) {
        const v = validateOp(op, w.byId); // safeParse pass, then referential/ownership pass
        if (!v.ok) {
          p.status = 'invalidated';
          p.reason = v.error;
          break;
        }
      }
    }
  }

  return { proposals, propose, previewViews, approve, reject, revalidateStagedProposals, getProposal };
}

export const canvasMediation = createMediation(canvasWorld);
