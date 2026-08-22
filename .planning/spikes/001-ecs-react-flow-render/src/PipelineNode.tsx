import { Handle, Position } from "@xyflow/react";
import { useRef } from "react";
import type { NodeStatus } from "./ecs";

const STATUS_COLOR: Record<NodeStatus, string> = {
  idle: "#4b5563",
  building: "#eab308",
  validating: "#3b82f6",
  validated: "#22c55e",
  error: "#ef4444",
};

export type PipelineNodeData = {
  label: string;
  status: NodeStatus;
  lastTouchedBy: string;
  updateCount: number;
};

export function PipelineNode({ data }: { data: PipelineNodeData }) {
  // Render counter — proves (or disproves) that this specific node
  // re-renders only when ITS data changes, not on every world touch().
  const renderCount = useRef(0);
  renderCount.current++;

  return (
    <div
      style={{
        padding: "8px 12px",
        borderRadius: 8,
        border: `2px solid ${STATUS_COLOR[data.status]}`,
        background: "#161923",
        minWidth: 140,
        fontSize: 12,
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div style={{ fontWeight: 600 }}>{data.label}</div>
      <div style={{ color: STATUS_COLOR[data.status] }}>{data.status}</div>
      <div style={{ opacity: 0.6, marginTop: 4 }}>
        touched: {data.lastTouchedBy} ({data.updateCount})
      </div>
      <div style={{ opacity: 0.4 }}>renders: {renderCount.current}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
