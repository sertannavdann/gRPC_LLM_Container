import { Handle, Position } from "@xyflow/react";
import { useRef } from "react";

export type PipelineNodeData = { label: string; highlighted: boolean };

export function PipelineNode({ data, id }: { data: PipelineNodeData; id: string }) {
  const renderCount = useRef(0);
  renderCount.current++;
  return (
    <div
      data-render-count={renderCount.current}
      onMouseEnter={() => window.dispatchEvent(new CustomEvent("spike:hover", { detail: { id } }))}
      onMouseLeave={() => window.dispatchEvent(new CustomEvent("spike:hover", { detail: { id: null } }))}
      style={{
        padding: "8px 12px",
        borderRadius: 8,
        border: data.highlighted ? "2px solid #f472b6" : "2px solid #4b5563",
        background: data.highlighted ? "#2a1f2a" : "#161923",
        minWidth: 130,
        fontSize: 12,
        opacity: data.highlighted ? 1 : 0.55,
        transition: "opacity 80ms linear",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div style={{ fontWeight: 600 }}>{data.label}</div>
      <div style={{ opacity: 0.5 }}>renders: {renderCount.current}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
