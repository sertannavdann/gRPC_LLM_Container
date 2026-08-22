// --- Implementation B: plain React, NEXUS's actual current idiom ---
// Matches the pattern already used in ui_service (e.g. ModuleNode.tsx's
// resolveLifecycle(): a pure function deriving state from data, called from
// a memoized selector — no ECS, no "system," no world object.
import { TOPOLOGY } from "./topology";

/** Pure derivation, same shape as ModuleNode.tsx's resolveLifecycle(). */
export function computeHighlighted(hoveredId: string | null): Set<string> {
  if (!hoveredId) return new Set();
  const hovered = TOPOLOGY.find((n) => n.id === hoveredId);
  if (!hovered) return new Set();
  const ids = new Set<string>([hovered.id, ...hovered.connections]);
  for (const n of TOPOLOGY) {
    if (n.connections.includes(hovered.id)) ids.add(n.id);
  }
  return ids;
}
