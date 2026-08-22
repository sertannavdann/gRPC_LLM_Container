# Phase 9: ECS Context-Substrate Canvas - Research

**Researched:** 2026-08-23
**Domain:** Frontend ECS state substrate (miniplex) for a React Flow + XState v5 canvas, with an LLM read/write context bridge
**Confidence:** HIGH (patterns are spike-proven with code; MEDIUM/LOW only on the two open production seams — c_state export route and history persistence scope, both Claude's Discretion)

## Summary

Phase 9 does not invent new patterns — it ports eight spikes' worth of already-validated code into `ui_service`. The three consumers (React Flow, XState, LLM context assembler) and two writers (SSE sync, LLM mediation) all funnel through one miniplex `World` plus a small set of choke-point helpers (`add`/`remove`/`mutate`) that the spikes proved buy dirty-tracking, delta-streaming, and replay-determinism "for free" once the ownership discipline is followed. The production integration surface is narrow: `pipelinePage.ts` gains one new guard action (`clearSelectionIfMissing`, generalized to `invalidateStaleProposals`) wired into its three `SSE_MESSAGE` transitions; `page.tsx`'s pipeline-rebuild `useEffect` is replaced by the buffered-patch pattern; and a new `src/ecs/` module owns the world, bridge, sync, verbalizer, mediation, and history. No backend schema changes are required for the write path — Phase 8's approve/reject RBAC-gated endpoints and `NodeDetailPanel` review-panel pattern are the template to generalize for staged canvas proposals, not a separate mechanism.

The one genuinely new backend seam is exporting `c_state` to the orchestrator. The dashboard service already computes every ingredient (`services`, `modules`, `adapters`, `tools`) inside `pipeline_stream.py:_build_pipeline_state()` every 2 seconds for the SSE stream — the ECS world's SSE-mirrored fields are a pure function of data the backend already has, with no dependency on the browser's live state. The smallest seam is therefore a **server-side Python port of the same canonical verbalizer**, exposed as a new `GET /context/canvas` endpoint on `dashboard_service` (sibling to, not routed through, the adapter-driven `/context/{category}` allowlist), consumed by `ContextBridge` the same way finance/weather/calendar context already is. This avoids requiring the browser tab to be open and connected for the orchestrator to assemble canvas context, and avoids a second live-state transport. Client-side proposal/staging state (LLM write path) does **not** need to reach this endpoint — it is resolved entirely in-browser through Phase 8's existing approval-gate pattern before anything durable happens.

**Primary recommendation:** Build `src/ecs/` as six small files (world+bridge, sync, verbalizer, dirty-tracker, mediation, history) directly adapting the cited spike source files, wire exactly two production touch points (`pipelinePage.ts`'s `SSE_MESSAGE` actions, `page.tsx`'s node-patch effect), and add a Python-side canonical-verbalizer port to `dashboard_service` for the orchestrator seam — do not attempt to push live browser ECS state to the backend.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ECS world (entities, components) | Browser / Client | — | Module-level singleton inside `ui_service`; no backend model per CONTEXT.md phase boundary |
| React Flow rendering (buffered patch) | Browser / Client | — | React Flow owns `nodes` state via `useNodesState`; ECS patches by id on `touch()` |
| Entity existence authority | Browser / Client (XState) | Frontend Server (none — no SSR involvement) | XState's `pipelinePageMachine`, driven by SSE payload already computed server-side |
| SSE payload computation (services/modules/adapters/tools) | API / Backend | — | `dashboard_service/pipeline_stream.py:_build_pipeline_state()` — unchanged by this phase |
| c_state verbalizer (canonical DSL) | Browser / Client (TS) | API / Backend (Python port) | Both consumers need it: in-browser proposal preview/debug (TS) and orchestrator context assembly (Python, sourced from the same backend-computed pipeline dict) |
| Delta/dirty tracking | Browser / Client (TS, for in-browser use) | API / Backend (Python, diffing successive `_build_pipeline_state()` calls) | Dirty tracking rides the add/remove/mutate choke points in each tier independently — no cross-tier state needed since both operate on the same source data |
| LLM mutation-op mediation (propose/validate/approve/reject) | Browser / Client | — | Staged proposals never leave the browser until approved; approval reuses Phase 8's admin-gated flow, itself already backend-enforced at the install-attestation layer for module builds — canvas ops are a new, narrower vocabulary that does not touch modules' install path |
| Snapshot ring + event log (history/undo/redo) | Browser / Client | — | In-memory, page-lifetime scoped; no persistence requirement in CONTEXT.md |
| c_state export to orchestrator | API / Backend | — | New `GET /context/canvas` on `dashboard_service`, consumed via `ContextBridge` — smallest seam consistent with existing pattern (see Pitfall 5) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| miniplex | 2.0.0 [VERIFIED: npm registry] | ECS entity store | Locked by spikes 003a/003b/005a/005b/006 — beats bitECS on every measured context-substrate criterion (see State of the Art table) |
| miniplex-react | 2.0.1 [VERIFIED: npm registry] | `<Entities>`/`useEntities` helpers | Companion package; used narrowly since fine-grained reactivity still requires the manual `touch()` bridge (spike finding, not a miniplex-react gap) |
| zod | 4.4.3 [VERIFIED: npm registry] | Schema validation for LLM mutation ops | Spike 007's explicit recommendation ("hand-rolled validator is spike-grade; use zod in ui_service"); no existing zod usage in `ui_service` to conflict with — clean install |

`ui_service` already has `@xyflow/react` ^12.10.0, `xstate` ^5.28.0, `@xstate/react` ^4.1.3, `zustand` ^5.0.11 — no new deps needed for those tiers. [VERIFIED: ui_service/package.json]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | — | — | Snapshot ring, event log, dirty tracker, and canonical verbalizer are all hand-rolled per spike code (~40–80 LOC each) — do not add a serialization or state-history library; the spikes measured this against library alternatives and hand-rolled won on every axis (see Don't Hand-Roll) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| miniplex | bitECS | INVALIDATED twice (003b UI-store criteria, 005a/006 context-substrate criteria) — do not reopen without a thousands-of-numeric-entities-per-frame-loop workload |
| Hand-rolled JSON snapshot serializer | miniplex's own serialization | miniplex ships none — this is why the adapter layer exists at all (39 LOC per 005b) |
| Zod-validated mutation ops | Hand-rolled validator (spike-grade) | Spike 007 explicitly defers to zod for the real build; hand-rolled was sufficient only to prove the mediation architecture |

**Installation:**
```bash
npm install miniplex miniplex-react zod
```

**Version verification:** Confirmed via `npm view <pkg> version` against the live registry on 2026-08-23. `zod` is on a v4 major (4.4.3); this is a fresh addition to `ui_service` with no existing v3 usage, so no migration concern — the discriminated-union API used for the op vocabulary (`z.discriminatedUnion`) is stable across zod v3 and v4.

## Package Legitimacy Audit

Ran `slopcheck install miniplex miniplex-react zod` against the live npm registry (2026-08-23). **Note for the planner:** slopcheck's `install` subcommand actually executes `npm install` as a side effect — the planner's install task should run `slopcheck scan <pkgs>` if that subcommand exists in the pinned slopcheck version, or isolate the `install` invocation to a throwaway directory / expect it to modify `package.json` and treat that as the real install step (do not run it twice). This research session ran it once, observed the `npm install` side effect against the live repo, and reverted `package.json`/`package-lock.json` via `git checkout` to keep research non-mutating.

| Package | Registry | Age | Downloads (last week) | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| miniplex | npm | ~4.5 yrs (created 2022-02-12) | 6,150 | github.com/hmans/miniplex | [OK] (no source repo linked *in package metadata* — repo exists on GitHub, just not declared in `package.json`) | Approved |
| miniplex-react | npm | ~6.5 yrs npm-registered (2020-03-07; predates the 2.0 miniplex line — same author/monorepo) | 653 | same repo (hmans/miniplex monorepo) | [OK] (same metadata caveat) | Approved |
| zod | npm | ~4.4 yrs (created 2022-03-25) | 264,797,429 | github.com/colinhacks/zod | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

slopcheck's "no source repository linked" note for miniplex/miniplex-react is a package.json metadata gap (the `repository` field), not an absence of a real repo — `npm view miniplex repository.url` resolves to `github.com/hmans/miniplex`, a repo with a multi-year commit history under a well-known author (also the author of `@hmans/id`/`eventery`, both transitive deps observed in the spike `node_modules`). This is a metadata hygiene issue on the package's end, not a legitimacy red flag; all three packages are approved for install without a `checkpoint:human-verify` gate.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────── Browser (ui_service, 'use client') ───────────────────────────┐
│                                                                                             │
│   SSE /stream/pipeline-state                                                              │
│         │ (2s interval, dashboard-computed)                                               │
│         ▼                                                                                  │
│   pipelinePageMachine (XState v5)                                                         │
│    ├─ connection region: sseConnection actor → SSE_MESSAGE event                          │
│    │      │                                                                                │
│    │      ├─ updatePipeline (existing)          ─┐                                        │
│    │      └─ invalidateStaleProposals (NEW,      │  fires on every SSE_MESSAGE,            │
│    │           generalizes clearSelectionIfMissing) ┘  all 3 substates                     │
│    │                                                                                        │
│    └─ (selection / reviewPanel regions — unchanged by this phase)                         │
│         │                                                                                   │
│         ▼ useEffect keyed on state.context.pipeline                                        │
│   syncFromPipeline(pipeline)  ──────────────► miniplex World (src/ecs/world.ts)            │
│         │  (ONLY writer allowed to add/remove   │  ▲                                       │
│         │   entities or write mirrored fields)  │  │ propose()/approve()/reject()          │
│         │                                       │  │ (LLM mediation — src/ecs/mediation.ts)│
│         ▼                                       │  │        ▲                              │
│   touch() ── notifies useSyncExternalStore ──────┘  │        │ chat/ActionCard tool output  │
│         │                                            │        │ (orchestrator → browser)     │
│         ▼                                            │        │                              │
│   buffered React Flow patch (useEffect on version)   │   dirty Set (src/ecs/dirty.ts)        │
│         │  patches nodes[] by id — NEVER a fresh     │        │                              │
│         │  world.entities.map()                      │        ▼                              │
│         ▼                                            │   verbalizer (src/ecs/verbalize.ts)   │
│   <ReactFlow nodes={nodes}> (useNodesState buffer)    │        │  compact-DSL c_state / deltas │
│         │  drag-stop only                             │        │  (in-browser preview/debug)   │
│         └──────── position write-back ────────────────┘        │                              │
│                                                                  │                              │
│   snapshot ring + event log (src/ecs/history.ts) ◄──────────────┘  rewind/undo/redo/replay     │
│         (clear-then-restore into same world; marks all entities dirty on restore)              │
│                                                                                                  │
└───────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                              │  (NO browser→backend push for c_state — see below)
┌─────────────────────────────────────────── API / Backend ─────────────────────────────────────┐
│                                                                                                  │
│  dashboard_service/pipeline_stream.py                                                          │
│    _build_pipeline_state()  ──► same dict already feeds SSE ──► NEW: canvas_verbalize.py       │
│                                                                        │  (Python port of        │
│                                                                        │   verbalize.ts,          │
│                                                                        │   sorted-by-id DSL)      │
│                                                                        ▼                          │
│  GET /context/canvas  (new endpoint, dashboard_service/main.py)                                │
│         ▲                                                                                        │
│         │ ContextBridge.fetch(categories=["canvas"]) or a dedicated fetch_canvas() method       │
│         │                                                                                        │
│  tools/builtin/context_bridge.py  ◄── orchestrator (chat LLM, module-approval ActionCards)      │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

A reader tracing the primary use case: SSE arrives → `syncFromPipeline` is the sole writer of mirrored fields → `touch()` fires → the buffered React Flow effect patches nodes by id → the human sees the update. In parallel, the orchestrator pulls `c_state` from a Python-side re-derivation of the *same* SSE source data (not from the browser), so it works whether or not a canvas tab is even open.

### Recommended Project Structure
```
ui_service/src/ecs/
├── world.ts            # miniplex World singleton + touch()/subscribeWorld()/getWorldVersion() bridge
├── sync.ts             # syncFromPipeline() — the ONE writer for SSE-derived add/remove/mirror
├── dirty.ts            # dirty Set / removedIds Set — choke-point tracker (32 LOC per spike 006)
├── verbalize.ts         # canonicalize() + toCompactDsl() + delta-with-header formatter
├── mediation.ts         # zod op schemas, validateOp(), propose()/previewViews()/approve()/reject()
└── history.ts           # SnapshotRing + EventLog + restoreSnapshot() + replayEvents()

dashboard_service/
└── canvas_context.py    # NEW — Python port of verbalize.ts's canonicalize()/toCompactDsl(),
                          #        operating on pipeline_stream._build_pipeline_state()'s dict
```
This mirrors CONTEXT.md's suggested `src/ecs/` layout exactly (Claude's Discretion section) and keeps a 1:1 file-to-spike-source mapping so review can diff against the cited spike files directly.

### Pattern 1: The reactivity bridge (mandatory boilerplate, not trimmable)
**What:** module-level `touch()`/`subscribeWorld()`/`getWorldVersion()` + `useSyncExternalStore`, because neither miniplex nor `miniplex-react`'s `<Entities>`/`useEntities` fire on component-*value* mutation (only add/remove).
**When to use:** every system/handler that mutates an existing entity's fields.
**Example:**
```ts
// Source: .claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md
import { World } from "miniplex";

type Listener = () => void;
const listeners = new Set<Listener>();
let version = 0;

export function touch() {
  version++;
  listeners.forEach((l) => l());
}
export function subscribeWorld(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function getWorldVersion() {
  return version;
}
```
```tsx
const version = useSyncExternalStore(subscribeWorld, getWorldVersion);
```

### Pattern 2: Buffered React Flow patch (mandatory — naive derivation breaks rendering outright)
**What:** React Flow owns `nodes` via `useNodesState`; an effect keyed on `version` patches matching nodes by id; position writes back to ECS only on drag-stop.
**When to use:** the single `useEffect` replacing `page.tsx`'s current pipeline-rebuild effect (lines 140-311 today rebuild the whole array from the SSE `pipeline` object directly — Phase 9 inserts the ECS layer between SSE and that rebuild, but the "patch by id, never replace wholesale" discipline is unchanged).
**Example:**
```tsx
// Source: .claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md
useEffect(() => {
  setNodes((prev) => prev.map((n) => {
    const e = byId(n.id);
    if (!e) return n;
    if (n.data.status === e.status /* ...other mirrored fields unchanged */) return n;
    return { ...n, data: { ...n.data, status: e.status /* ... */ } };
  }));
}, [version]);
```

### Pattern 3: Single mediation path — SSE sync and LLM proposals share one world
**What:** one `createMediatedWorld()` closure exposing `syncFromPipeline`, `propose`, `previewViews`, `approve`, `reject` — no second world or store for staged proposals.
**When to use:** `src/ecs/mediation.ts`, replacing the spike's hand-rolled `validateOp` with zod schemas.
**Example (adapt directly — spike 007 is reference-quality):**
```ts
// Source: .planning/spikes/007-llm-writes-world/mediation.mjs (adapt to zod + TS types)
import { z } from "zod";

const StatusEnum = z.enum(["running", "disabled", "failed", /* ... */]);

const SetStatusOp = z.object({
  op: z.literal("set_status"),
  id: z.string(),
  value: StatusEnum,
});
const SetCredentialsOp = z.object({
  op: z.literal("set_credentials"),
  id: z.string(),
  list: z.array(z.string()),
});
const MoveOp = z.object({ op: z.literal("move"), id: z.string(), x: z.number(), y: z.number() });
const AddModuleOp = z.object({
  op: z.literal("add_module"),
  rec: z.object({ id: z.string().startsWith("mod-"), label: z.string(), status: StatusEnum }),
});
const RemoveModuleOp = z.object({ op: z.literal("remove_module"), id: z.string() });

export const MutationOp = z.discriminatedUnion("op", [
  SetStatusOp, SetCredentialsOp, MoveOp, AddModuleOp, RemoveModuleOp,
]);

// Ownership policy — separate from schema validity, checked against the LIVE world:
const OWNERSHIP: Record<string, string[]> = {
  set_status: ["service", "module", "stage"],
  set_credentials: ["module"],
  move: ["service", "module", "stage"],
  add_module: ["module"],
  remove_module: ["module"],
};
```
Then port `propose()`/`previewViews()`/`approve()`/`reject()` verbatim from `mediation.mjs` (lines 55-154 of the spike file), swapping the hand-rolled `validateOp` field checks for `MutationOp.safeParse(op)` plus the same referential/ownership checks that remain schema-independent.

### Pattern 4: Re-validation at three points (proposal, every SSE sync, approval)
**What:** `syncFromPipeline` invalidates any staged proposal whose target no longer validates, in the *same* transition that would remove the entity — the `clearSelectionIfMissing` pattern generalized from one XState field to the full proposals map.
**When to use:** inside `sync.ts`'s `syncFromPipeline`, immediately after the add/remove/mirror loop.
**Example:**
```ts
// Source: .planning/spikes/007-llm-writes-world/mediation.mjs lines 87-95
for (const [pid, p] of proposals) {
  if (p.status !== "staged") continue;
  for (const op of p.ops) {
    const v = validateOp(op, byId);
    if (!v.ok) { p.status = "invalidated"; p.reason = v.error; break; }
  }
}
```
The XState-side counterpart (`pipelinePage.ts`) needs the *original* `clearSelectionIfMissing` for `selectedNodeId` specifically — that is a separate, smaller action from the proposals re-validation above (proposals live in the ECS mediation layer, not XState context).

### Pattern 5: Canonical verbalizer — compact-DSL, sorted by id, format-stable under churn
**What:** `canonicalize()` sorts by logical string id before any serialization; `toCompactDsl()` groups by `kind`, is 2.9x more token-efficient than pretty JSON (752 vs 2,175 tokens at 26 entities, spike 005b measurement).
**When to use:** every c_state export — both the TS in-browser verbalizer and its Python port.
**Example:**
```ts
// Source: .planning/spikes/006-delta-context-streaming/verbalize.mjs (byte-identical across 005a/005b/006)
export function canonicalize(views) {
  return [...views].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}
export function toCompactDsl(views) {
  const rows = canonicalize(views);
  const groups = new Map();
  for (const v of rows) {
    if (!groups.has(v.kind)) groups.set(v.kind, []);
    groups.get(v.kind).push(v);
  }
  const lines = ["# pipeline_state — line format: <id> \"<label>\" <status>[/<lifecycle>] ..."];
  for (const kind of [...groups.keys()].sort()) {
    lines.push(`[${kind}]`);
    for (const v of groups.get(kind)) lines.push(`${v.id} "${v.label}" ${v.status} ...`);
  }
  return lines.join("\n");
}
```

### Pattern 6: Delta contexts with explicit "unchanged omitted" header
**What:** iterative invocations receive only `dirty` + `removedIds` since last invocation, with a header stating so explicitly (prompt-framing risk noted in spike 006 — the model may otherwise treat the delta as the full world).
**When to use:** any repeated LLM invocation against canvas state (chat follow-ups, multi-step approval flows).
**Example:**
```ts
// Delta format per spike 006 §"Delta format" — header + changed lines + removed line
function toDelta(dirty: Set<string>, removedIds: Set<string>, byId: (id: string) => View | undefined) {
  const changed = [...dirty].map(byId).filter(Boolean);
  const header = "# pipeline_state delta — unchanged entities omitted from this context";
  const body = toCompactDsl(changed);
  const removedLine = removedIds.size ? `removed: ${[...removedIds].sort().join(",")}` : "";
  return [header, body, removedLine].filter(Boolean).join("\n");
}
```

### Pattern 7: Rewind = clear-then-restore (never in-place)
**What:** restoring a snapshot into a drifted world duplicates entities (005a's failure mode) — always clear first, then re-add, then mark everything dirty so downstream consumers observe the rewind.
**When to use:** `history.ts:restoreSnapshot()`, `approve`/`reject` rejection-path rewind.
**Example:**
```ts
// Source: .planning/spikes/008-snapshot-replay-and-rewind/history.mjs lines 38-50
export function restoreSnapshot(w, snapshotJson) {
  for (const e of [...w.world.entities]) { w.byId.delete(e.id); w.world.remove(e); }
  w.dirty.clear(); w.removedIds.clear();
  for (const rec of JSON.parse(snapshotJson)) {
    const entity = w.world.add({ ...rec, credentials: [...rec.credentials] });
    w.byId.set(rec.id, entity);
    w.dirty.add(rec.id); // downstream consumers (deltas, React Flow patch) must see the restore
  }
}
```

### Pattern 8: Redo via log replay, not inverse ops
**What:** `EventLog` records `sync`/`approve` events; redo re-runs `propose→approve` through the same mediation layer from a snapshot-ring mark, rather than maintaining inverse-operation machinery.
**Example:**
```ts
// Source: .planning/spikes/008-snapshot-replay-and-rewind/history.mjs lines 61-72
export function replayEvents(w, events) {
  for (const ev of events) {
    if (ev.type === "sync") w.syncFromPipeline(ev.payload);
    else if (ev.type === "approve") {
      const r = w.propose(ev.payload);
      if (!r.accepted) throw new Error(`replay diverged: proposal rejected: ${r.errors?.join("; ")}`);
      const a = w.approve(r.proposalId);
      if (!a.ok) throw new Error(`replay diverged: approve failed: ${a.error}`);
    }
  }
}
```
**Constraint carried forward from spike 008:** replaying `sync` events requires logging full snapshot payloads, so the real build must checkpoint (drop the log prefix at each ring snapshot) — do not let the event log grow unbounded across a session.

### Anti-Patterns to Avoid
- **Deriving `nodes` fresh from `world.entities.map()` on every `touch()`.** Confirmed: blank canvas, ~2700-4900 renders/node/sec, independent of mutation rate, breaks even at rest. Root cause (inferred): new array + new object identity every render defeats React Flow's internal measurement tracking.
- **Looping the full `changes` array in `onNodesChange` and tagging every entity as user-touched.** A real spike bug: `for (const n of next) entity.lastTouchedBy = "drag"` tagged ALL entities, not just the moved one. Diff `changes` precisely.
- **Assuming `selectedNodeId`-style XState state auto-clears on entity removal.** It does not (A/B-confirmed) — needs the explicit guard action on every `SSE_MESSAGE` transition.
- **Assuming ECS-only fields (hover, drag state) survive a remove+re-add cycle.** They don't — a fresh entity object is created with defaults, even though the "only patch mirrored fields" sync contract is honored correctly. This is a *different* failure mode than the selection-dangling one above; both guards are needed, and neither prevents the other's failure.
- **In-place snapshot restore over a drifted world.** Duplicates entities (005a). Always clear-then-restore.
- **Routing stateless per-interaction derivations (validation, highlighting, layout hints) through ECS "systems."** Measured 3x code (54 vs 17 lines) for identical correctness/performance vs a plain `resolveLifecycle`-style function. `ModuleNode.tsx`'s existing `resolveLifecycle()` (lines 79-86) is the exact convention to extend for any new per-interaction derivation this phase needs — do not wrap it in an ECS system.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ECS entity storage/querying | A custom Map-of-Maps component store | `miniplex.World` | Automatic entity hygiene on remove/recycle, full TS entity-level typing (spike 003a measurement) |
| Mutation-op schema validation | Hand-rolled field-type switch (spike-grade, seen in `mediation.mjs`) | `zod` discriminated unions | Spike 007's own README explicitly defers to zod for production; hand-rolled was scoped to prove architecture, not to ship |
| React-external-store reactivity | Polling/`setInterval` on the world | `useSyncExternalStore` + `touch()`/`subscribeWorld()` | This *is* the correct hand-rolled piece — 6 LOC, matches React 18's canonical external-store API, no library exists that does less |

**Key insight:** the parts that stay hand-rolled in this domain (snapshot serializer, dirty tracker, event log, verbalizer) are hand-rolled *because the spikes measured library alternatives losing to them* — 005a/005b invalidated bitECS's built-in serialization module for this exact role, and 006 invalidated bitECS's native delta machinery for the same reason (opaque `ArrayBuffer`s, no change-set accessor). This is the inverse of the usual "don't hand-roll" guidance: here, the spikes are the verification that hand-rolling is the tested-superior choice, not a shortcut.

## Common Pitfalls

### Pitfall 1: Next.js 14 App Router SSR and a module-level ECS singleton
**What goes wrong:** `src/ecs/world.ts` exports a module-level `const world = new World()` — if this module is ever imported into a Server Component or a file lacking `'use client'`, Next.js's App Router will attempt to construct it during server-side rendering, and the singleton will be **shared across requests on the server** (a well-known Next.js App Router footgun for any module-level mutable state) or fail outright if miniplex touches browser globals.
**Why it happens:** `page.tsx` already has `'use client'` at the top (confirmed, line 11), and `pipelinePage.ts`/`nexusStore.ts` are consumed only from client components today — but nothing currently enforces that `src/ecs/*` stays client-only as new files are added by the planner.
**How to avoid:** Put an explicit `'use client'` directive at the top of every new `src/ecs/*.ts` file that touches the `World` instance (not just the consuming component), and never import `src/ecs/world.ts` from a Server Component, a `route.ts` handler, or `generateMetadata`. `next.config.js` currently has no `experimental.serverComponentsExternalPackages` or React Server Components restriction for this — the discipline is manual.
**Warning signs:** module state resetting unexpectedly between navigations, or a build-time error referencing `window`/`document` inside `src/ecs/`.

### Pitfall 2: `reactStrictMode: true` — HMR/StrictMode double-invocation
**What goes wrong:** `next.config.js` has `reactStrictMode: true` [VERIFIED: ui_service/next.config.js line 4]. In React 18 dev mode, StrictMode double-invokes effects (mount → cleanup → mount) to surface non-idempotent effects. If `syncFromPipeline` or the snapshot-ring `push()` is called from a bare `useEffect` without cleanup-awareness, dev-mode will run it twice per SSE tick, and — critically — the **snapshot ring and event log are not naturally idempotent** (`ring.push()` appends unconditionally; `EventLog.record()` appends unconditionally).
**Why it happens:** the spikes were plain Node scripts (`.mjs`, no React runtime) or Vite dev servers without this specific interaction tested — `ui_service`'s actual `reactStrictMode: true` + Next.js 14 combination is untested by any spike.
**How to avoid:** Wire `syncFromPipeline` and any history-append call from the effect that already governs SSE ingestion (keyed on `state.context.pipeline` reference identity, which XState only replaces on genuine new data, not on StrictMode's synthetic re-invoke) rather than a raw `useEffect([])`. Confirm in an implementation task that a StrictMode double-mount does not double-append to the event log or double-push to the snapshot ring — this is an explicit gap the spikes did not close (see Open Questions).
**Warning signs:** event log length growing 2x expected during local dev; snapshot ring showing duplicate consecutive entries.

### Pitfall 3: `syncFromPipeline` dragging mid-removal (untested edge case)
**What goes wrong:** none of the spikes tested what happens if the currently-dragged node is removed mid-drag (an outright removal via `syncFromPipeline`, not a field patch). React Flow's `onNodesChange`/drag-stop write-back path assumes the dragged node still exists in `nodes` when the drag-stop `NodeChange` arrives.
**Why it happens:** explicitly flagged as an open question in `ecs-pipeline-canvas.md`'s Constraints section — "None of the spikes tested what happens if the currently-dragged node is removed mid-drag."
**How to avoid:** in the `onNodesChange` drag-stop branch, guard the ECS write-back (`entity.position = n.position`) with an existence check (`byId(c.id)` before writing) — the buffered-pattern code already does `if (n && entity)`, which is a partial guard; verify with a manual test (SSE removal fired while a node is actively being dragged) before considering this pattern production-ready.
**Warning signs:** a console error or silent no-op write to an already-removed entity during a drag interaction that overlaps an SSE tick.

### Pitfall 4: SSE remove/re-add flicker for ECS-only fields (known, deferred gap)
**What goes wrong:** a transient SSE drop (confirmed in spike 002 at a synthetic 15%-per-tick drop rate: `adding X → removing X → adding X` within ~2s) creates a brand-new entity object, silently discarding `hovered`/`dragCount`/other ECS-only fields at their defaults — even though the "only patch mirrored fields" sync contract is honored correctly.
**Why it happens:** `syncFromPipeline`'s diff (`incomingIds.has(entity.id)`) cannot distinguish transient absence from genuine removal.
**How to avoid:** CONTEXT.md explicitly defers this to Deferred Ideas ("implement if observed in production telemetry") — do not build a grace-period/debounce mechanism speculatively in this phase; document the gap in the mediation/sync module's comments (matching the spike's own documentation) and leave it.
**Warning signs:** hover highlights or drag-in-progress indicators flickering to default state without user action, correlated with dashboard/orchestrator restarts (`dashboard_service:8003` health-probe failures visible in the existing `services.orchestrator_admin` SSE field).

### Pitfall 5: c_state export — do not build a browser→backend push path
**What goes wrong:** the natural-seeming approach is "the browser has the live ECS world, so push it to the backend for the orchestrator to read." This requires the canvas tab to be open, introduces a new stateful ingestion endpoint on `dashboard_service`, and creates a staleness/ordering problem with the SSE stream the browser already consumes from the same backend.
**Why it happens:** CONTEXT.md leaves this as Claude's Discretion without prescribing the direction, and it is easy to default to "wherever the ECS world lives is the source of c_state."
**How to avoid:** Recognize that `dashboard_service/pipeline_stream.py:_build_pipeline_state()` already computes every field the ECS world's SSE-mirrored entities are built from (`services`, `modules`, `adapters`, `tools`) — confirmed by reading the endpoint. A Python-side port of `canonicalize()`/`toCompactDsl()` operating on that same dict produces an equivalent c_state with zero dependency on the browser tab being open, reusing `ContextBridge`'s existing `GET {dashboard_url}/context/...` pattern (`tools/builtin/context_bridge.py`). Add `GET /context/canvas` as a new top-level route in `dashboard_service/main.py` (sibling to `/context/{category}`, **not** routed through it — `/context/{category}`'s `valid_categories` allowlist is tied to the adapter-aggregator subsystem in `shared/context`, a different code path than `pipeline_stream.py`'s pipeline-state builder, and forcing "canvas" through it would require touching that allowlist and the `ContextBridge.normalize()` adapter map for no benefit). LLM-staged proposal state (not-yet-approved) correctly stays browser-only — the orchestrator does not need to see unapproved proposals in its context.
**Warning signs:** a design that requires "is the canvas page open" as a precondition for chat-driven context assembly to work.

### Pitfall 6: Zustand `nexusStore.ts` and XState `pipelinePageMachine` both still own real state — don't let ECS become a third owner of the same fact
**What goes wrong:** `nexusStore.ts`'s comment (line 4-9) already documents a past migration where SSE/selection ownership moved *out* of Zustand into `pipelinePageMachine` (D-14). Phase 9 risks re-introducing the same "which store is authoritative" ambiguity by having ECS entities carry fields that duplicate `pipeline.modules[].pending_approval` or `state.context.selectedNodeId` without a single clear direction of truth.
**Why it happens:** the ECS world is new and it's tempting to mirror everything defensively.
**How to avoid:** CONTEXT.md is explicit and should be treated as binding: ECS never adds/removes entities except in reaction to XState-owned SSE snapshots, and `nexusStore.ts`'s existing scope (module admin actions, test runner — see current file, 82 lines) is untouched by this phase. Do not migrate `enableModule`/`disableModule`/`runModuleTests` into ECS; those remain imperative admin-API calls exactly as they are today.
**Warning signs:** a task that proposes moving `ModuleDetail[]`/`testResult` from `nexusStore.ts` into ECS entities — out of scope per the phase boundary.

## Code Examples

Verified patterns from spike sources (all citations are exact file:line references already given inline in Architecture Patterns above). No additional Context7/official-docs lookups were needed — miniplex/zod/@xyflow/react/xstate APIs used here are already exercised correctly in the cited spike code and in `ui_service`'s existing `pipelinePage.ts`/`ModuleNode.tsx`, which is a stronger signal than isolated doc lookups for a port task.

## State of the Art

| Old Approach (Session 1 spikes 001-004, "UI store" framing) | Current Approach (Session 2 spikes 005-008, "context substrate" framing) | When Changed | Impact |
|--------------|------------------|------------------|--------|
| ECS evaluated only as a React Flow state store | ECS evaluated as tri-consumer substrate: React Flow + XState + LLM context assembler | 2026-08-23 (Session 2 reframing per *A Survey of Context Engineering for LLMs* + *LLMs as Software Components*) | The library choice (miniplex) held under the new criteria, but the *scope* of what Phase 9 builds expanded from "render sync" to "render sync + read path (verbalizer/deltas) + write path (mediation) + history (snapshot/replay)" |
| bitECS reopened as "presumptive winner" hypothesis for serialization/deltas | Hypothesis empirically invalidated on both halves (005a/b snapshots, 006 deltas) | 2026-08-23 | miniplex remains locked; do not re-litigate without a thousands-of-entities-per-frame workload |
| No LLM write path existed | Schema-validated staged proposals, 3-point re-validation, single mediation path | 2026-08-23 (spike 007) | Phase 9 must build `mediation.ts`; this did not exist in Session 1's scope at all |
| No history mechanism existed | Snapshot ring + event log, rewind = clear-then-restore, redo = replay | 2026-08-23 (spike 008) | Phase 9 must build `history.ts`; also did not exist in Session 1's scope |

**Deprecated/outdated:** none — this is a from-scratch build on a codebase with no prior ECS code (`grep` for `miniplex`/`bitecs` in `ui_service/src` returns nothing outside the spikes directory).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `GET /context/canvas` as a new top-level dashboard route (not routed through `/context/{category}`) is the right seam | Architecture Patterns, Pitfall 5 | Low — this is an additive, isolated endpoint; if wrong, the fix is routing-only and does not affect the ECS/mediation/history core of the phase |
| A2 | zod v4.4.3 (latest) has no migration friction for the discriminated-union op schemas used here | Standard Stack | Low — no existing zod usage in `ui_service` to conflict with; if a future phase needs zod v3-only syntax, this is a version-pin change, not a rework |
| A3 | StrictMode double-invocation does not double-append to the snapshot ring/event log if wiring follows the `state.context.pipeline`-keyed effect pattern already used elsewhere in `page.tsx` | Pitfall 2 | Medium — untested by any spike (all spikes ran outside React's dev-mode double-invoke path); if wrong, history/replay would silently corrupt in dev only (StrictMode is dev-only), which could mask a real duplicate-write bug that also manifests in production under a different trigger. Recommend an explicit implementation-time verification task. |
| A4 | The mid-drag removal edge case (Pitfall 3) is safe with the existing `if (n && entity)` guard in the buffered pattern | Pitfall 3 | Low-Medium — explicitly flagged unverified by the spikes themselves; recommend a manual verification task rather than blocking planning on it |

**If this table is empty:** N/A — see rows above. All other claims in this research are either `[VERIFIED]` (npm registry lookups, direct file reads of `ui_service`/`dashboard_service` source) or `[CITED]` (spike README/blueprint text, which the CONTEXT.md and skill system already established as user-verdict-approved, not re-litigated here).

## Open Questions

1. **Does the mid-drag-removal edge case (Pitfall 3) need a dedicated task, or is the existing guard sufficient?**
   - What we know: the buffered pattern already checks `if (n && entity)` before writing position back.
   - What's unclear: whether React Flow's `NodeChange` event for a node removed mid-drag even reaches `onNodesChange`, or whether the removal (via the patch effect) races the drag-stop event in a way the guard doesn't cover.
   - Recommendation: planner should add a small manual/E2E verification step (not necessarily a full task) rather than block on it — CONTEXT.md itself calls this "worth a quick check before shipping this pattern for real," not a blocker.

2. **Does the orchestrator's chat-driven approval flow for canvas proposals reuse Phase 8's `ActionCard`/`NodeDetailPanel` UI verbatim, or does it need a new review surface?**
   - What we know: Phase 8 built a full review-panel pattern (D-01 through D-19) for *module build* approval (`ModuleReview`, `BuildAuditLog`, `NodeDetailPanel`'s `reviewPanel` region). Spike 007's op vocabulary (`set_status`, `move`, `add_module`, `remove_module`, `set_credentials`) is a different, narrower kind of proposal than "approve this built module."
   - What's unclear: whether canvas-op proposals get their own lightweight approve/reject UI (e.g., a toast/inline diff) or are folded into the existing `reviewPanel` XState region as a new substate.
   - Recommendation: treat as a planning-time design decision, not a research gap — CONTEXT.md's Claude's Discretion doesn't address it directly, but the "reuse, don't rebuild" principle from Phase 8's own `code_context` section ("React Flow node set — extend, don't rebuild") should apply: extend `pipelinePageMachine`'s existing regions rather than introduce a fourth parallel region, if the shape fits.

3. **Does `GET /context/canvas` need auth (matching `ContextBridge`'s `X-API-Key` header pattern)?**
   - What we know: `ContextBridge._headers` sends `X-API-Key` when `DASHBOARD_API_KEY`/`INTERNAL_API_KEY` is set; other `/context/*` routes on `dashboard_service` do not appear to enforce auth at the FastAPI route level in the code read during this research (no `Depends(...)` auth guard visible on `/context` or `/context/{category}`).
   - What's unclear: whether Phase 1's RBAC/API-key middleware is applied globally to `dashboard_service` (via middleware, not per-route `Depends`) — this research did not read `dashboard_service/main.py`'s middleware stack in full.
   - Recommendation: the planner should verify whether dashboard-wide auth middleware already covers a new route automatically (likely, given Phase 1's "middleware rejects unauthenticated requests with 401" acceptance criterion in REQUIREMENTS.md REQ-001) before assuming a bespoke auth task is needed for `/context/canvas`.

## Environment Availability

No external service/runtime dependencies beyond what `ui_service` and `dashboard_service` already require to run (Node/npm, Python/FastAPI — both already provisioned per the existing 13-container Docker Compose stack). This phase adds only npm packages (`miniplex`, `miniplex-react`, `zod`) with no system-level installation requirements.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| npm registry access | `npm install miniplex miniplex-react zod` | ✓ | — | — |
| Python 3 (dashboard_service) | New `canvas_context.py` verbalizer port | ✓ (existing service) | matches dashboard_service's pinned version | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Playwright ^1.62.1 [VERIFIED: ui_service/package.json] (E2E only — **no unit test runner (Jest/Vitest) exists in `ui_service` today**, confirmed by absence of any `*.config.*` matching jest/vitest and zero `*.test.*`/`*.spec.*` files under `src/`) |
| Config file | `ui_service/playwright.config.ts` — runs against the live docker-compose stack (`E2E_BASE_URL`, default `http://localhost:5001`), no dev-server-launcher entry |
| Quick run command | `npx playwright test e2e/<new-spec>.spec.ts` (targeted) |
| Full suite command | `npm run e2e` (from `ui_service/`) |

### Phase Requirements → Test Map

No REQ-IDs are mapped to this phase (spike-derived, per phase scope). Test coverage is instead mapped to CONTEXT.md's locked decisions and the two Done Criteria named in the phase description (Playwright SSE-churn test, mirror-reconstruction test):

| Decision / Criterion | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| Buffered React Flow pattern (LOCKED) | Canvas stays rendered (not blank) under sustained SSE churn | E2E (Playwright, extends existing SSE reconnection suite) | `npx playwright test e2e/pipeline-sse.spec.ts` pattern, new spec file | ❌ Wave 0 — new spec needed |
| `clearSelectionIfMissing`/proposal re-validation (LOCKED) | Selection and staged proposals clear/invalidate when their target entity is removed by a new SSE snapshot | E2E or component-level (no unit runner exists — see gap below) | new Playwright spec, drives SSE state via the existing `dashboard`/mock and asserts DOM state | ❌ Wave 0 — new spec needed |
| Delta mirror-reconstruction (spike 006 claim to preserve) | An "LLM mental model" mirror rebuilt from deltas alone matches the true world at every invocation | Unit (pure function — `verbalize.ts`/`dirty.ts` have no DOM/React dependency) | **no unit runner exists** — see Wave 0 gap | ❌ Wave 0 — framework + test needed |
| Canonical text stability under churn (spike 005b claim) | `toCompactDsl()` output is byte-stable for an unchanged entity set regardless of insertion/mutation order | Unit (pure function) | same as above | ❌ Wave 0 — framework + test needed |
| Rewind = clear-then-restore, no duplication (spike 008 claim) | `restoreSnapshot()` produces exact pre-mutation state, no duplicate entities | Unit (pure function, operates on the `World` directly, no React) | same as above | ❌ Wave 0 — framework + test needed |

### Sampling Rate
- **Per task commit:** run the relevant Playwright spec (targeted) for any task touching `page.tsx`/`pipelinePage.ts`; for pure `src/ecs/*` logic, run the new unit suite once Wave 0 stands it up.
- **Per wave merge:** `npm run e2e` (full Playwright suite) — note this requires the docker-compose stack running (`make up`), per `playwright.config.ts`'s `globalSetup` fail-fast check.
- **Phase gate:** full Playwright suite green, plus the new unit suite (once added) green, before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] **Unit test runner install** — `ui_service` has zero unit-test infrastructure today (Playwright is E2E-only). The pure-function core of this phase (`verbalize.ts`, `dirty.ts`, `mediation.ts`'s `validateOp`, `history.ts`'s `restoreSnapshot`/`replayEvents`) is exactly the kind of logic the spikes validated with plain Node scripts (`node run.mjs`) — recommend **Vitest** (fast, ESM-native, zero-config with Next.js/TS via `vite-tsconfig-paths`, and the spike convention already established plain-ESM Node scripts as the fact-checking style for this exact code, `CONVENTIONS.md`). This is a judgment call (Claude's Discretion territory, not locked) — Jest is the more common Next.js pairing but has heavier ESM/TS config friction; Vitest more directly continues the spike's own "plain ESM, run with `node`/a lightweight runner" convention. Flag as `[ASSUMED]` recommendation for planner confirmation, not a locked choice.
- [ ] `ui_service/src/ecs/__tests__/verbalize.test.ts` (or `.spec.ts`, depending on runner choice) — covers canonical ordering + format stability under churn
- [ ] `ui_service/src/ecs/__tests__/dirty.test.ts` — covers delta mirror-reconstruction claim
- [ ] `ui_service/src/ecs/__tests__/history.test.ts` — covers rewind/replay determinism
- [ ] `ui_service/e2e/pipeline-ecs-churn.spec.ts` — new Playwright spec for the buffered-pattern-under-churn Done Criterion, following `e2e/pipeline-sse.spec.ts`'s existing structure (reads `E2E_BASE_URL`/`E2E_DASHBOARD_URL` from `e2e/util.ts`)
- [ ] Framework install (if Vitest chosen): `npm install -D vitest @vitest/ui` (verify exact current versions at implementation time via `npm view vitest version`)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (new surface) | N/A — `GET /context/canvas` inherits whatever auth `dashboard_service` already applies dashboard-wide (Open Question 3) |
| V3 Session Management | No | Not session-based; SSE/HTTP polling, no new session concept introduced |
| V4 Access Control | Yes (write path) | LLM mutation-op ownership policy (`OWNERSHIP` map in `mediation.ts`) enforces that LLM-authored ops may only touch `module`-kind entities, never `service`/`stage` — this is an application-level authorization control, not RBAC in the Phase 1 sense, but functions as one for the write path |
| V5 Input Validation | Yes | `zod` discriminated-union schemas (`MutationOp`) validate every LLM-authored op's shape before referential/ownership checks run — matches CONTEXT.md's LOCKED decision |
| V6 Cryptography | No | No secrets, tokens, or cryptographic material handled by this phase's new code |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM emits a mutation op targeting an entity kind outside its ownership scope (e.g., `set_status` on a `service` entity) | Elevation of Privilege | `OWNERSHIP` allow-list check in `validateOp`, enforced at all three re-validation points (proposal, sync, approval) — already locked by CONTEXT.md |
| Stale proposal race — a proposal approved after its target entity was removed by an intervening SSE snapshot | Tampering (state corruption) | Re-validation at approval time (Pattern 4) catches this even when the sync-time re-validation was missed due to timing — spike 007 T5 explicitly tested this "non-sync race" case |
| Optimistic `add_module` flicker exploited to desync UI from actual backend state | Denial of Service (UX-level, not security-critical) | Documented as a known constraint requiring pending-confirmation handling (grace period) — CONTEXT.md LOCKED decision, not a new mitigation invented here |
| `GET /context/canvas` exposing internal pipeline topology (module credential presence, adapter states) to an unauthenticated caller | Information Disclosure | Contingent on Open Question 3's resolution — if dashboard-wide auth middleware does not already cover new routes, this endpoint must not ship without it, since it exposes the same class of data (`has_credentials`, `requires_auth`) already gated on other `/admin/*` routes per Phase 1's RBAC matrix |

## Sources

### Primary (HIGH confidence)
- `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md` — full implementation blueprint with code (touch bridge, buffered pattern, sync system, selection guard)
- `.planning/spikes/MANIFEST.md` — Session 1 + Session 2 Requirements sections (binding constraints)
- `.planning/spikes/005b-world-snapshot-miniplex/README.md` + `world.mjs` + `verbalize.mjs` (shared with 006) — snapshot/verbalizer code, head-to-head verdict table
- `.planning/spikes/006-delta-context-streaming/README.md` — delta strategy, token savings measurements, bitECS delta-machinery invalidation
- `.planning/spikes/007-llm-writes-world/README.md` + `mediation.mjs` — full mediation layer source, op vocabulary, ownership policy
- `.planning/spikes/008-snapshot-replay-and-rewind/README.md` + `history.mjs` — snapshot ring, event log, rewind/replay source
- `.planning/spikes/CONVENTIONS.md` — cross-session pattern/stack conventions
- Direct reads of production source: `ui_service/src/machines/pipelinePage.ts`, `ui_service/src/app/pipeline/page.tsx`, `ui_service/src/components/pipeline/ModuleNode.tsx`, `ui_service/src/store/nexusStore.ts`, `ui_service/src/lib/adminClient.ts`, `ui_service/package.json`, `ui_service/next.config.js`, `ui_service/playwright.config.ts`, `dashboard_service/pipeline_stream.py`, `dashboard_service/main.py` (lines 440-510), `tools/builtin/context_bridge.py`
- `npm view miniplex/miniplex-react/zod version|dist-tags|repository.url|time.created` — live npm registry queries, 2026-08-23
- `slopcheck install miniplex miniplex-react zod` — live legitimacy scan, 2026-08-23

### Secondary (MEDIUM confidence)
- `.planning/phases/08-co-evolution-approval/08-CONTEXT.md` — approval-gate UI/flow this phase's write path must plug into; read in full but not re-verified against current `orchestrator/admin_api.py` implementation state (assumed unchanged since Phase 8 completion per STATE.md's Phase 6-complete/Phase 7-8 status)
- npm weekly-download counts via `api.npmjs.org` — point-in-time snapshot, not a repeated-measurement trend

### Tertiary (LOW confidence)
- None — all findings above were either verified via tool/registry query, cited from a spike README with a user-approved verdict, or cited from direct production-file reads.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified live against npm registry; slopcheck clean; no alternatives to weigh (library choice is LOCKED by CONTEXT.md)
- Architecture: HIGH — every pattern has cited, working spike source code; production integration points were read directly, not assumed
- Pitfalls: MEDIUM-HIGH — five of six pitfalls are spike-confirmed or directly observed in `ui_service` source (`reactStrictMode: true`, existing store-ownership migration history); Pitfall 3 (mid-drag removal) is explicitly spike-flagged as untested, not researcher-verified

**Research date:** 2026-08-23
**Valid until:** 2026-09-22 (30 days — stack is stable/locked by CONTEXT.md; the only fast-moving element, npm package versions, is pinned by exact verified version above and should be re-checked only if the planner delays implementation past this window)
