/**
 * Pipeline Page — Hierarchical Tree
 *
 * Three-tier React Flow visualization of the NEXUS decision pipeline:
 *   Row 0: Pipeline stages (Intent → Routing → Tools → Synthesis)
 *   Row 1: Tools connected to stages
 *   Row 2: Adapters connected to tools
 *
 * SSE-driven live state with interactive node detail panel.
 */
'use client';

import React, { useCallback, useEffect, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Zap, RefreshCw, Wifi, WifiOff } from 'lucide-react';

import { ServiceNode } from '@/components/pipeline/ServiceNode';
import { StageNode, type StageNodeData } from '@/components/pipeline/StageNode';
import { ToolNode } from '@/components/pipeline/ToolNode';
import { AdapterNode } from '@/components/pipeline/AdapterNode';
import { NodeDetailPanel } from '@/components/pipeline/NodeDetailPanel';
import { useNexusStore } from '@/store/nexusStore';

// ── Node types ──
const nodeTypes = {
  service: ServiceNode,
  stage: StageNode,
  tool: ToolNode,
  adapter: AdapterNode,
};

// ── Static pipeline stages (Row 0) ──
const STAGE_NODES: Node[] = [
  { id: 'stage-intent', type: 'stage', position: { x: 60, y: 50 }, data: { label: 'Intent Detection', description: 'Pattern matching + NLU' } satisfies StageNodeData },
  { id: 'stage-routing', type: 'stage', position: { x: 300, y: 50 }, data: { label: 'LIDM Routing', description: 'Tier selection & delegation' } satisfies StageNodeData },
  { id: 'stage-tools', type: 'stage', position: { x: 540, y: 50 }, data: { label: 'Tool Execution', description: 'Function calls & RAG' } satisfies StageNodeData },
  { id: 'stage-synth', type: 'stage', position: { x: 780, y: 50 }, data: { label: 'Synthesis', description: 'Response generation' } satisfies StageNodeData },
];

const STAGE_EDGES: Edge[] = [
  { id: 'e-s1-s2', source: 'stage-intent', target: 'stage-routing', animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
  { id: 'e-s2-s3', source: 'stage-routing', target: 'stage-tools', animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
  { id: 'e-s3-s4', source: 'stage-tools', target: 'stage-synth', animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
];

// Edge style helpers
const stageToToolEdge = (source: string, target: string): Edge => ({
  id: `e-${source}-${target}`,
  source,
  sourceHandle: 'bottom',
  target,
  style: { stroke: '#f59e0b', strokeWidth: 1.5, strokeDasharray: '6 3' },
});

const stateEdgeColor: Record<string, string> = {
  running: '#22c55e',
  error: '#ef4444',
  disabled: '#71717a',
};

const toolToAdapterEdge = (source: string, target: string, state: string): Edge => ({
  id: `e-${source}-${target}`,
  source,
  target,
  style: { stroke: stateEdgeColor[state] ?? '#71717a', strokeWidth: 1.5 },
});

export default function PipelinePage() {
  const {
    pipeline,
    connected,
    startSSE,
    stopSSE,
    fetchModules,
    selectedNode,
    selectNode,
    testRunning,
    testResult,
    runModuleTests,
  } = useNexusStore();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([...STAGE_NODES]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([...STAGE_EDGES]);

  // Start SSE on mount
  useEffect(() => {
    startSSE();
    fetchModules();
    return () => stopSSE();
  }, [startSSE, stopSSE, fetchModules]);

  // Node click handler
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      selectNode({
        type: node.type ?? 'stage',
        id: node.id,
        data: node.data as Record<string, unknown>,
      });
    },
    [selectNode],
  );

  // Rebuild nodes when pipeline state updates
  useEffect(() => {
    if (!pipeline) return;

    const dynamicNodes: Node[] = [...STAGE_NODES];
    const dynamicEdges: Edge[] = [...STAGE_EDGES];

    // ── Row -1: Service nodes (y=-80, above stages) ──
    const services = Object.values(pipeline.services);
    services.forEach((svc, i) => {
      const id = `svc-${svc.name}`;
      dynamicNodes.push({
        id,
        type: 'service',
        position: { x: 60 + i * 220, y: -80 },
        data: { label: svc.name, state: svc.state, latency_ms: svc.latency_ms },
      });
      if (i === 0) {
        dynamicEdges.push({
          id: `e-${id}-intent`,
          source: id,
          target: 'stage-intent',
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
        dynamicNodes.push({
          id: toolId,
          type: 'tool',
          position: { x: startX + i * 170, y: 230 },
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
      const pos = adapterPositions.get(adapter.id) ?? { x: 0, y: 420 };
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

    setNodes(dynamicNodes);
    setEdges(dynamicEdges);
  }, [pipeline, setNodes, setEdges]);

  const ago = useMemo(() => {
    if (!pipeline?.timestamp) return '';
    return `${Math.round((Date.now() / 1000 - pipeline.timestamp))}s ago`;
  }, [pipeline?.timestamp]);

  const handleRunTests = useCallback(
    (category: string, platform: string) => {
      runModuleTests(category, platform);
    },
    [runModuleTests],
  );

  return (
    <div className="flex flex-col h-full relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/60 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Zap className="w-4 h-4 text-orange-400" />
          <span className="text-sm font-medium text-zinc-100">Decision Pipeline</span>
          {pipeline && (
            <span className="text-xs text-zinc-500">
              {Object.keys(pipeline.services).length} services
              {(pipeline.tools?.length ?? 0) > 0 && ` · ${pipeline.tools.length} tools`}
              {(pipeline.adapters?.length ?? 0) > 0 && ` · ${pipeline.adapters.length} adapters`}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {ago && <span className="text-[11px] text-zinc-500">{ago}</span>}
          <span className="flex items-center gap-1.5 text-xs">
            {connected ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-green-400" />
                <span className="text-green-400">Live</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-red-400" />
                <span className="text-red-400">Disconnected</span>
              </>
            )}
          </span>
          <button
            onClick={() => fetchModules()}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Refresh modules"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* React Flow canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
          className="bg-background"
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#27272a" />
          <Controls className="!bg-zinc-800 !border-zinc-700 !text-zinc-300 [&>button]:!bg-zinc-800 [&>button]:!border-zinc-700 [&>button]:!text-zinc-300 [&>button:hover]:!bg-zinc-700" />
          <MiniMap
            nodeColor={(n) => {
              if (n.type === 'service') return '#22c55e';
              if (n.type === 'tool') return '#f59e0b';
              if (n.type === 'adapter') return '#3b82f6';
              return '#f97316';
            }}
            className="!bg-zinc-900 !border-zinc-700"
            maskColor="rgba(0,0,0,0.7)"
          />
        </ReactFlow>
      </div>

      {/* Node detail panel */}
      <NodeDetailPanel
        node={selectedNode}
        onClose={() => selectNode(null)}
        testRunning={testRunning}
        testResult={testResult}
        onRunTests={handleRunTests}
      />
    </div>
  );
}
