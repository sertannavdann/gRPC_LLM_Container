// FROZEN 2026-09-18: removed from the navbar, reachable by URL (/pipeline) only.
// Phase 9 (ECS context canvas) stopped at plan 09-09; 09-10 was not executed.
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

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useSyncExternalStore } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeChange,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useMachine } from '@xstate/react';
import { Zap, RefreshCw, Wifi, WifiOff } from 'lucide-react';

import { ServiceNode } from '@/components/pipeline/ServiceNode';
import { StageNode } from '@/components/pipeline/StageNode';
import { ToolNode } from '@/components/pipeline/ToolNode';
import { AdapterNode } from '@/components/pipeline/AdapterNode';
import { ModuleNode, type ModuleNodeData } from '@/components/pipeline/ModuleNode';
import { NodeDetailPanel } from '@/components/pipeline/NodeDetailPanel';
import { RewindToast } from '@/components/pipeline/RewindToast';
import type { SelectedNode } from '@/store/nexusStore';
import { useNexusStore } from '@/store/nexusStore';
import { pipelinePageMachine } from '@/machines/pipelinePage';
import { buildCanvasGraph, STAGE_NODES, STAGE_EDGES } from './canvasGraph';
import { subscribeWorld, getWorldVersion, canvasWorld } from '@/ecs/world';
import { syncFromPipeline } from '@/ecs/sync';
import { canvasMediation } from '@/ecs/mediation';
import { proposalAnnotations, pendingConfirmations, type ProposalAnnotation } from '@/ecs/preview';
import '@/ecs/ingress';
import type { EntityRecord } from '@/ecs/types';

// Same "{field} → {value}" derivation preview.ts already uses for node-level
// delta lines — reused here (not re-implemented) for the panel's row list so
// the two surfaces can never drift in format.
function opRow(op: import('@/ecs/mediation').MutationOpT): { field: string; value: string } | null {
  if (op.op === 'set_status') return { field: 'status', value: op.value };
  if (op.op === 'set_credentials') return { field: 'credentials', value: `${op.list.length} items` };
  if (op.op === 'move') return { field: 'position', value: `(${op.x}, ${op.y})` };
  if (op.op === 'add_module') return { field: 'add_module', value: op.rec.label };
  if (op.op === 'remove_module') return { field: 'remove_module', value: op.id };
  return null;
}

// ── Node types ──
const nodeTypes = {
  service: ServiceNode,
  stage: StageNode,
  tool: ToolNode,
  adapter: AdapterNode,
  module: ModuleNode,
};

// Mirrored fields a rendered node's `data` carries — must stay in sync with
// ecs/sync.ts's MIRRORED_FIELDS so the patch effect below only rewrites data
// that actually changed.
function dataFromEntity(nodeType: string | undefined, entity: EntityRecord): Record<string, unknown> | null {
  switch (nodeType) {
    case 'service':
      return { label: entity.label, state: entity.status, latency_ms: entity.latency };
    case 'tool':
      return { label: entity.label, connectedAdapters: entity.flags.map((f) => f.replace(/^adapter:/, '')) };
    case 'adapter':
      return {
        label: entity.label,
        state: entity.status,
        requiresAuth: entity.flags.includes('auth_required'),
        hasCredentials: !entity.flags.includes('no_credentials'),
      };
    case 'module':
      return {
        label: entity.label,
        state: entity.status,
        status: entity.lifecycle,
        buildStage: entity.detail,
        pendingApproval: entity.flags.includes('pending_approval'),
      };
    default:
      return null;
  }
}

// Compare ProposalAnnotations by value, not object identity, per plan 08's
// early-return-identical-reference requirement — a node whose annotation is
// unchanged (even though `proposalAnnotations()` returns a fresh Map/object
// every call) must still return the SAME node reference.
function annotationKey(ann: ProposalAnnotation | undefined): string {
  if (!ann) return '';
  return `${ann.proposalId}|${ann.kind}|${ann.deltaLines.join('|')}`;
}

export default function PipelinePage() {
  const { fetchModules, testRunning, testResult, runModuleTests } = useNexusStore();

  // Page state (SSE connection, node selection, review panel) is machine-driven
  // (D-14) — exactly one EventSource is owned by the machine's sseConnection actor.
  const [state, send] = useMachine(pipelinePageMachine);
  const pipeline = state.context.pipeline;
  const connected = state.matches({ connection: 'connected' });

  // Explicit `matches` derivation (preferred over casting `state.value`) for the
  // reviewPanel region's current substate — drives NodeDetailPanel's review UI.
  const reviewState = state.matches({ reviewPanel: 'loading' })
    ? 'loading'
    : state.matches({ reviewPanel: 'open' })
      ? 'open'
      : state.matches({ reviewPanel: 'approving' }) || state.matches({ reviewPanel: 'approvingChange' })
        ? 'approving'
        : state.matches({ reviewPanel: 'rejecting' }) || state.matches({ reviewPanel: 'rejectingChange' })
          ? 'rejecting'
          : state.matches({ reviewPanel: 'error' })
            ? 'error'
            : 'closed';

  const [nodes, setNodes, onNodesChangeRF] = useNodesState<Node>([...STAGE_NODES]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([...STAGE_EDGES]);

  // Subscribe to the ECS world's touch() bridge (world.ts) — the server
  // snapshot arg (3rd) prevents a Next.js App Router SSR/hydration mismatch
  // throw, since the world is a module-scope singleton with no server twin.
  const version = useSyncExternalStore(subscribeWorld, getWorldVersion, getWorldVersion);

  // Tracks the node id currently mid-drag so the drag-stop write-back below
  // only ever touches the one entity that actually moved (skill blueprint's
  // What-to-Avoid: never tag the whole array as user-touched).
  const draggingId = useRef<string | null>(null);

  // Populate the admin module list (module enable/disable actions) on mount.
  // SSE transport itself is owned by pipelinePageMachine's connection region.
  useEffect(() => {
    fetchModules();
  }, [fetchModules]);

  // Remembers the most recent canvas-op proposal id opened for a given node,
  // even after it moves from `staged` to `approved` — `proposalAnnotations()`
  // only annotates STAGED proposals (D9-08), so a node's live badge vanishes
  // the instant it's approved. Without this, "reject an already-applied
  // proposal" (a locked must-have truth) would be unreachable by clicking the
  // node a second time, since `node.data.proposal` would already be gone.
  const lastProposalByNodeRef = useRef<Map<string, string>>(new Map());

  // Node click handler — routes through the machine so the reviewPanel region's
  // hasModuleId guard can open review mode only for module nodes.
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const proposal = (node.data as ModuleNodeData | undefined)?.proposal as
        | ProposalAnnotation
        | undefined;
      if (proposal) {
        lastProposalByNodeRef.current.set(node.id, proposal.proposalId);
        send({ type: 'CANVAS_PROPOSAL', proposalId: proposal.proposalId, nodeId: node.id });
        return;
      }
      const rememberedId = lastProposalByNodeRef.current.get(node.id);
      const remembered = rememberedId ? canvasMediation.getProposal(rememberedId) : undefined;
      if (rememberedId && remembered?.status === 'approved') {
        send({ type: 'CANVAS_PROPOSAL', proposalId: rememberedId, nodeId: node.id });
        return;
      }
      send({
        type: 'SELECT_NODE',
        nodeId: node.id,
        moduleId: node.type === 'module' ? (node.data as ModuleNodeData).moduleId : undefined,
      });
    },
    [send],
  );

  // Build the currently-selected node's SelectedNode shape from the machine's
  // selectedNodeId by looking it up in the live nodes array.
  const selectedNode: SelectedNode | null = useMemo(() => {
    const nodeId = state.context.selectedNodeId;
    if (!nodeId) return null;
    const found = nodes.find((n) => n.id === nodeId);
    if (!found) return null;
    return { type: found.type ?? 'stage', id: found.id, data: found.data as Record<string, unknown> };
  }, [state.context.selectedNodeId, nodes]);

  // Derives the panel's canvasProposal prop from the machine's
  // canvasProposalId plus the live proposal record in canvasMediation —
  // converts ops into rows using the SAME "{field} → {value}" derivation
  // preview.ts already exports (opRow() above), never a second formatter.
  const canvasProposal = useMemo(() => {
    const proposalId = state.context.canvasProposalId;
    if (!proposalId) return null;
    const proposal = canvasMediation.getProposal(proposalId);
    if (!proposal) return null;
    const rows = proposal.ops
      .map(opRow)
      .filter((r): r is { field: string; value: string } => r !== null);
    return { proposalId, status: proposal.status, reason: proposal.reason, rows };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.context.canvasProposalId, version]);

  const [rewindMessage, setRewindMessage] = React.useState<string | null>(null);
  const prevRewindRef = useRef(false);

  // Tracks add_module ids of the proposal currently being approved so that,
  // once the approvingChange substate resolves back to closed, this effect
  // can call pending.mark(id) — plan 08's optimistic confirming treatment —
  // without the machine needing to know about the pending-confirmation
  // registry at all.
  const pendingApprovalAddIdsRef = useRef<string[]>([]);
  const wasApprovingChangeRef = useRef(false);
  const isApprovingChange = state.matches({ reviewPanel: 'approvingChange' });
  useEffect(() => {
    if (isApprovingChange) {
      const proposalId = state.context.canvasProposalId;
      const proposal = proposalId ? canvasMediation.getProposal(proposalId) : undefined;
      pendingApprovalAddIdsRef.current = (proposal?.ops ?? [])
        .filter((op): op is Extract<typeof op, { op: 'add_module' }> => op.op === 'add_module')
        .map((op) => op.rec.id);
    } else if (wasApprovingChangeRef.current) {
      for (const id of pendingApprovalAddIdsRef.current) {
        pendingConfirmations.mark(id);
      }
      pendingApprovalAddIdsRef.current = [];
    }
    wasApprovingChangeRef.current = isApprovingChange;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isApprovingChange]);

  // A rejection of an APPLIED proposal sets canvasRewound; a rejection of a
  // merely-staged proposal does not (two non-overlapping feedback paths —
  // UI-SPEC Interaction Contracts). Only fires the toast on the transition
  // into `true`, so it does not re-fire on unrelated re-renders.
  useEffect(() => {
    if (state.context.canvasRewound && !prevRewindRef.current) {
      setRewindMessage('Change rejected — canvas rewound to the previous state.');
    }
    prevRewindRef.current = state.context.canvasRewound;
  }, [state.context.canvasRewound]);

  // ── ECS ingestion effect: keyed on the pipeline reference itself (XState
  // replaces it only on genuine new SSE data — never a raw `useEffect([])`,
  // per 09-RESEARCH.md Pitfall 2 StrictMode double-invocation). Builds the
  // graph, feeds `syncFromPipeline` the computed layout so plan 04's
  // `toEntityRecords` can seed new entities, then replaces `nodes`/`edges`
  // ONLY when the node id set (the topology) actually changed — a wholesale
  // replace on every 2s tick is exactly what the buffered pattern exists to
  // stop.
  useEffect(() => {
    if (!pipeline) return;

    const currentEcsPositions = new Map<string, { x: number; y: number }>();
    for (const [id, entity] of canvasWorld.byId) {
      currentEcsPositions.set(id, { x: entity.x, y: entity.y });
    }

    const { nodes: builtNodes, edges: builtEdges, layout } = buildCanvasGraph(
      pipeline,
      currentEcsPositions,
    );

    syncFromPipeline(pipeline, layout);

    // Resolve/expire optimistic add_module confirmations in the SAME
    // transition as the sync above (T-09-03) — an id present in the fresh
    // ECS world after syncFromPipeline was confirmed by the backend; an id
    // that outlives its grace window is removed through the ECS choke point
    // rather than left as a permanent ghost.
    for (const id of pendingConfirmations.pendingIds()) {
      if (canvasWorld.byId.has(id)) pendingConfirmations.resolve(id);
    }
    for (const id of pendingConfirmations.expired(Date.now())) {
      canvasWorld.removeById(id);
      pendingConfirmations.resolve(id);
    }

    // Ghost nodes for staged `add_module` proposals reference an entity id
    // that does not exist in `pipeline`/ECS yet — appended here (not in
    // canvasGraph.ts) using the same auto-layout row the real module nodes
    // use, per plan 08 Task 3.
    const existingIds = new Set(builtNodes.map((n) => n.id));
    const moduleCount = builtNodes.filter((n) => n.type === 'module').length;
    let ghostOffset = 0;
    for (const [proposalId, proposal] of canvasMediation.proposals) {
      if (proposal.status !== 'staged') continue;
      for (const op of proposal.ops) {
        if (op.op !== 'add_module') continue;
        if (existingIds.has(op.rec.id)) continue;
        builtNodes.push({
          id: op.rec.id,
          type: 'module',
          position: { x: (moduleCount + ghostOffset) * 190, y: 600 },
          data: {
            label: op.rec.label,
            category: op.rec.category ?? '',
            // GhostModuleNode never reads `state` (there is no live status
            // to reflect yet) — 'disabled' is a type-safe placeholder only.
            state: 'disabled',
            moduleId: op.rec.id,
            proposal: { proposalId, kind: 'ghost', deltaLines: [] },
          } satisfies ModuleNodeData,
        });
        existingIds.add(op.rec.id);
        ghostOffset++;
      }
    }

    setNodes((prev) => {
      const prevIds = new Set(prev.map((n) => n.id));
      const builtIds = new Set(builtNodes.map((n) => n.id));
      const sameTopology =
        prevIds.size === builtIds.size && [...prevIds].every((id) => builtIds.has(id));
      return sameTopology ? prev : builtNodes;
    });
    setEdges((prev) => {
      const prevIds = new Set(prev.map((e) => e.id));
      const builtIds = new Set(builtEdges.map((e) => e.id));
      const sameTopology =
        prevIds.size === builtIds.size && [...prevIds].every((id) => builtIds.has(id));
      return sameTopology ? prev : builtEdges;
    });
  }, [pipeline, setNodes, setEdges]);

  // ── ECS patch effect: keyed on `version` (the touch() bridge). Looks each
  // node up by id in the ECS `byId` map and returns the SAME node reference
  // when nothing mirrored changed — this is what preserves React Flow's
  // internal measurement tracking. Never builds the array from
  // a fresh mapping of the live entity collection; never replaces the whole array here.
  useEffect(() => {
    // Computed once per run — a pure derivation from canvasMediation.proposals
    // (D9-08: preview is a pure overlay, never touches the live world).
    const annotations = proposalAnnotations(canvasMediation.proposals);
    const pendingIds = new Set(pendingConfirmations.pendingIds());

    setNodes((prev) =>
      prev.map((n) => {
        const entity = canvasWorld.byId.get(n.id);
        const mirroredPatch = entity ? dataFromEntity(n.type, entity) : null;
        const currentData = n.data as Record<string, unknown>;

        const ann = annotations.get(n.id);
        const confirming = pendingIds.has(n.id);

        const mirroredChanged = mirroredPatch
          ? Object.entries(mirroredPatch).some(([k, v]) => currentData[k] !== v)
          : false;
        const annotationChanged =
          annotationKey(ann) !== annotationKey(currentData.proposal as ProposalAnnotation | undefined);
        const confirmingChanged = Boolean(currentData.confirming) !== confirming;

        if (!mirroredChanged && !annotationChanged && !confirmingChanged) return n;

        return {
          ...n,
          data: {
            ...currentData,
            ...(mirroredPatch ?? {}),
            proposal: ann,
            confirming,
          },
        };
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, setNodes]);

  // Drag-stop write-back: only the entity that actually moved gets its x/y
  // written into ECS, and only once the drag gesture completes — never
  // mid-drag. `if (n && entity)` is the full extent of spike-tested
  // protection against a node removed mid-drag (09-RESEARCH.md Pitfall 3,
  // explicitly unverified); flagged here rather than building speculative
  // machinery, slated for the plan-10 manual check.
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const c of changes) {
        if (c.type !== 'position') continue;
        if (c.dragging) {
          draggingId.current = c.id;
        } else if (draggingId.current === c.id) {
          draggingId.current = null;
          const n = nodes.find((n) => n.id === c.id);
          const entity = canvasWorld.byId.get(c.id);
          if (n && entity && n.position) {
            entity.x = n.position.x;
            entity.y = n.position.y;
          }
        }
      }
      onNodesChangeRF(changes);
    },
    [nodes, onNodesChangeRF],
  );

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
        onClose={() => send({ type: 'CLOSE_PANEL' })}
        testRunning={testRunning}
        testResult={testResult}
        onRunTests={handleRunTests}
        review={state.context.review}
        audit={state.context.audit}
        reviewState={reviewState}
        actionError={state.context.actionError}
        onApprove={() => send({ type: 'APPROVE' })}
        onReject={(feedback) => send({ type: 'REJECT', feedback })}
        onRetryReview={() => send({ type: 'RETRY' })}
        canvasProposal={canvasProposal}
        onApproveChange={() => send({ type: 'APPROVE_CHANGE' })}
        onRejectChange={() => send({ type: 'REJECT_CHANGE' })}
      />

      {/* Rewind confirmation toast — fires only when a rejection actually
          rewound applied state (canvasRewound), never for a plain reject of
          a staged-only proposal. */}
      <RewindToast message={rewindMessage} onDismiss={() => setRewindMessage(null)} />
    </div>
  );
}
