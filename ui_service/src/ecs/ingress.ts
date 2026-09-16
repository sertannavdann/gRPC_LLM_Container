'use client';

/**
 * The single documented entry point for LLM-authored ops into the browser
 * mediation layer (Phase 9 plan 09).
 *
 * `submitCanvasOps` adds NO logic of its own — it forwards straight to the
 * mediation layer's staging call, which owns all zod schema validation and
 * OWNERSHIP checks (see mediation.ts). Ops are NEVER applied here; applying
 * requires a human clicking "Approve Change" in the NodeDetailPanel, which
 * drives `canvasHistory.approveWithHistory()`.
 *
 * A future orchestrator-driven chat/ActionCard transport should call this
 * function directly (import it into that transport's handler) rather than
 * talking to `canvasMediation` itself — this file is the seam, and widening
 * what can reach the mediation layer means adding a new caller of
 * `submitCanvasOps`, not a new bypass. No such orchestrator-side transport is
 * built in Phase 9 — it is a deferred follow-up (see 09-09-SUMMARY.md).
 */

import { canvasMediation, type ProposeResult } from './mediation';
import { canvasWorld } from './world';
import { toCompactDsl, toDelta } from './verbalize';

export function submitCanvasOps(ops: unknown[]): ProposeResult {
  return canvasMediation.propose(ops as Parameters<typeof canvasMediation.propose>[0]);
}

/**
 * Dev-seam helpers exposed alongside `submitCanvasOps` so the propose ->
 * preview -> approve/reject -> rewind loop can be exercised end-to-end by
 * Playwright without a chat transport (see Task 3's
 * `e2e/pipeline-canvas-ops.spec.ts`). Pure read-only reflections of ECS
 * state — neither mutates the live world.
 */
function delta() {
  return toDelta(
    canvasWorld.tracker.dirty,
    canvasWorld.tracker.removedIds,
    canvasWorld.viewOf,
    canvasWorld.tracker.version(),
  );
}

function cState(): string {
  return toCompactDsl(canvasWorld.views());
}

/**
 * Dev-seam helper: a single entity's compact-DSL line (or null if absent).
 * Exists so E2E rewind assertions can verify byte-identical restoration of
 * the entity a canvas op actually targeted, without being defeated by
 * unrelated live SSE-driven telemetry (e.g. service latency_ms) that
 * fluctuates independently of the rewind under test across the real
 * docker-compose stack's 2s SSE tick.
 */
function entityLine(id: string): string | null {
  const view = canvasWorld.viewOf(id);
  return view ? toCompactDsl([view]).split('\n').slice(1).join('\n') : null;
}

// Guarded browser handle: the NODE_ENV-only guard is NOT sufficient because
// ui_service/Dockerfile sets `ENV NODE_ENV=production` and the compose stack
// Playwright targets is a production build — a dev-only guard would compile
// this seam out entirely. NEXT_PUBLIC_CANVAS_DEV_SEAM is inlined at BUILD
// time by Next.js, so the Dockerfile/docker-compose.yaml wiring controls
// whether this handle exists in a given image. Setting the flag to anything
// other than '1' removes the handle entirely.
if (
  typeof window !== 'undefined' &&
  (process.env.NODE_ENV !== 'production' || process.env.NEXT_PUBLIC_CANVAS_DEV_SEAM === '1')
) {
  (window as unknown as { __nexusCanvas: unknown }).__nexusCanvas = {
    submitCanvasOps,
    delta,
    cState,
    entityLine,
  };
}
