# Phase 9: ECS Context-Substrate Canvas - Context

**Gathered:** 2026-08-23
**Status:** Ready for planning
**Source:** Spike sessions 1–2 (`.planning/spikes/MANIFEST.md` Requirements, spikes 001–008) — decisions were made and verdict-approved by the user during spiking; this document translates them for planning.

<domain>
## Phase Boundary

Frontend-first phase inside `ui_service`, plus one thin export surface for the orchestrator.
Rebuilds the pipeline canvas state layer (`ui_service/src/app/pipeline/page.tsx` and its
supporting store/machine files) on a miniplex ECS world serving three consumers: React Flow
v12 rendering, the locked XState v5 page machines, and LLM context assembly. Adds the LLM
write path (staged proposals behind Phase 8 approval gates) and snapshot/event-log history.

Out of scope: backend data model changes, new visual design language (Phase 6/8 design
system is reused), marketplace/enterprise features (Phase 10), RL/training concerns.

</domain>

<decisions>
## Implementation Decisions

### Library and substrate (LOCKED — spikes 003a/b, 005a/b, 006)
- miniplex 2.0 is the ECS library. The bitECS reversal hypothesis was tested on its own
  best criteria (serialization, deltas) and empirically invalidated on both halves. Do not
  reopen without a workload of thousands of numeric entities in a per-frame loop.
- One world, tri-consumer: React Flow, XState, and the context assembler all read the same
  entity store. No parallel/dual stores.

### Rendering (LOCKED — spike 001)
- Buffered React Flow pattern is mandatory: React Flow owns node state via `useNodesState`;
  ECS patches non-positional fields by id on `touch()`; position writes back to ECS on
  drag-stop only. NEVER derive the `nodes` prop fresh from `world.entities.map()` — this
  breaks rendering outright (blank canvas, remeasure feedback loop).
- Reactivity bridge: module-level `touch()`/`subscribeWorld()`/`getWorldVersion()` +
  `useSyncExternalStore`. Neither miniplex nor React notice component-value mutation
  without it.

### Ownership (LOCKED — spike 002, extended by 007)
- XState (via SSE snapshots) is the single source of truth for entity existence. The sync
  system (`syncFromPipeline`) is the only place that adds/removes entities or writes
  mirrored fields from snapshots.
- Any XState state referencing an entity id must be re-validated against every new snapshot
  in the same transition (`clearSelectionIfMissing` pattern), generalized to staged
  proposals (see write path).

### Context assembly (LOCKED — spikes 005, 006)
- c_state is produced by a canonical verbalizer: sort by logical string id, compact
  schema-headed DSL format. Never dump raw JSON into LLM context (2.9× token cost).
- Iterative invocations receive delta contexts (changed/added entities + removed ids since
  last invocation) with an explicit "unchanged entities omitted" header. Dirty tracking
  rides the same mutation choke points the ownership contract already mandates.

### LLM write path (LOCKED — spike 007)
- LLM output arrives as schema-validated mutation ops (zod in production), staged as
  proposals — never direct mutation. Preview is a pure overlay on views.
- Re-validation at three points: proposal time, every SSE snapshot sync, approval time.
- Ownership policy: LLM ops may touch module entities only; services/stages read-only.
- Optimistic approved additions need pending-confirmation handling (grace period) or the
  next backend snapshot without them will flicker them out.

### History (LOCKED — spike 008)
- Snapshot ring (canonical sorted JSON) + append-only semantic event log. Rewind is
  clear-then-restore — never in-place restore over a drifted world. Restore marks all
  entities dirty so deltas and the React Flow buffer observe it. Redo is log replay
  through the mediation layer, not inverse ops.
- Snapshots capture full entity records including UI-only fields (closes the known 002
  ECS-only-field gap for rewind scenarios).

### Behaviors (LOCKED — spike 004)
- Stateless per-interaction derivations (validation, highlighting, layout hints) stay as
  plain `resolveLifecycle`-style pure functions. No ECS "systems" for these — measured
  3× code for zero benefit.

### Claude's Discretion
- File/module layout within `ui_service/src` (suggested: `src/ecs/` for world, bridge,
  sync, verbalizer, mediation, history).
- Exact zod schemas for the op vocabulary; exact compact-DSL field order.
- How the c_state export reaches the orchestrator (dashboard endpoint vs UI-side export) —
  choose the smallest seam consistent with the existing `/context` bridge pattern.
- Whether delta version counters live in the XState machine context or the ECS module.
- Test framework specifics (Playwright for E2E per spike conventions; existing unit
  harness for pure functions).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spike blueprint (proven patterns, code snippets, landmines)
- `.claude/skills/spike-findings-grpc-llm/SKILL.md` — requirements index
- `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md` — implementation blueprint (touch bridge, buffered pattern, sync system, selection guard — with code)
- `.planning/spikes/MANIFEST.md` — Session-2 Requirements section (context-substrate rules)
- `.planning/spikes/005b-world-snapshot-miniplex/README.md` — snapshot head-to-head + canonical serializer
- `.planning/spikes/006-delta-context-streaming/README.md` — delta strategy, dirty tracker
- `.planning/spikes/007-llm-writes-world/README.md` — mediation layer, op schema, 3-point re-validation
- `.planning/spikes/008-snapshot-replay-and-rewind/README.md` — ring + event log, rewind semantics

### Production integration points
- `ui_service/src/machines/pipelinePage.ts` — locked XState v5 machine (Phase 6); SSE_MESSAGE transitions gain `clearSelectionIfMissing`
- `ui_service/src/app/pipeline/page.tsx` — canvas page to be re-plumbed
- `ui_service/src/components/pipeline/ModuleNode.tsx` — `resolveLifecycle` convention exemplar
- `ui_service/src/store/nexusStore.ts` — existing Zustand store (SSE wiring)
- `dashboard_service/pipeline_stream.py` — SSE `/stream/pipeline-state` source shape
- Phase 8 approval-gate UI/flow — `.planning/phases/08-co-evolution-approval/08-CONTEXT.md`

</canonical_refs>

<specifics>
## Specific Ideas

- Spike code in `.planning/spikes/00{5,6,7,8}*/` is reference-quality and may be adapted
  directly (fixture shapes mirror the real SSE payload).
- Token/measurement claims to preserve in tests: canonical text stable across churn;
  delta mirror-reconstruction exact; compact-DSL ≪ raw JSON.

</specifics>

<deferred>
## Deferred Ideas

- bitECS reconsideration (only if a future workload is thousands-of-numeric-entities in a
  per-frame loop).
- Live-model behavioral testing of delta-context prompts (spike 006 noted framing risk;
  verify with the real orchestrator LLM post-integration).
- SSE remove/re-add flicker grace period for ECS-only fields outside rewind (known 002
  residual gap) — implement if observed in production telemetry.

</deferred>

---

*Phase: 09-ecs-context-canvas*
*Context gathered: 2026-08-23 from spike sessions (user-approved verdicts)*
