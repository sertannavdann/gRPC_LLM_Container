import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { ReactFlow, Background, Controls, useNodesState, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { TOPOLOGY, buildEdgePairs } from "./topology";
import { world as ecsWorld, subscribeWorld, getWorldVersion, highlightSystem } from "./ecsImpl";
import { computeHighlighted } from "./adhocImpl";
import { PipelineNode, type PipelineNodeData } from "./PipelineNode";

const nodeTypes = { pipeline: PipelineNode };

function initialNodes(): Node<PipelineNodeData>[] {
  return TOPOLOGY.map((n) => ({
    id: n.id,
    type: "pipeline",
    position: n.position,
    data: { label: n.label, highlighted: false },
  }));
}

function initialEdges(): Edge[] {
  return buildEdgePairs().map(([source, target]) => ({ id: `${source}->${target}`, source, target }));
}

function useWorldVersion() {
  return useSyncExternalStore(subscribeWorld, getWorldVersion);
}

/** Implementation A: ECS + highlightSystem(). */
function EcsCanvas() {
  const version = useWorldVersion();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<PipelineNodeData>>(initialNodes());
  const [edges] = useState<Edge[]>(initialEdges());

  useEffect(() => {
    const onHover = (ev: Event) => {
      const { id } = (ev as CustomEvent).detail;
      highlightSystem(id);
    };
    window.addEventListener("spike:hover", onHover);
    return () => window.removeEventListener("spike:hover", onHover);
  }, []);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const e = ecsWorld.entities.find((e) => e.id === n.id);
        if (!e || n.data.highlighted === e.highlighted) return n;
        return { ...n, data: { ...n.data, highlighted: e.highlighted } };
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, setNodes]);

  return (
    <ReactFlow nodeTypes={nodeTypes} nodes={nodes} edges={edges} onNodesChange={onNodesChange} fitView>
      <Background />
      <Controls />
    </ReactFlow>
  );
}

/** Implementation B: plain React — pure computeHighlighted() + useMemo, no ECS. */
function AdhocCanvas() {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<PipelineNodeData>>(initialNodes());
  const [edges] = useState<Edge[]>(initialEdges());
  const highlighted = useMemo(() => computeHighlighted(hoveredId), [hoveredId]);

  useEffect(() => {
    const onHover = (ev: Event) => {
      const { id } = (ev as CustomEvent).detail;
      setHoveredId(id);
    };
    window.addEventListener("spike:hover", onHover);
    return () => window.removeEventListener("spike:hover", onHover);
  }, []);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const isHighlighted = highlighted.has(n.id);
        if (n.data.highlighted === isHighlighted) return n;
        return { ...n, data: { ...n.data, highlighted: isHighlighted } };
      })
    );
  }, [highlighted, setNodes]);

  return (
    <ReactFlow nodeTypes={nodeTypes} nodes={nodes} edges={edges} onNodesChange={onNodesChange} fitView>
      <Background />
      <Controls />
    </ReactFlow>
  );
}

async function runStressTest(rounds: number, onDone: (elapsedMs: number) => void) {
  const start = performance.now();
  for (let r = 0; r < rounds; r++) {
    for (const n of TOPOLOGY) {
      window.dispatchEvent(new CustomEvent("spike:hover", { detail: { id: n.id } }));
      await new Promise((res) => setTimeout(res, 5));
    }
  }
  window.dispatchEvent(new CustomEvent("spike:hover", { detail: { id: null } }));
  onDone(performance.now() - start);
}

export default function App() {
  const [impl, setImpl] = useState<"ecs" | "adhoc">("ecs");
  const [lastStressMs, setLastStressMs] = useState<number | null>(null);

  const sumRenders = () =>
    Array.from(document.querySelectorAll<HTMLElement>("[data-render-count]")).reduce(
      (sum, el) => sum + Number(el.dataset.renderCount ?? 0),
      0
    );

  const [renderSum, setRenderSum] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setRenderSum(sumRenders()), 300);
    return () => clearInterval(id);
  }, [impl]);

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
        <span>Spike 004 — ECS systems vs ad-hoc React</span>
        <label>
          <input type="radio" checked={impl === "ecs"} onChange={() => setImpl("ecs")} /> ecs-system
        </label>
        <label>
          <input type="radio" checked={impl === "adhoc"} onChange={() => setImpl("adhoc")} /> adhoc-react
        </label>
        <button
          id="stress-button"
          onClick={() => runStressTest(10, (ms) => setLastStressMs(ms))}
        >
          Run stress test (10x full sweep)
        </button>
        <span id="render-sum">total node renders: {renderSum}</span>
        {lastStressMs !== null && <span id="stress-elapsed">stress elapsed: {lastStressMs.toFixed(0)}ms</span>}
      </div>
      <div style={{ position: "absolute", inset: 0, top: 0 }}>{impl === "ecs" ? <EcsCanvas key="ecs" /> : <AdhocCanvas key="adhoc" />}</div>
    </div>
  );
}
