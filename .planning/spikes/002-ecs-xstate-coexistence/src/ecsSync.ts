import { world, touch, byId, type PipelineEntity } from "./ecs";
import type { PipelineSnapshot } from "./pipelineMachine";

// Deterministic layout so entities don't jump around when re-added.
const LAYOUT: Record<string, { x: number; y: number }> = {
  orchestrator: { x: 0, y: 0 },
  dashboard: { x: 280, y: -140 },
  sandbox: { x: 280, y: 140 },
  "module-0": { x: 560, y: -200 },
  "module-1": { x: 560, y: -60 },
  "module-2": { x: 560, y: 80 },
};

/**
 * The ONE place allowed to add/remove entities or write mirrored fields.
 * Called every time the XState actor's snapshot changes. Must never touch
 * ECS-only components (hovered, dragCount) on entities that already exist —
 * that's the whole point of the coexistence test: two owners, one each for
 * a disjoint set of fields on the same entity.
 */
export function syncFromPipeline(pipeline: PipelineSnapshot | null, log: (msg: string) => void) {
  if (!pipeline) return;
  const incomingIds = new Set(pipeline.nodes.map((n) => n.id));

  // Remove entities no longer present in the snapshot.
  for (const entity of [...world.entities]) {
    if (!incomingIds.has(entity.id)) {
      log(`sync: removing ${entity.id} (dropped from SSE snapshot)`);
      world.remove(entity);
    }
  }

  // Add or patch entities from the snapshot.
  for (const n of pipeline.nodes) {
    const existing = byId(n.id);
    if (existing) {
      // Patch ONLY mirrored fields. hovered/dragCount are untouched.
      existing.label = n.label;
      existing.status = n.status;
    } else {
      const entity: PipelineEntity = {
        id: n.id,
        label: n.label,
        status: n.status,
        position: LAYOUT[n.id] ?? { x: Math.random() * 500, y: Math.random() * 400 },
        hovered: false,
        dragCount: 0,
      };
      world.add(entity);
      log(`sync: adding ${n.id} (new in SSE snapshot)`);
    }
  }

  touch();
}
