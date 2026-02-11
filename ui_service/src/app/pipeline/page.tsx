/**
 * Pipeline Page
 *
 * React Flow visualization of the NEXUS decision pipeline.
 * SSE-driven live state, custom service/module/stage nodes.
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

import { ServiceNode, type ServiceNodeData } from '@/components/pipeline/ServiceNode';
import { ModuleNode, type ModuleNodeData } from '@/components/pipeline/ModuleNode';
import { StageNode, type StageNodeData } from '@/components/pipeline/StageNode';
import { useNexusStore } from '@/store/nexusStore';

// ── Node types ──
const nodeTypes = {
  service: ServiceNode,
  module: ModuleNode,
  stage: StageNode,
};

// ── Static pipeline stages ──
const STAGE_NODES: Node[] = [
  { id: 'stage-intent', type: 'stage', position: { x: 60, y: 200 }, data: { label: 'Intent Detection', description: 'Pattern matching + NLU' } satisfies StageNodeData },
  { id: 'stage-routing', type: 'stage', position: { x: 300, y: 200 }, data: { label: 'LIDM Routing', description: 'Tier selection & delegation' } satisfies StageNodeData },
  { id: 'stage-tools', type: 'stage', position: { x: 540, y: 200 }, data: { label: 'Tool Execution', description: 'Function calls & RAG' } satisfies StageNodeData },
  { id: 'stage-synth', type: 'stage', position: { x: 780, y: 200 }, data: { label: 'Synthesis', description: 'Response generation' } satisfies StageNodeData },
];

const STAGE_EDGES: Edge[] = [
  { id: 'e-s1-s2', source: 'stage-intent', target: 'stage-routing', animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
  { id: 'e-s2-s3', source: 'stage-routing', target: 'stage-tools', animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
  { id: 'e-s3-s4', source: 'stage-tools', target: 'stage-synth', animated: true, style: { stroke: '#f97316', strokeWidth: 2 } },
];

export default function PipelinePage() {
  const { pipeline, connected, startSSE, stopSSE, fetchModules, enableModule, disableModule } = useNexusStore();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([...STAGE_NODES]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([...STAGE_EDGES]);

  // Start SSE on mount
  useEffect(() => {
    startSSE();
    fetchModules();
    return () => stopSSE();
  }, [startSSE, stopSSE, fetchModules]);

  // Module toggle handler
  const handleModuleToggle = useCallback(
    (moduleId: string, enable: boolean) => {
      const [cat, plat] = moduleId.split('/');
      if (enable) enableModule(cat, plat);
      else disableModule(cat, plat);
    },
    [enableModule, disableModule],
  );

  // Rebuild nodes when pipeline state updates
  useEffect(() => {
    if (!pipeline) return;

    const dynamicNodes: Node[] = [...STAGE_NODES];
    const dynamicEdges: Edge[] = [...STAGE_EDGES];

    // Service nodes (above pipeline)
    const services = Object.values(pipeline.services);
    services.forEach((svc, i) => {
      const id = `svc-${svc.name}`;
      dynamicNodes.push({
        id,
        type: 'service',
        position: { x: 60 + i * 220, y: 30 },
        data: { label: svc.name, state: svc.state, latency_ms: svc.latency_ms } satisfies ServiceNodeData,
      });
      // Connect first service to intent stage
      if (i === 0) {
        dynamicEdges.push({ id: `e-${id}-intent`, source: id, target: 'stage-intent', style: { stroke: '#71717a' } });
      }
    });

    // Module nodes (below pipeline)
    pipeline.modules.forEach((mod, i) => {
      const id = `mod-${mod.id}`;
      dynamicNodes.push({
        id,
        type: 'module',
        position: { x: 60 + i * 220, y: 380 },
        data: {
          label: mod.name,
          category: mod.category ?? 'unknown',
          state: mod.state,
          moduleId: mod.id,
          onToggle: handleModuleToggle,
        } satisfies ModuleNodeData,
      });
      // Connect modules to tool stage
      dynamicEdges.push({ id: `e-${id}-tools`, source: id, target: 'stage-tools', style: { stroke: '#3b82f6', strokeDasharray: '5 3' } });
    });

    setNodes(dynamicNodes);
    setEdges(dynamicEdges);
  }, [pipeline, handleModuleToggle, setNodes, setEdges]);

  const ago = useMemo(() => {
    if (!pipeline?.timestamp) return '';
    return `${Math.round((Date.now() / 1000 - pipeline.timestamp))}s ago`;
  }, [pipeline?.timestamp]);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/60 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Zap className="w-4 h-4 text-orange-400" />
          <span className="text-sm font-medium text-zinc-100">Decision Pipeline</span>
          {pipeline && (
            <span className="text-xs text-zinc-500">
              {Object.keys(pipeline.services).length} services
              {pipeline.modules.length > 0 && ` · ${pipeline.modules.length} modules`}
              {pipeline.adapters_count > 0 && ` · ${pipeline.adapters_count} adapters`}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {ago && <span className="text-[11px] text-zinc-500">{ago}</span>}
          <span className="flex items-center gap-1.5 text-xs">
            {connected
              ? <><Wifi className="w-3.5 h-3.5 text-green-400" /><span className="text-green-400">Live</span></>
              : <><WifiOff className="w-3.5 h-3.5 text-red-400" /><span className="text-red-400">Disconnected</span></>}
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
              if (n.type === 'module') return '#3b82f6';
              return '#f97316';
            }}
            className="!bg-zinc-900 !border-zinc-700"
            maskColor="rgba(0,0,0,0.7)"
          />
        </ReactFlow>
      </div>
    </div>
  );
}
