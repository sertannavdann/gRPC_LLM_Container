import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useMachine } from "@xstate/react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  type Node,
  type Edge,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { makePipelineMachine } from "./pipelineMachine";
import { world, byId, subscribeWorld, getWorldVersion, resetWorld, touch } from "./ecs";
import { syncFromPipeline } from "./ecsSync";
import { PipelineNode, type PipelineNodeData } from "./PipelineNode";

const nodeTypes = { pipeline: PipelineNode };

function useWorldVersion() {
  return useSyncExternalStore(subscribeWorld, getWorldVersion);
}

function Canvas({
  intervalMs,
  guardStaleSelection,
}: {
  intervalMs: number;
  guardStaleSelection: boolean;
}) {
  const intervalMsRef = useRef(intervalMs);
  const machine = useMemo(
    () => makePipelineMachine(intervalMsRef, { guardStaleSelection }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );
  const [state, send] = useMachine(machine);
  const [log, setLog] = useState<string[]>([]);
  const appendLog = useCallback((msg: string) => {
    setLog((l) => [...l.slice(-19), msg]);
    // eslint-disable-next-line no-console
    console.log(msg);
  }, []);

  useEffect(() => {
    resetWorld();
  }, []);

  useEffect(() => {
    syncFromPipeline(state.context.pipeline, appendLog);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.context.pipeline]);

  const version = useWorldVersion();
  const [nodes, setNodes, onNodesChangeRF] = useNodesState<Node<PipelineNodeData>>([]);
  const [edges] = useState<Edge[]>([]);
  const draggingId = useRef<string | null>(null);
  const selectedId = state.context.selectedNodeId;

  // Patch buffered RF node list from ECS world + XState selection.
  useEffect(() => {
    setNodes((prev) => {
      const next: Node<PipelineNodeData>[] = [];
      for (const e of world.entities) {
        const existing = prev.find((n) => n.id === e.id);
        const position = e.id === draggingId.current && existing ? existing.position : e.position;
        next.push({
          id: e.id,
          type: "pipeline",
          position,
          data: {
            label: e.label,
            status: e.status,
            hovered: e.hovered,
            dragCount: e.dragCount,
            selected: e.id === selectedId,
          },
        });
      }
      return next;
    });
  }, [version, selectedId, setNodes]);

  useEffect(() => {
    const onHover = (ev: Event) => {
      const { id, hovered } = (ev as CustomEvent).detail;
      const entity = byId(id);
      if (entity) {
        entity.hovered = hovered;
        touch();
      }
    };
    const onSelect = (ev: Event) => {
      const { id } = (ev as CustomEvent).detail;
      send({ type: "SELECT_NODE", nodeId: id });
    };
    window.addEventListener("spike:hover", onHover);
    window.addEventListener("spike:select", onSelect);
    return () => {
      window.removeEventListener("spike:hover", onHover);
      window.removeEventListener("spike:select", onSelect);
    };
  }, [send]);

  const onNodesChange = useCallback(
    (changes: NodeChange<Node<PipelineNodeData>>[]) => {
      for (const c of changes) {
        if (c.type === "position") {
          if (c.dragging) {
            draggingId.current = c.id;
          } else {
            draggingId.current = null;
            const n = nodes.find((n) => n.id === c.id);
            const entity = byId(c.id);
            if (n && entity) {
              entity.position = n.position;
              entity.dragCount++;
            }
          }
        }
      }
      onNodesChangeRF(changes);
    },
    [nodes, onNodesChangeRF]
  );

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <ReactFlow nodeTypes={nodeTypes} nodes={nodes} edges={edges} onNodesChange={onNodesChange} fitView>
        <Background />
        <Controls />
      </ReactFlow>
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
          background: "#161923cc",
          padding: 8,
          borderRadius: 6,
          fontSize: 11,
          maxWidth: 460,
          maxHeight: 220,
          overflow: "auto",
        }}
      >
        <div>
          selected (xstate): <b id="selected-id">{selectedId ?? "none"}</b>
        </div>
        <div id="sync-log">
          {log.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [intervalMs, setIntervalMs] = useState(2000);
  const [guardStaleSelection, setGuardStaleSelection] = useState(true);
  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          zIndex: 10,
          background: "#161923cc",
          padding: 12,
          borderRadius: 8,
          display: "flex",
          gap: 16,
          alignItems: "center",
          fontSize: 13,
        }}
      >
        <span>Spike 002 — ECS + XState Coexistence</span>
        <label>
          <input
            type="checkbox"
            checked={guardStaleSelection}
            onChange={(e) => setGuardStaleSelection(e.target.checked)}
          />{" "}
          guard stale selection
        </label>
        <label>
          churn interval:{" "}
          <select value={intervalMs} onChange={(e) => setIntervalMs(Number(e.target.value))}>
            <option value={2000}>2000ms (realistic)</option>
            <option value={600}>600ms (stress)</option>
          </select>
        </label>
      </div>
      <Canvas key={`${intervalMs}-${guardStaleSelection}`} intervalMs={intervalMs} guardStaleSelection={guardStaleSelection} />
    </div>
  );
}
