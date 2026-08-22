// Shared, fixed graph topology used identically by BOTH implementations
// (ecs-system and adhoc-react) so the comparison is apples-to-apples.
export type NodeSpec = { id: string; label: string; position: { x: number; y: number }; connections: string[] };

export const TOPOLOGY: NodeSpec[] = [
  { id: "orchestrator", label: "Orchestrator", position: { x: 0, y: 0 }, connections: ["dashboard", "sandbox"] },
  { id: "dashboard", label: "Dashboard", position: { x: 280, y: -160 }, connections: [] },
  { id: "sandbox", label: "Sandbox", position: { x: 280, y: 160 }, connections: [] },
  { id: "module-0", label: "module-0", position: { x: 560, y: -240 }, connections: ["sandbox"] },
  { id: "module-1", label: "module-1", position: { x: 560, y: -80 }, connections: ["sandbox"] },
  { id: "module-2", label: "module-2", position: { x: 560, y: 80 }, connections: ["sandbox"] },
  { id: "module-3", label: "module-3", position: { x: 560, y: 240 }, connections: ["sandbox"] },
];

export function buildEdgePairs(): Array<[string, string]> {
  const pairs: Array<[string, string]> = [];
  for (const n of TOPOLOGY) for (const target of n.connections) pairs.push([n.id, target]);
  return pairs;
}
