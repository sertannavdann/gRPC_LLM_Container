import { Handle, Position } from "@xyflow/react";
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
  hovered: boolean;
  dragCount: number;
  selected: boolean;
};

export function PipelineNode({
  data,
  id,
}: {
  data: PipelineNodeData;
  id: string;
}) {
  return (
    <div
      onMouseEnter={() => window.dispatchEvent(new CustomEvent("spike:hover", { detail: { id, hovered: true } }))}
      onMouseLeave={() => window.dispatchEvent(new CustomEvent("spike:hover", { detail: { id, hovered: false } }))}
      onClick={() => window.dispatchEvent(new CustomEvent("spike:select", { detail: { id } }))}
      style={{
        padding: "8px 12px",
        borderRadius: 8,
        border: `2px solid ${STATUS_COLOR[data.status]}`,
        outline: data.selected ? "3px solid #f472b6" : data.hovered ? "2px dashed #f472b6" : "none",
        outlineOffset: 2,
        background: "#161923",
        minWidth: 140,
        fontSize: 12,
        cursor: "pointer",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div style={{ fontWeight: 600 }}>{data.label}</div>
      <div style={{ color: STATUS_COLOR[data.status] }}>{data.status}</div>
      <div style={{ opacity: 0.6, marginTop: 4 }}>
        {data.selected ? "SELECTED (xstate)" : data.hovered ? "hovered (ecs-only)" : " "}
      </div>
      <div style={{ opacity: 0.4 }}>dragCount: {data.dragCount}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
