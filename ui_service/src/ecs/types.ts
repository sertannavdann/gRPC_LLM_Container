'use client';

/**
 * Shared ECS entity/view/id contract for the pipeline canvas (Phase 9).
 *
 * Every downstream plan (Python c_state port in plan 02, TS verbalizer in
 * plan 03, and the miniplex world itself) imports this file rather than
 * re-declaring the vocabulary, id scheme, or DSL grammar.
 *
 * C_STATE DSL GRAMMAR (implemented verbatim by plan 02's Python port and
 * plan 03's TS verbalizer — this comment is the contract, not decoration):
 *
 *   header line: `# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>][ detail=<detail>][ latency=<ms>][ creds:<c1,c2>][ flags:<f1,f2>]`
 *
 *   Then, for each kind in ascending kind order: a `[<kind>]` group header,
 *   then one line per entity in ascending logical-id order. Optional segments
 *   are omitted entirely when the value is null or the array is empty.
 *   `latency` is rendered as a rounded integer on BOTH sides
 *   (`Math.round(v)` in TS, `round(v)` in Python) so the two ports cannot
 *   diverge on float formatting. Labels are wrapped in double quotes with any
 *   embedded `"` stripped.
 */

// ── Vocabulary ───────────────────────────────────────────────────────────────

export const KINDS = ['adapter', 'module', 'service', 'stage', 'tool'] as const;

export const STATUSES = [
  'unknown',
  'running',
  'degraded',
  'disabled',
  'error',
  'failed',
  'stopped',
  'building',
  'validating',
  'available',
  // 'idle' is required because the production ServiceState union
  // ('running' | 'error' | 'idle') can produce it — it is NOT mapped to
  // 'unknown'; the test must reflect reality, not aspiration.
  'idle',
] as const;

export const LIFECYCLES = [
  'discovered',
  'installed',
  'pending',
  'validating',
  'approved',
  'rejected',
  'enabled',
  'disabled',
  'error',
] as const;

export type Kind = (typeof KINDS)[number];
export type Status = (typeof STATUSES)[number];
export type Lifecycle = (typeof LIFECYCLES)[number];

// ── Entity / View contracts ─────────────────────────────────────────────────

/**
 * The full ECS entity, including UI-only fields. Snapshots capture full
 * records (locked decision D9-13) — history/rewind depends on this shape
 * being complete, not a projection.
 */
export interface EntityRecord {
  id: string;
  label: string;
  kind: Kind;
  status: Status;
  lifecycle: Lifecycle | null;
  detail: string | null;
  latency: number | null;
  creds: string[];
  flags: string[];
  x: number;
  y: number;
}

/**
 * The c_state projection of an EntityRecord. `x`/`y` are deliberately
 * EXCLUDED: they are user-owned drag state, and including them would break
 * the "byte-stable across churn for unchanged worlds" Done Criterion the
 * moment a node is dragged. Snapshots (history) still carry x/y; the
 * verbalizer does not.
 */
export type CanvasView = Omit<EntityRecord, 'x' | 'y'>;

// ── Id scheme ────────────────────────────────────────────────────────────────

/**
 * Produces the same logical ids the existing React Flow page
 * (ui_service/src/app/pipeline/page.tsx) already uses:
 *   service -> svc-${key}, tool -> tool-${key}, adapter -> adapter-${key},
 *   module -> module-${key}, stage -> stage-${key}.
 *
 * The ECS logical id MUST equal the React Flow node id (the buffered patch
 * in plan 07 matches by id).
 */
export function entityIdFor(kind: Kind, key: string): string {
  switch (kind) {
    case 'service':
      return `svc-${key}`;
    case 'tool':
      return `tool-${key}`;
    case 'adapter':
      return `adapter-${key}`;
    case 'module':
      return `module-${key}`;
    case 'stage':
      return `stage-${key}`;
  }
}
