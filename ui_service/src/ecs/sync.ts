'use client';

/**
 * The ONE writer for SSE-derived ECS state (Phase 9, ported from spike 007's
 * `syncFromPipeline` — .planning/spikes/007-llm-writes-world/mediation.mjs
 * lines 77-95).
 *
 * This is the ONLY function permitted to add/remove entities or write
 * mirrored fields in reaction to SSE data. Never call the world's add/remove
 * choke points directly from anywhere else in reaction to SSE snapshots
 * — the mediation layer (mediation.ts) is the second writer, and it only
 * touches the live world through an explicit human approval action.
 *
 * Must be called from a `useEffect` keyed on `state.context.pipeline` (the
 * XState machine's SSE-derived context field, replaced only on genuine new
 * data) rather than a raw `useEffect([])` — 09-RESEARCH.md Pitfall 2,
 * StrictMode double-invocation.
 *
 * Known deferred gap (09-RESEARCH.md Pitfall 4): a transient SSE drop
 * produces remove-then-re-add and silently resets ECS-only fields.
 * CONTEXT.md defers the grace period for that to production telemetry — do
 * not build one speculatively here.
 */

import type { PipelineState } from '@/lib/adminClient';
import type { EntityRecord } from './types';
import { entityIdFor } from './types';
import { canvasWorld, touch, type createPipelineWorld } from './world';
import { canvasMediation, type createMediation } from './mediation';

export interface Layout {
  x: number;
  y: number;
}

const MIRRORED_FIELDS: (keyof EntityRecord)[] = [
  'label',
  'status',
  'lifecycle',
  'detail',
  'latency',
  'creds',
  'flags',
];

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

function fieldsDiffer(existing: EntityRecord, incoming: EntityRecord, field: keyof EntityRecord): boolean {
  const a = existing[field];
  const b = incoming[field];
  if (Array.isArray(a) && Array.isArray(b)) return !arraysEqual(a, b);
  return a !== b;
}

/**
 * The browser twin of plan 02's Python `pipeline_state_to_views` —
 * dashboard_service/canvas_context.py. Must produce the SAME ids and the
 * SAME field mapping; any divergence is a defect.
 */
export function toEntityRecords(
  pipeline: PipelineState,
  layout: Map<string, Layout>
): EntityRecord[] {
  const records: EntityRecord[] = [];

  const posFor = (id: string): Layout => layout.get(id) ?? { x: 0, y: 0 };

  try {
    const services = pipeline.services ?? {};
    for (const [name, svc] of Object.entries(services)) {
      const id = entityIdFor('service', name);
      const pos = posFor(id);
      records.push({
        id,
        label: name,
        kind: 'service',
        status: (svc?.state as EntityRecord['status']) ?? 'unknown',
        lifecycle: null,
        detail: null,
        latency: svc?.latency_ms != null ? Math.round(svc.latency_ms) : null,
        creds: [],
        flags: [],
        x: pos.x,
        y: pos.y,
      });
    }
  } catch {
    // degrade gracefully — one bad source collection must not break the rest
  }

  try {
    const modules = pipeline.modules ?? [];
    for (const m of modules) {
      const id = entityIdFor('module', m.id);
      const pos = posFor(id);
      const flags: string[] = [];
      if (m.pending_approval) flags.push('pending_approval');
      records.push({
        id,
        label: m.name ?? 'unknown',
        kind: 'module',
        status: (m.state as EntityRecord['status']) ?? 'unknown',
        lifecycle: (m.status as EntityRecord['lifecycle']) ?? null,
        detail: m.build_stage ?? null,
        latency: null,
        creds: [],
        flags,
        x: pos.x,
        y: pos.y,
      });
    }
  } catch {
    // degrade gracefully
  }

  try {
    const adapters = pipeline.adapters ?? [];
    for (const a of adapters) {
      const id = entityIdFor('adapter', a.id);
      const pos = posFor(id);
      const flags: string[] = [];
      if (a.requires_auth) {
        flags.push('auth_required');
        if (!a.has_credentials) flags.push('no_credentials');
      }
      records.push({
        id,
        label: a.name ?? 'unknown',
        kind: 'adapter',
        status: (a.state as EntityRecord['status']) ?? 'unknown',
        lifecycle: null,
        detail: `${a.category}/${a.platform}`,
        latency: null,
        creds: [],
        flags,
        x: pos.x,
        y: pos.y,
      });
    }
  } catch {
    // degrade gracefully
  }

  try {
    const tools = pipeline.tools ?? [];
    for (const t of tools) {
      const id = entityIdFor('tool', t.name);
      const pos = posFor(id);
      const connected = [...(t.connected_adapters ?? [])].sort();
      const flags = connected.map((a) => `adapter:${a}`);
      records.push({
        id,
        label: t.name ?? 'unknown',
        kind: 'tool',
        status: 'available',
        lifecycle: null,
        detail: t.stage ?? null,
        latency: null,
        creds: [],
        flags,
        x: pos.x,
        y: pos.y,
      });
    }
  } catch {
    // degrade gracefully
  }

  try {
    const stageTools = pipeline.stage_tools ?? {};
    for (const key of Object.keys(stageTools)) {
      const id = entityIdFor('stage', key);
      const pos = posFor(id);
      records.push({
        id,
        label: key,
        kind: 'stage',
        status: 'unknown',
        lifecycle: null,
        detail: null,
        latency: null,
        creds: [],
        flags: [],
        x: pos.x,
        y: pos.y,
      });
    }
  } catch {
    // degrade gracefully
  }

  return records;
}

type World = ReturnType<typeof createPipelineWorld>;
type Mediation = ReturnType<typeof createMediation>;

/**
 * The testable core of the sync writer. Ported from mediation.mjs lines
 * 77-95: removals, then mirrored-field patches / adds, then proposal
 * re-validation in the SAME transition, then a single notify call.
 */
export function syncRecords(w: World, m: Mediation, records: EntityRecord[]): void {
  const incoming = new Set(records.map((r) => r.id));

  for (const entity of [...w.world.entities]) {
    if (!incoming.has(entity.id)) w.removeById(entity.id);
  }

  for (const rec of records) {
    const existing = w.byId.get(rec.id);
    if (existing) {
      const patch: Partial<EntityRecord> = {};
      for (const field of MIRRORED_FIELDS) {
        if (fieldsDiffer(existing, rec, field)) {
          (patch as Record<string, unknown>)[field] = rec[field];
        }
      }
      if (Object.keys(patch).length > 0) w.mutate(rec.id, patch);
    } else {
      w.add(rec);
    }
  }

  // Re-validation point 2 of 3: in the SAME transition that performed the
  // removals above (the clearSelectionIfMissing pattern generalized).
  m.revalidateStagedProposals();

  touch();
}

export function syncFromPipeline(pipeline: PipelineState, layout: Map<string, Layout>): void {
  syncRecords(canvasWorld, canvasMediation, toEntityRecords(pipeline, layout));
}
