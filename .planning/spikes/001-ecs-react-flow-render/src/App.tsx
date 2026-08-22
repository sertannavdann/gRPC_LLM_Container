import {
  ReactFlow,
  Background,
  Controls,
  applyNodeChanges,
  useNodesState,
  type Node,
  type NodeChange,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  world,
  seed,
  byId,
  touch,
  subscribeWorld,
  getWorldVersion,
  startChaos,
  stopChaos,
  type PipelineEntity,
} from "./ecs";
import { PipelineNode, type PipelineNodeData } from "./PipelineNode";

seed();

const nodeTypes = { pipeline: PipelineNode };

function entityToNode(e: PipelineEntity): Node<PipelineNodeData> {
  return {
    id: e.id,
    type: "pipeline",
    position: e.position,
    data: {
      label: e.label,
      status: e.status,
      lastTouchedBy: e.lastTouchedBy,
      updateCount: e.updateCount,
    },
  };
}

function buildEdges(): Edge[] {
  const edges: Edge[] = [];
  for (const e of world.entities) {
    for (const target of e.connections) {
      edges.push({ id: `${e.id}->${target}`, source: e.id, target, animated: true });
    }
  }
  return edges;
}

function useWorldVersion() {
  return useSyncExternalStore(subscribeWorld, getWorldVersion);
}

function useFps() {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let frames = 0;
    let last = performance.now();
    let raf = 0;
    const loop = (t: number) => {
      frames++;
      if (t - last >= 1000) {
        setFps(frames);
        frames = 0;
        last = t;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  return fps;
}

/** Mode A: nodes are re-derived from the ECS world on every touch(), with
 * no local buffer. React Flow is fully controlled from ECS state. */
function NaiveCanvas({ chaosMs }: { chaosMs: number }) {
  const version = useWorldVersion();
  const draggingId = useRef<string | null>(null);
  const conflictCount = useRef(0);
  const lastNodesRef = useRef<Node<PipelineNodeData>[]>([]);

  const nodes = useMemo(() => world.entities.map(entityToNode), [version]);
  const edges = useMemo(() => buildEdges(), [version]);

  useEffect(() => {
    if (draggingId.current && lastNodesRef.current !== nodes) {
      conflictCount.current++;
    }
    lastNodesRef.current = nodes;
  }, [nodes]);

  const onNodesChange = useCallback((changes: NodeChange<Node<PipelineNodeData>>[]) => {
    const next = applyNodeChanges(changes, world.entities.map(entityToNode));
    for (const n of next) {
      const entity = byId(n.id);
      if (entity) {
        entity.position = n.position;
        entity.lastTouchedBy = "drag";
      }
    }
    for (const c of changes) {
      if (c.type === "position") {
        draggingId.current = c.dragging ? c.id : null;
      }
    }
    touch();
  }, []);

  useEffect(() => {
    startChaos(chaosMs, null); // naive mode never excludes the dragged node
    return () => stopChaos();
  }, [chaosMs]);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <ReactFlow nodeTypes={nodeTypes} nodes={nodes} edges={edges} onNodesChange={onNodesChange} fitView>
        <Background />
        <Controls />
      </ReactFlow>
      <ConflictBadge getCount={() => conflictCount.current} />
    </div>
  );
}

/** Mode B: React Flow owns its own local node state for drag responsiveness.
 * ECS touches only patch non-positional data (status/updateCount) into the
 * local state; position writes back to ECS only on drag stop. */
function BufferedCanvas({ chaosMs }: { chaosMs: number }) {
  const initial = useMemo(() => world.entities.map(entityToNode), []);
  const [nodes, setNodes, onNodesChangeRF] = useNodesState<Node<PipelineNodeData>>(initial);
  const [edges] = useState<Edge[]>(() => buildEdges());
  const draggingId = useRef<string | null>(null);
  const conflictCount = useRef(0);

  useEffect(() => {
    const unsub = subscribeWorld(() => {
      setNodes((prev) => {
        let changed = false;
        const next = prev.map((n) => {
          if (n.id === draggingId.current) return n; // never touch the actively-dragged node
          const entity = byId(n.id);
          if (!entity) return n;
          const dataChanged =
            entity.status !== n.data.status || entity.updateCount !== n.data.updateCount;
          if (!dataChanged) return n;
          changed = true;
          return { ...n, data: { ...n.data, status: entity.status, lastTouchedBy: entity.lastTouchedBy, updateCount: entity.updateCount } };
        });
        return changed ? next : prev;
      });
    });
    return unsub;
  }, [setNodes]);

  useEffect(() => {
    startChaos(chaosMs, draggingId.current);
    return () => stopChaos();
  }, [chaosMs]);

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
              entity.lastTouchedBy = "drag";
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
      <ConflictBadge getCount={() => conflictCount.current} />
    </div>
  );
}

function ConflictBadge({ getCount }: { getCount: () => number }) {
  const [, forceTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => forceTick((t) => t + 1), 300);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={hud}>
      drag-vs-touch conflicts: <b id="conflict-count">{getCount()}</b>
    </div>
  );
}

const hud: React.CSSProperties = {
  position: "absolute",
  bottom: 12,
  left: 12,
  background: "#161923cc",
  padding: "6px 10px",
  borderRadius: 6,
  fontSize: 12,
  zIndex: 5,
};

export default function App() {
  const [mode, setMode] = useState<"naive" | "buffered">("naive");
  const [chaosMs, setChaosMs] = useState(400);
  const fps = useFps();

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
        <span>Spike 001 — ECS + React Flow</span>
        <label>
          <input
            type="radio"
            checked={mode === "naive"}
            onChange={() => setMode("naive")}
          />{" "}
          naive (fully controlled from ECS)
        </label>
        <label>
          <input
            type="radio"
            checked={mode === "buffered"}
            onChange={() => setMode("buffered")}
          />{" "}
          buffered (RF-local + patch)
        </label>
        <label>
          chaos interval:{" "}
          <select value={chaosMs} onChange={(e) => setChaosMs(Number(e.target.value))}>
            <option value={2000}>2000ms (realistic SSE)</option>
            <option value={400}>400ms (stress)</option>
            <option value={50}>50ms (extreme stress)</option>
          </select>
        </label>
        <span id="fps">fps: {fps}</span>
      </div>
      {mode === "naive" ? <NaiveCanvas chaosMs={chaosMs} key="naive" /> : <BufferedCanvas chaosMs={chaosMs} key="buffered" />}
    </div>
  );
}
