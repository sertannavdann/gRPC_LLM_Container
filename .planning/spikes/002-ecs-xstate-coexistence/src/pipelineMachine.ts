// Simplified stand-in for ui_service/src/machines/pipelinePage.ts (D-14).
// Kept structurally faithful: parallel regions, `pipeline` as a wholesale-
// replaced context field on SSE_MESSAGE, a `selection` region for the
// selected node. The `reviewPanel` region is omitted — it's pure approval
// flow-control, unrelated to the ECS entity-rendering question this spike
// tests.
import { setup, fromCallback, assign } from "xstate";
import type { NodeStatus } from "./ecs";

export type NodeSnapshot = { id: string; label: string; status: NodeStatus };
export type PipelineSnapshot = { nodes: NodeSnapshot[] };

export interface PipelinePageContext {
  pipeline: PipelineSnapshot | null;
  lastUpdate: number;
  selectedNodeId: string | null;
}

export type PipelinePageEvent =
  | { type: "SSE_MESSAGE"; data: PipelineSnapshot }
  | { type: "SSE_ERROR" }
  | { type: "SELECT_NODE"; nodeId: string }
  | { type: "CLOSE_PANEL" };

const ALL_IDS = ["orchestrator", "dashboard", "sandbox", "module-0", "module-1", "module-2"];
const STATUSES: NodeStatus[] = ["idle", "building", "validating", "validated", "error"];

/** Simulated SSE stream — mirrors connectPipelineSSE()'s sendBack contract.
 * Periodically drops/re-adds entities (simulating modules appearing and
 * disappearing from the live graph, per Phase 8 D-04 "the graph is the
 * notification") and randomizes status, at a configurable interval. */
export function makeSseActor(intervalMsRef: { current: number }) {
  return fromCallback<PipelinePageEvent>(({ sendBack }) => {
    const tick = () => {
      const nodes: NodeSnapshot[] = ALL_IDS.filter(() => Math.random() > 0.15).map((id) => ({
        id,
        label: id,
        status: STATUSES[Math.floor(Math.random() * STATUSES.length)],
      }));
      // Always keep at least one node present so the canvas isn't empty.
      if (nodes.length === 0) nodes.push({ id: "orchestrator", label: "orchestrator", status: "idle" });
      sendBack({ type: "SSE_MESSAGE", data: { nodes } });
    };
    tick();
    const id = setInterval(tick, intervalMsRef.current);
    return () => clearInterval(id);
  });
}

export function makePipelineMachine(
  intervalMsRef: { current: number },
  opts: { guardStaleSelection: boolean } = { guardStaleSelection: true }
) {
  const onMessage = opts.guardStaleSelection
    ? (["updatePipeline", "clearSelectionIfMissing"] as const)
    : (["updatePipeline"] as const);

  return setup({
    types: {
      context: {} as PipelinePageContext,
      events: {} as PipelinePageEvent,
    },
    actors: {
      sseConnection: makeSseActor(intervalMsRef),
    },
    actions: {
      updatePipeline: assign(({ event }) => {
        if (event.type !== "SSE_MESSAGE") return {};
        return { pipeline: event.data, lastUpdate: Date.now() };
      }),
      setSelection: assign(({ event }) => {
        if (event.type !== "SELECT_NODE") return {};
        return { selectedNodeId: event.nodeId };
      }),
      clearSelection: assign(() => ({ selectedNodeId: null })),
      // Ownership-conflict guard: if the currently-selected node vanishes
      // from a new SSE snapshot, XState's selection region must clear
      // itself — otherwise selectedNodeId points at an entity the ECS
      // sync system is about to delete. This is the coexistence case this
      // spike is built to test.
      clearSelectionIfMissing: assign(({ context, event }) => {
        if (event.type !== "SSE_MESSAGE") return {};
        const stillPresent = event.data.nodes.some((n) => n.id === context.selectedNodeId);
        if (context.selectedNodeId && !stillPresent) {
          return { selectedNodeId: null };
        }
        return {};
      }),
    },
  }).createMachine({
    id: "pipelinePageSpike",
    type: "parallel",
    context: { pipeline: null, lastUpdate: 0, selectedNodeId: null },
    states: {
      connection: {
        initial: "connecting",
        invoke: { src: "sseConnection" },
        states: {
          connecting: {
            on: {
              SSE_MESSAGE: {
                target: "connected",
                actions: onMessage,
              },
            },
          },
          connected: {
            on: {
              SSE_MESSAGE: { actions: onMessage },
              SSE_ERROR: "reconnecting",
            },
          },
          reconnecting: {
            on: {
              SSE_MESSAGE: {
                target: "connected",
                actions: onMessage,
              },
            },
          },
        },
      },
      selection: {
        initial: "none",
        states: {
          none: {
            on: { SELECT_NODE: { target: "selected", actions: "setSelection" } },
          },
          selected: {
            on: {
              SELECT_NODE: { actions: "setSelection" },
              CLOSE_PANEL: { target: "none", actions: "clearSelection" },
            },
          },
        },
      },
    },
  });
}
