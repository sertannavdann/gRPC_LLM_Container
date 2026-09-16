'use client';

/**
 * Pure layout builder extracted from page.tsx's former rebuild effect
 * (09-07 Task 1). Produces the exact same node/edge shapes and byte-equivalent
 * positioning math the page rendered before this plan — the UI-SPEC's Visual
 * Regression Lock is binding here.
 *
 * `buildCanvasGraph` is called from two places in the rewired page:
 *   - the SSE ingestion effect, to recompute topology and hand `layout` to
 *     `syncFromPipeline` (plan 04's `toEntityRecords` consumes it to seed new
 *     ECS entities' default x/y);
 *   - nowhere else — the `[version]`-keyed patch effect never calls this, it
 *     only patches mirrored fields onto the existing buffered `nodes` array.
 */

import type { Node, Edge } from '@xyflow/react';
import type { StageNodeData } from '@/components/pipeline/StageNode';
import type { ModuleNodeData } from '@/components/pipeline/ModuleNode';
import type { PipelineState } from '@/lib/adminClient';
import { STAGE_NODE_IDS } from '@/machines/pipelinePage';

// ── Static pipeline stages (Row 0) ──
// Ids MUST match STAGE_NODE_IDS (imported, not redefined) — the
// `pipelineNodeIds`/`clearSelectionIfMissing` guard in pipelinePage.ts relies
// on this constant being the single source of truth for stage ids.
export const STAGE_NODES: Node[] = [
  { id: STAGE_NODE_IDS[0], type: 'stage', position: { x: 60, y: 50 }, data: { label: 'Intent Detection', description: 'Pattern matching + NLU' } satisfies StageNodeData },
  { id: STAGE_NODE_IDS[1], type: 'stage', position: { x: 300, y: 50 }, data: { label: 'LIDM Routing', description: 'Tier selection & delegation' } satisfies StageNodeData },
  { id: STAGE_NODE_IDS[2], type: 'stage', position: { x: 540, y: 50 }, data: { label: 'Tool Execution', description: 'Function calls & RAG' } satisfies StageNodeData },
  { id: STAGE_NODE_IDS[3], type: 'stage', position: { x: 780, y: 50 }, data: { label: 'Synthesis', description: 'Response generation' } satisfies StageNodeData },
];

export const STAGE_EDGES: Edge[] = [
  { id: 'e-s1-s2', source: STAGE_NODE_IDS[0], target: STAGE_NODE_IDS[1], animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
  { id: 'e-s2-s3', source: STAGE_NODE_IDS[1], target: STAGE_NODE_IDS[2], animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
  { id: 'e-s3-s4', source: STAGE_NODE_IDS[2], target: STAGE_NODE_IDS[3], animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
];

// Edge style helpers
export const stageToToolEdge = (source: string, target: string): Edge => ({
  id: `e-${source}-${target}`,
  source,
  sourceHandle: 'bottom',
  target,
  style: { stroke: '#f59e0b', strokeWidth: 1.5, strokeDasharray: '6 3' },
});

export const stateEdgeColor: Record<string, string> = {
  running: '#22c55e',
  error: '#ef4444',
  disabled: '#71717a',
};

export const toolToAdapterEdge = (source: string, target: string, state: string): Edge => ({
  id: `e-${source}-${target}`,
  source,
  target,
  style: { stroke: stateEdgeColor[state] ?? '#71717a', strokeWidth: 1.5 },
});

export interface CanvasGraphResult {
  nodes: Node[];
  edges: Edge[];
  layout: Map<string, { x: number; y: number }>;
}

/**
 * Pure builder: `pipeline === null` yields just the static stage scaffolding.
 * When `positions` supplies an entry for a node id, that position WINS over
 * the freshly-computed layout — this is how a user's dragged position (held
 * on the live ECS entity's x/y) survives a topology rebuild.
 */
export function buildCanvasGraph(
  pipeline: PipelineState | null,
  positions?: Map<string, { x: number; y: number }>,
): CanvasGraphResult {
  const layout = new Map<string, { x: number; y: number }>();
  for (const n of STAGE_NODES) layout.set(n.id, { x: n.position.x, y: n.position.y });

  if (!pipeline) {
    return { nodes: [...STAGE_NODES], edges: [...STAGE_EDGES], layout };
  }

  const resolvePos = (id: string, computed: { x: number; y: number }): { x: number; y: number } => {
    const override = positions?.get(id);
    const pos = override ?? computed;
    layout.set(id, pos);
    return pos;
  };

  const dynamicNodes: Node[] = [...STAGE_NODES];
  const dynamicEdges: Edge[] = [...STAGE_EDGES];

  // ── Row -1: Service nodes (y=-80, above stages) ──
  const services = Object.values(pipeline.services);
  services.forEach((svc, i) => {
    const id = `svc-${svc.name}`;
    const pos = resolvePos(id, { x: 60 + i * 220, y: -80 });
    dynamicNodes.push({
      id,
      type: 'service',
      position: pos,
      data: { label: svc.name, state: svc.state, latency_ms: svc.latency_ms },
    });
    if (i === 0) {
      dynamicEdges.push({
        id: `e-${id}-intent`,
        source: id,
        target: STAGE_NODE_IDS[0],
        style: { stroke: '#71717a' },
      });
    }
  });

  // ── Row 1: Tool nodes (y=230) ──
  const tools = pipeline.tools ?? [];
  // Group tools by stage for positioning
  const toolsByStage: Record<string, typeof tools> = {};
  tools.forEach((t) => {
    const stage = t.stage ?? 'tools';
    if (!toolsByStage[stage]) toolsByStage[stage] = [];
    toolsByStage[stage].push(t);
  });

  // Stage x-positions for aligning tools beneath
  const stageX: Record<string, number> = {
    intent: 60,
    routing: 300,
    tools: 540,
    synth: 780,
  };

  Object.entries(toolsByStage).forEach(([stage, stageTools]) => {
    const baseX = stageX[stage] ?? 540;
    const totalWidth = stageTools.length * 170;
    const startX = baseX - totalWidth / 2 + 85;

    stageTools.forEach((tool, i) => {
      const toolId = `tool-${tool.name}`;
      const pos = resolvePos(toolId, { x: startX + i * 170, y: 230 });
      dynamicNodes.push({
        id: toolId,
        type: 'tool',
        position: pos,
        data: {
          label: tool.name,
          connectedAdapters: tool.connected_adapters ?? [],
          stage,
        },
      });

      // Stage → Tool edge
      const stageNodeId = `stage-${stage}`;
      dynamicEdges.push(stageToToolEdge(stageNodeId, toolId));
    });
  });

  // ── Row 2: Adapter nodes (y=420) ──
  const adapters = pipeline.adapters ?? [];
  // Track adapter positions to avoid overlap
  const adapterPositions: Map<string, { x: number; y: number }> = new Map();
  let adapterX = 0;

  // First, compute x-positions per tool based on their connected adapters
  tools.forEach((tool) => {
    const connectedAdapters = tool.connected_adapters ?? [];
    if (connectedAdapters.length === 0) return;

    // Find tool node position
    const toolId = `tool-${tool.name}`;
    const toolNode = dynamicNodes.find((n) => n.id === toolId);
    if (!toolNode) return;

    const toolBaseX = toolNode.position.x;
    const totalWidth = connectedAdapters.length * 160;
    const startX = toolBaseX - totalWidth / 2 + 80;

    connectedAdapters.forEach((adapterId, i) => {
      if (!adapterPositions.has(adapterId)) {
        adapterPositions.set(adapterId, { x: startX + i * 160, y: 420 });
      }
    });
  });

  // Add any unconnected adapters at the end
  adapters.forEach((adapter) => {
    if (!adapterPositions.has(adapter.id)) {
      adapterPositions.set(adapter.id, { x: adapterX, y: 420 });
      adapterX += 160;
    }
  });

  adapters.forEach((adapter) => {
    const adapterId = `adapter-${adapter.id}`;
    const computed = adapterPositions.get(adapter.id) ?? { x: 0, y: 420 };
    const pos = resolvePos(adapterId, computed);
    const locked = adapter.requires_auth && !adapter.has_credentials;

    dynamicNodes.push({
      id: adapterId,
      type: 'adapter',
      position: pos,
      data: {
        label: adapter.name,
        adapterId: adapter.id,
        category: adapter.category,
        platform: adapter.platform,
        state: adapter.state,
        requiresAuth: adapter.requires_auth,
        hasCredentials: adapter.has_credentials,
      },
    });

    // Tool → Adapter edges
    tools.forEach((tool) => {
      if (tool.connected_adapters?.includes(adapter.id)) {
        dynamicEdges.push(
          toolToAdapterEdge(
            `tool-${tool.name}`,
            adapterId,
            locked ? 'disabled' : adapter.state,
          ),
        );
      }
    });
  });

  // ── Row 3: Module nodes (y=600, below adapters) ──
  // Pending-approval modules sort first (leftmost) — UI-SPEC's focal-point rule.
  const modules = pipeline.modules ?? [];
  const sortedModules = [...modules].sort((a, b) => {
    const aPending = a.pending_approval ? 0 : 1;
    const bPending = b.pending_approval ? 0 : 1;
    return aPending - bPending;
  });
  const moduleAnchorId = dynamicNodes.some((n) => n.id === 'tool-module_installer')
    ? 'tool-module_installer'
    : STAGE_NODE_IDS[2];

  sortedModules.forEach((m, i) => {
    const moduleNodeId = `module-${m.id}`;
    const pos = resolvePos(moduleNodeId, { x: i * 190, y: 600 });
    dynamicNodes.push({
      id: moduleNodeId,
      type: 'module',
      position: pos,
      data: {
        label: m.name,
        category: m.category ?? '',
        state: m.state,
        moduleId: m.id,
        pendingApproval: m.pending_approval ?? false,
        status: m.status,
        buildStage: m.build_stage,
      } satisfies ModuleNodeData,
    });

    dynamicEdges.push(toolToAdapterEdge(moduleAnchorId, moduleNodeId, m.state));
  });

  return { nodes: dynamicNodes, edges: dynamicEdges, layout };
}
