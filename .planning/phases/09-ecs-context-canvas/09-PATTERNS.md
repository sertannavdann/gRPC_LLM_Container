# Phase 9: ECS Context-Substrate Canvas - Pattern Map

**Mapped:** 2026-08-23
**Files analyzed:** 13 (6 new `ui_service/src/ecs/*`, 3 new unit test files, 1 new Playwright spec, 1 new Python backend file, 2 modified production files)
**Analogs found:** 13 / 13 (all files have either a direct spike source port or a production codebase analog; two files use both)

This phase is a **port task**, not a from-scratch design task. Every `src/ecs/*` file has a
byte-adjacent spike source file that is reference-quality per RESEARCH.md — the "analog" for
those files is the spike source itself (cited file:line), with a secondary production analog
for TypeScript/React-specific conventions (client-directive placement, import style, naming).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `ui_service/src/ecs/world.ts` | model (ECS store + reactivity bridge) | event-driven | `.planning/spikes/005b-world-snapshot-miniplex/world.mjs` + `.claude/skills/.../ecs-pipeline-canvas.md` touch bridge | exact (spike port) |
| `ui_service/src/ecs/sync.ts` | service (single SSE writer) | event-driven | `.planning/spikes/007-llm-writes-world/mediation.mjs` `syncFromPipeline` (lines 77-95) | exact (spike port) |
| `ui_service/src/ecs/dirty.ts` | utility (choke-point dirty tracker) | transform | `.planning/spikes/006-delta-context-streaming/run.mjs` lines 24-57 | exact (spike port) |
| `ui_service/src/ecs/verbalize.ts` | utility (canonical DSL formatter) | transform | `.planning/spikes/006-delta-context-streaming/verbalize.mjs` (byte-identical to 005b) + `run.mjs` lines 59-67 (delta variant) | exact (spike port) |
| `ui_service/src/ecs/mediation.ts` | service (LLM write-path, staged proposals) | event-driven | `.planning/spikes/007-llm-writes-world/mediation.mjs` (full file, adapt `validateOp`→zod) | exact (spike port) |
| `ui_service/src/ecs/history.ts` | service (snapshot ring + event log) | event-driven / batch | `.planning/spikes/008-snapshot-replay-and-rewind/history.mjs` (full file) | exact (spike port) |
| `ui_service/src/ecs/__tests__/verbalize.test.ts` | test (unit) | transform | `.planning/spikes/005b-world-snapshot-miniplex/run.mjs` (assertions on canonical ordering/stability — spike's own fact-check style) | exact (spike test logic port, new Vitest wrapper) |
| `ui_service/src/ecs/__tests__/dirty.test.ts` | test (unit) | transform | `.planning/spikes/006-delta-context-streaming/run.mjs` lines 69-100+ (mirror-reconstruction check) | exact (spike test logic port) |
| `ui_service/src/ecs/__tests__/history.test.ts` | test (unit) | transform | `.planning/spikes/008-snapshot-replay-and-rewind/run.mjs` (rewind/replay determinism assertions) | exact (spike test logic port) |
| `ui_service/e2e/pipeline-ecs-churn.spec.ts` | test (E2E, Playwright) | event-driven | `ui_service/e2e/pipeline-sse.spec.ts` (full file — structure, `util.ts` imports, non-disruptive-by-default pattern) | exact (production analog) |
| `ui_service/src/machines/pipelinePage.ts` (MODIFIED) | machine (XState v5 guard action) | event-driven | itself — `clearSelection` action (lines 142-148) + `SSE_MESSAGE` transition wiring (lines 192, 197, 203) is the existing precedent for the new action | exact (self-analog, extend in place) |
| `ui_service/src/app/pipeline/page.tsx` (MODIFIED) | component (buffered React Flow patch) | event-driven | `.claude/skills/.../ecs-pipeline-canvas.md` buffered pattern (lines 79-107) as the target shape; itself lines 140-311 as the code being replaced | exact (spike pattern replaces self's current effect) |
| `dashboard_service/canvas_context.py` (NEW) | utility (Python verbalizer port) + route handler | request-response | `.planning/spikes/006-delta-context-streaming/verbalize.mjs` (port target) + `dashboard_service/formatters.py` (Python module-style analog) + `dashboard_service/main.py` `get_category_context` (route pattern, lines 473-504) | exact (spike port) + role-match (route/module style) |

## Pattern Assignments

### `ui_service/src/ecs/world.ts` (model, event-driven)

**Analog:** `.planning/spikes/005b-world-snapshot-miniplex/world.mjs` (full file, 58 lines) + skill blueprint's reactivity bridge

**Core pattern — miniplex World adapter** (`world.mjs` lines 11-38, port verbatim, add TS types):
```ts
import { World } from "miniplex";

export function createPipelineWorld() {
  const world = new World();
  const byId = new Map<string, /* Entity */ any>();

  function add(rec: EntityRecord) {
    const entity = world.add({
      id: rec.id, label: rec.label, kind: rec.kind, status: rec.status,
      lifecycle: rec.lifecycle, cpu: rec.cpu, mem: rec.mem, x: rec.x, y: rec.y,
      credentials: [...rec.credentials],
    });
    byId.set(rec.id, entity);
    return entity;
  }

  function remove(id: string) {
    const entity = byId.get(id);
    if (!entity) return;
    world.remove(entity);
    byId.delete(id);
  }

  function views() {
    return [...world.entities].map((e) => ({ ...e, credentials: [...e.credentials] }));
  }

  return { world, byId, add, remove, views };
}
```

**Reactivity bridge — mandatory, not trimmable** (from `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md` lines 47-71, port verbatim):
```ts
'use client'; // MANDATORY on this file — Pitfall 1 (Next.js App Router SSR footgun)
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

**Critical constraint (Pitfall 1):** every file in `src/ecs/` that imports `world.ts` must carry
an explicit `'use client'` directive at its own top — do not rely on `page.tsx`'s directive
propagating implicitly.

---

### `ui_service/src/ecs/sync.ts` (service, event-driven)

**Analog:** `.planning/spikes/007-llm-writes-world/mediation.mjs` lines 63-95 (the `add`/`removeById`/`syncFromPipeline` trio — this is the ONE writer contract)

**Core pattern — sync + choke-point add/remove + proposal re-validation** (adapt `mediation.mjs` lines 63-95):
```ts
const add = (rec: EntityRecord) => {
  const e = world.add({ ...rec, credentials: [...rec.credentials] });
  byId.set(rec.id, e); dirty.add(rec.id); removedIds.delete(rec.id);
  return e;
};
const removeById = (id: string) => {
  const e = byId.get(id);
  if (!e) return;
  world.remove(e); byId.delete(id); dirty.delete(id); removedIds.add(id);
};

function syncFromPipeline(snapshotRecs: EntityRecord[]) {
  const incoming = new Set(snapshotRecs.map((r) => r.id));
  for (const e of [...world.entities]) if (!incoming.has(e.id)) removeById(e.id);
  for (const rec of snapshotRecs) {
    const existing = byId.get(rec.id);
    if (existing) {
      if (existing.status !== rec.status) { existing.status = rec.status; dirty.add(rec.id); }
      // ...other mirrored-field diffs
    } else add(rec);
  }
  touch();
}
```

**Ownership rule (CONTEXT.md LOCKED):** this is the ONLY function permitted to call
`world.add`/`world.remove` in reaction to SSE data. Never call `add`/`remove` from
`mediation.ts`'s SSE-facing code path except through this same choke point.

**Wire from:** a `useEffect` keyed on `state.context.pipeline` (the XState machine's SSE-derived
context field) inside `page.tsx` — not a raw `useEffect([])` (Pitfall 2, StrictMode double-invoke).

---

### `ui_service/src/ecs/dirty.ts` (utility, transform)

**Analog:** `.planning/spikes/006-delta-context-streaming/run.mjs` lines 24-57 ("the ENTIRE tracker is ~20 lines")

**Core pattern — choke-point dirty/removed Sets** (port verbatim, extract from `sync.ts`'s add/remove/mutate into a shared module both `sync.ts` and `mediation.ts` import):
```ts
export function createDirtyTracker() {
  const dirty = new Set<string>();     // logical ids changed/added since last invocation
  const removedIds = new Set<string>(); // logical ids removed since last invocation

  function markDirty(id: string) { dirty.add(id); removedIds.delete(id); }
  function markRemoved(id: string) { dirty.delete(id); removedIds.add(id); }
  function clear() { dirty.clear(); removedIds.clear(); }

  return { dirty, removedIds, markDirty, markRemoved, clear };
}
```
Note: the spike inlines dirty-tracking directly into `add`/`remove`/`mutate` (run.mjs lines 30-50)
rather than as a separate module — CONTEXT.md's Claude's Discretion suggests a dedicated
`dirty.ts` file; either inline (matching spike exactly) or extracted-and-shared (matching
CONTEXT.md's suggested layout) is acceptable, but `world.ts`'s `add`/`remove` and
`mediation.ts`'s `approve`/`add`/`removeById` must call into the SAME instance — do not create
two independent dirty Sets.

---

### `ui_service/src/ecs/verbalize.ts` (utility, transform)

**Analog:** `.planning/spikes/006-delta-context-streaming/verbalize.mjs` (full file, byte-identical to 005b's `verbalize.mjs`) + `run.mjs` lines 59-67 for the delta variant

**Core pattern — canonicalize + compact DSL** (port verbatim, this is THE format per CONTEXT.md LOCKED decision — 2.9x token savings over pretty JSON):
```ts
export function canonicalize<T extends { id: string }>(views: T[]): T[] {
  return [...views].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

export function toCompactDsl(views: View[]): string {
  const rows = canonicalize(views);
  const groups = new Map<string, View[]>();
  for (const v of rows) {
    if (!groups.has(v.kind)) groups.set(v.kind, []);
    groups.get(v.kind)!.push(v);
  }
  const lines = [
    '# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>] cpu=<pct> mem=<MB> @(<x>,<y>)[ creds:<list>]',
  ];
  for (const kind of [...groups.keys()].sort()) {
    lines.push(`[${kind}]`);
    for (const v of groups.get(kind)!) {
      let line = `${v.id} "${v.label}" ${v.status}`;
      if (v.lifecycle) line += `/${v.lifecycle}`;
      line += ` cpu=${v.cpu} mem=${v.mem} @(${v.x},${v.y})`;
      if (v.credentials.length) line += ` creds:${v.credentials.join(',')}`;
      lines.push(line);
    }
  }
  return lines.join('\n');
}
```

**Delta variant with "unchanged omitted" header** (port from `run.mjs` lines 60-67 — CONTEXT.md
explicitly flags this framing risk, keep the header wording):
```ts
export function toDelta(dirty: Set<string>, removedIds: Set<string>, viewOf: (id: string) => View | null) {
  const changed = [...dirty].map(viewOf).filter((v): v is View => v !== null);
  const lines = ['# pipeline_state DELTA — unchanged entities omitted'];
  if (removedIds.size) lines.push(`removed: ${[...removedIds].sort().join(',')}`);
  if (changed.length) lines.push(toCompactDsl(changed).split('\n').slice(1).join('\n')); // drop verbalizer's own header
  else if (!removedIds.size) lines.push('(no changes)');
  return { text: lines.join('\n'), changed, removed: [...removedIds] };
}
```

**Do NOT skip `canonicalize()`** — insertion order and numeric entity ids are not stable
across churn in miniplex; sort-by-logical-id is what makes output byte-stable (test target for
`verbalize.test.ts`).

---

### `ui_service/src/ecs/mediation.ts` (service, event-driven)

**Analog:** `.planning/spikes/007-llm-writes-world/mediation.mjs` (full file, 154 lines — adapt `validateOp`'s hand-rolled type-switch to `zod`, keep everything else, including the ownership map and the three re-validation call sites, unchanged)

**Zod schema replacing hand-rolled `OPS`/`validateOp` field checks** (per RESEARCH.md Pattern 3, `mediation.mjs` lines 17-23 is the field/kind vocabulary to encode in zod):
```ts
import { z } from 'zod';

const StatusEnum = z.enum(STATUSES as [string, ...string[]]);

const SetStatusOp = z.object({ op: z.literal('set_status'), id: z.string(), value: StatusEnum });
const SetCredentialsOp = z.object({ op: z.literal('set_credentials'), id: z.string(), list: z.array(z.string()) });
const MoveOp = z.object({ op: z.literal('move'), id: z.string(), x: z.number(), y: z.number() });
const AddModuleOp = z.object({
  op: z.literal('add_module'),
  rec: z.object({ id: z.string().startsWith('mod-'), label: z.string(), status: StatusEnum }),
});
const RemoveModuleOp = z.object({ op: z.literal('remove_module'), id: z.string() });

export const MutationOp = z.discriminatedUnion('op', [
  SetStatusOp, SetCredentialsOp, MoveOp, AddModuleOp, RemoveModuleOp,
]);

// Ownership policy — checked against the LIVE world, separate from schema validity:
const OWNERSHIP: Record<string, string[]> = {
  set_status: ['service', 'module', 'stage'],
  set_credentials: ['module'],
  move: ['service', 'module', 'stage'],
  add_module: ['module'],
  remove_module: ['module'],
};
```

**Keep the referential + ownership checks from `mediation.mjs` lines 42-51 as a second-pass
check AFTER `MutationOp.safeParse(op)` succeeds** — schema validity and ownership/referential
validity are separate concerns, both required before a proposal is `accepted`.

**Three re-validation points (CONTEXT.md LOCKED, `mediation.mjs` lines 87-94, 131-134):**
```ts
// 1. Inside syncFromPipeline, immediately after the add/remove/mirror loop:
for (const [pid, p] of proposals) {
  if (p.status !== 'staged') continue;
  for (const op of p.ops) {
    const v = MutationOp.safeParse(op);
    if (!v.success || !ownershipOk(op, byId)) { p.status = 'invalidated'; p.reason = /* ... */; break; }
  }
}
```
Port `propose()` (lines 98-108), `previewViews()` (lines 111-123), `approve()` (lines 127-144),
and `reject()` (lines 146-151) verbatim — these four functions ARE the single mediation path;
do not fork a second implementation for SSE-vs-LLM writers.

**Ownership constraint (SECURITY, CONTEXT.md LOCKED + RESEARCH.md V4 Access Control):** LLM ops
may only target `module`-kind entities except `move`/`set_status` which also permit
`service`/`stage` per the `OWNERSHIP` map above — do not widen this without a corresponding
CONTEXT.md decision update.

---

### `ui_service/src/ecs/history.ts` (service, event-driven/batch)

**Analog:** `.planning/spikes/008-snapshot-replay-and-rewind/history.mjs` (full file, 73 lines — port verbatim including comments, this is the exact target shape)

**Snapshot ring** (`history.mjs` lines 15-35):
```ts
export function createSnapshotRing(capacity: number) {
  const ring: { label: string; json: string; bytes: number }[] = [];
  return {
    push(label: string, worldViews: View[]) {
      const json = JSON.stringify(canonicalize(worldViews));
      ring.push({ label, json, bytes: new TextEncoder().encode(json).length }); // Buffer→TextEncoder for browser
      if (ring.length > capacity) ring.shift();
    },
    get(label: string) {
      for (let i = ring.length - 1; i >= 0; i--) if (ring[i].label === label) return ring[i];
      return null;
    },
    at(offsetFromHead: number) { return ring[ring.length - 1 + offsetFromHead] ?? null; },
    totalBytes: () => ring.reduce((s, r) => s + r.bytes, 0),
    size: () => ring.length,
  };
}
```
**Node-to-browser adaptation note:** the spike uses `Buffer.byteLength(json, 'utf8')` (line 22)
— this is Node-only. Replace with `new TextEncoder().encode(json).length` in the browser port.

**Rewind = clear-then-restore, NEVER in-place** (`history.mjs` lines 38-50, port verbatim — 005a
proved in-place restore over a drifted world duplicates entities):
```ts
export function restoreSnapshot(w: MediatedWorld, snapshotJson: string) {
  for (const e of [...w.world.entities]) { w.byId.delete(e.id); w.world.remove(e); }
  w.dirty.clear(); w.removedIds.clear();
  for (const rec of JSON.parse(snapshotJson)) {
    const entity = w.world.add({ ...rec, credentials: [...rec.credentials] });
    w.byId.set(rec.id, entity);
    w.dirty.add(rec.id); // downstream consumers (deltas, React Flow patch) must see the restore
  }
  touch(); // NEW vs spike: browser port must call touch() so useSyncExternalStore observes restore
}
```

**Event log + replay** (`history.mjs` lines 52-72, port verbatim):
```ts
export function createEventLog() {
  const events: { seq: number; type: string; payload: unknown }[] = [];
  return {
    record(type: string, payload: unknown) { events.push({ seq: events.length, type, payload }); },
    slice: (from = 0, to = events.length) => events.slice(from, to),
    length: () => events.length,
  };
}

export function replayEvents(w: MediatedWorld, events: LoggedEvent[]) {
  for (const ev of events) {
    if (ev.type === 'sync') w.syncFromPipeline(ev.payload as EntityRecord[]);
    else if (ev.type === 'approve') {
      const r = w.propose((ev.payload as { ops: MutationOpT[] }).ops);
      if (!r.accepted) throw new Error(`replay diverged: proposal rejected: ${r.errors?.join('; ')}`);
      const a = w.approve(r.proposalId!);
      if (!a.ok) throw new Error(`replay diverged: approve failed: ${a.error}`);
    }
  }
}
```
**Unbounded-growth constraint (carried forward from spike 008 README):** the real build must
checkpoint (drop the log prefix at each ring snapshot push) — do not let `EventLog` grow
unbounded across a page-lifetime session.

---

### `ui_service/src/ecs/__tests__/*.test.ts` (test, unit — Vitest, per RESEARCH.md Wave 0 recommendation)

**Analog:** the spike `run.mjs` files themselves — they ARE the test logic (plain-ESM Node
assertion scripts), just not wrapped in a test-runner's `describe`/`it`. Port the assertion
LOGIC, wrap in Vitest syntax.

- `verbalize.test.ts` — assert `toCompactDsl()` output is byte-identical across insertion-order
  permutations of the same entity set (canonical-text-stability claim, 005b). Analog: `run.mjs`
  in `005b-world-snapshot-miniplex` (format-stability check).
- `dirty.test.ts` — assert an LLM-mental-model "mirror" `Map` rebuilt from
  `applyDeltaToMirror(delta)` calls alone matches `canonicalize(world.views())` at every
  invocation (mirror-reconstruction claim, 006). Direct port of `run.mjs` lines 74-85 in
  `006-delta-context-streaming` (`applyFullToMirror`/`applyDeltaToMirror`/`mirrorEquals`).
- `history.test.ts` — assert `restoreSnapshot()` produces exact pre-mutation state with no
  duplicate entities (rewind-no-duplication claim, 008). Analog: `run.mjs` in
  `008-snapshot-replay-and-rewind`.

**No production Vitest config exists yet** — this is a Wave-0 framework-install task (RESEARCH.md
"Wave 0 Gaps"), not a pattern-port. Use `vite-tsconfig-paths` so `@/*` resolves consistently
with `ui_service/tsconfig.json`'s existing `paths` block.

---

### `ui_service/e2e/pipeline-ecs-churn.spec.ts` (test, E2E)

**Analog:** `ui_service/e2e/pipeline-sse.spec.ts` (full file, 116 lines — structure, imports, and non-disruptive-by-default convention to replicate exactly)

**Imports/structure pattern** (lines 20-30):
```ts
import { test, expect } from '@playwright/test';
import { execSync } from 'node:child_process';
import { DASHBOARD_COMPOSE_SERVICE } from './util';

const ALLOW_RESTART = Boolean(process.env.E2E_ALLOW_RESTART);
```

**Core assertion pattern to extend for the churn/buffered-pattern Done Criterion** (mirrors
lines 31-37's shape — assert both the toolbar text AND the canvas DOM element, never just one):
```ts
test('canvas survives sustained SSE churn without going blank', async ({ page }) => {
  await page.goto('/pipeline');
  await expect(page.getByText('Live')).toBeVisible();
  await expect(page.locator('.react-flow')).toBeVisible();
  // ... drive several SSE ticks (the REAL dashboard SSE stream, 2s interval —
  // do NOT mock/intercept EventSource per pipeline-sse.spec.ts's own Pitfall-4 note ...
  await expect(page.locator('.react-flow')).toBeVisible(); // still rendered, not blank
  await expect(page.locator('.react-flow__node').first()).toBeVisible();
});
```
**Non-mocking constraint carried forward:** `pipeline-sse.spec.ts`'s own header comment (lines
6-9) documents that Playwright's request-interception API does not reliably deliver events to
`EventSource` — this churn spec must also run against the real dashboard SSE endpoint, not a
mocked one. Reuse `E2E_BASE_URL`/`E2E_DASHBOARD_URL` from `./util.ts` if the spec needs to
directly observe backend state.

---

### `ui_service/src/machines/pipelinePage.ts` (MODIFIED — machine, event-driven)

**Analog:** itself — the existing `clearSelection` action (lines 142-148) is the *shape* to
follow; the NEW action generalizes the skill blueprint's `clearSelectionIfMissing`
(`ecs-pipeline-canvas.md` lines 140-146).

**Existing precedent for an assign-action reacting to SSE_MESSAGE-adjacent state** (lines 129-148):
```ts
updatePipeline: assign(({ event }) => {
  if (event.type !== 'SSE_MESSAGE') return {};
  return { pipeline: event.data, lastUpdate: Date.now() };
}),
// ...
clearSelection: assign(() => ({
  selectedNodeId: null, selectedModuleId: null, review: null, audit: [], actionError: null,
})),
```

**New guard action to add** (per skill blueprint lines 140-146, adapted to this machine's actual
context shape — note `PipelinePageContext.selectedNodeId`/`pipeline` already exist, no new
context fields needed for this specific action):
```ts
clearSelectionIfMissing: assign(({ context, event }) => {
  if (event.type !== 'SSE_MESSAGE') return {};
  const stillPresent = /* derive node-id set from event.data — services/modules/adapters/tools,
                           whatever page.tsx's node-id-building logic (lines 149-307) treats as
                           the authoritative id space */ true;
  if (context.selectedNodeId && !stillPresent) return { selectedNodeId: null };
  return {};
}),
```

**Wiring — add to ALL THREE `SSE_MESSAGE` transitions** (lines 192, 197, 203 — exactly where
`updatePipeline` is currently the sole action):
```ts
connecting: { on: { SSE_MESSAGE: { target: 'connected', actions: ['updatePipeline', 'clearSelectionIfMissing'] } } },
connected: { on: { SSE_MESSAGE: { actions: ['updatePipeline', 'clearSelectionIfMissing'] }, SSE_ERROR: 'reconnecting' } },
reconnecting: { on: { SSE_MESSAGE: { target: 'connected', actions: ['updatePipeline', 'clearSelectionIfMissing'] } } },
```

**Scope note (RESEARCH.md Pattern 4):** this XState-side guard is a SEPARATE, SMALLER action
from the ECS mediation layer's proposal re-validation (`mediation.ts`'s `syncFromPipeline`
proposal loop) — `selectedNodeId` lives in XState context, proposals live in the ECS world; do
not conflate the two guards into one action.

---

### `ui_service/src/app/pipeline/page.tsx` (MODIFIED — component, event-driven)

**Analog:** `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md` lines
79-107 (buffered pattern, the TARGET shape) — replaces this file's OWN current pipeline-rebuild
effect (lines 140-311, the code being REPLACED, not an external analog).

**What stays unchanged:** `useNodesState`/`useEdgesState` ownership (line 107-108), `nodeTypes`
map (lines 40-46), `onNodeClick` → `send({type:'SELECT_NODE', ...})` (lines 118-127),
`NodeDetailPanel` wiring (lines 395-408), `STAGE_NODES`/`STAGE_EDGES` static scaffolding
(lines 49-60) — Phase 9 inserts the ECS layer BETWEEN the SSE `pipeline` object and the existing
`setNodes`/`setEdges` calls, it does not touch the static-node layout code or the review-panel
wiring.

**What changes — replace the useEffect at lines 140-311.** Today it derives `dynamicNodes`
fresh from `pipeline` on every SSE tick and calls `setNodes(dynamicNodes)` wholesale (a full
replace, line 309) — CONTEXT.md's buffered-pattern requirement forbids this exact shape once
ECS is inserted (a fresh array on every `touch()` breaks React Flow rendering outright per
RESEARCH.md's Anti-Patterns section). New shape (adapt skill blueprint lines 84-91,
keyed on ECS `version` via `useSyncExternalStore` instead of `[pipeline]`):
```tsx
const version = useSyncExternalStore(subscribeWorld, getWorldVersion);

// One-time/pipeline-shape-change effect: still builds STAGE_NODES + calls syncFromPipeline
// (the ECS choke point) instead of building React Flow nodes directly.
useEffect(() => {
  if (!pipeline) return;
  syncFromPipeline(toEntityRecords(pipeline)); // the ONE writer — see sync.ts
}, [pipeline]);

// Patch effect: keyed on ECS version, patches nodes[] by id — NEVER setNodes(freshArray).
useEffect(() => {
  setNodes((prev) => prev.map((n) => {
    const e = byId(n.id);
    if (!e) return n;
    if (n.data.status === e.status /* && other mirrored fields unchanged */) return n;
    return { ...n, data: { ...n.data, status: e.status /* ... */ } };
  }));
}, [version]);
```

**`onNodesChange` drag-stop write-back** (skill blueprint lines 93-106, NEW code — today's
`page.tsx` uses the RF-generated `onNodesChange` directly at line 370 with no ECS write-back):
```tsx
const onNodesChange = useCallback((changes: NodeChange[]) => {
  for (const c of changes) {
    if (c.type === 'position') {
      if (c.dragging) draggingId.current = c.id;
      else {
        draggingId.current = null;
        const n = nodes.find((n) => n.id === c.id);
        const entity = byId(c.id);
        if (n && entity) entity.position = n.position; // write back ONLY on drag-stop
      }
    }
  }
  onNodesChangeRF(changes);
}, [nodes, onNodesChangeRF]);
```
**Unverified edge case (Pitfall 3, RESEARCH.md A4):** the `if (n && entity)` guard above is the
full extent of spike-tested protection against a node being removed mid-drag — flag for manual
verification, do not treat as fully proven.

---

### `dashboard_service/canvas_context.py` (NEW — utility + route handler, request-response)

**Analog 1 (verbalizer port target):** `.planning/spikes/006-delta-context-streaming/verbalize.mjs` (full file — `canonicalize()`/`toCompactDsl()`, port to Python 1:1)

**Analog 2 (Python module style):** `dashboard_service/formatters.py` lines 1-37 (module
docstring convention, plain-function-per-concern style, `Dict[str, Any]` typing convention —
NOT a structural pattern to copy since `formatters.py` builds prose summaries while
`canvas_context.py` builds a compact DSL, but the file-header/typing/docstring CONVENTIONS
should match):
```python
"""
Canvas Context Verbalizer — Python port of ui_service/src/ecs/verbalize.ts's
canonicalize()/toCompactDsl(), operating on the same dict
dashboard_service/pipeline_stream.py:_build_pipeline_state() already produces for
the SSE stream. Exposed via GET /context/canvas (dashboard_service/main.py) for
orchestrator context assembly — works with no browser tab open (see 09-RESEARCH.md
Pitfall 5).

Canonical ordering rule: sort by logical string id (same rule as the TS verbalizer;
insertion order / dict key order is not stable across dashboard restarts).
"""
from typing import Any, Dict, List


def canonicalize(views: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(views, key=lambda v: v["id"])


def to_compact_dsl(views: List[Dict[str, Any]]) -> str:
    rows = canonicalize(views)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for v in rows:
        groups.setdefault(v["kind"], []).append(v)
    lines = [
        '# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>] cpu=<pct> mem=<MB> @(<x>,<y>)[ creds:<list>]'
    ]
    for kind in sorted(groups.keys()):
        lines.append(f"[{kind}]")
        for v in groups[kind]:
            line = f'{v["id"]} "{v["label"]}" {v["status"]}'
            if v.get("lifecycle"):
                line += f'/{v["lifecycle"]}'
            line += f' cpu={v["cpu"]} mem={v["mem"]} @({v["x"]},{v["y"]})'
            if v.get("credentials"):
                line += f' creds:{",".join(v["credentials"])}'
            lines.append(line)
    return "\n".join(lines)
```
**Data-source adapter note:** `_build_pipeline_state()`'s dict shape (`services`, `modules`,
`adapters`, `tools` — see `dashboard_service/pipeline_stream.py` lines 309-317) is NOT already
the flat `{id, label, kind, status, ...}` "view" record shape the verbalizer expects — a small
adapter function (in this same file) must flatten `services`/`modules`/`adapters` dicts/lists
into that view shape before calling `to_compact_dsl()`, analogous to how `sync.ts`'s
`syncFromPipeline` on the TS side treats `PipelineState` as its own separate shape from the ECS
entity record.

**Route pattern to copy — `GET /context/{category}`** (`dashboard_service/main.py` lines
473-504, closest role+data-flow match among existing routes):
```python
@app.get("/context/{category}", tags=["Context"])
async def get_category_context(
    category: str,
    user_id: str = Query(default="default", description="User identifier"),
    force_refresh: bool = Query(default=False, description="Bypass cache"),
):
    ...
    try:
        aggregator = get_aggregator(user_id)
        data = await aggregator.get_category_data(category=category, force_refresh=force_refresh)
        return {"category": category, "user_id": user_id, "data": data}
    except Exception as e:
        logger.error(f"Error fetching {category} for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```
**Do NOT route `/context/canvas` through this handler or its `valid_categories` allowlist**
(RESEARCH.md Pitfall 5, explicit) — add a new SIBLING top-level route in `main.py`:
```python
@app.get("/context/canvas", tags=["Context"])
async def get_canvas_context():
    """
    c_state for the pipeline canvas — canonical compact-DSL verbalization of the
    same dict _build_pipeline_state() computes for the SSE stream. No dependency
    on a browser canvas tab being open (09-RESEARCH.md Pitfall 5).
    """
    from dashboard_service.pipeline_stream import _build_pipeline_state
    from dashboard_service.canvas_context import to_compact_dsl, pipeline_state_to_views
    state = await _build_pipeline_state(app)
    return {"c_state": to_compact_dsl(pipeline_state_to_views(state)), "timestamp": state["timestamp"]}
```
**IMPORTANT — place this route BEFORE `@app.get("/context/{category}")`** in `main.py`'s route
registration order, or FastAPI's path-param route will greedily match `/context/canvas` as
`category="canvas"` first (path-ordering footgun, not spike-covered — verify at implementation
time with a manual request).

**Auth — resolved, no new task needed (Open Question 3 answered):** `shared/auth/middleware.py`
`APIKeyAuthMiddleware.dispatch` (lines 51-55) does PREFIX matching: `path == public or
path.startswith(public + "/")`. Since `"/context"` is already in `main.py`'s `public_paths` list
(line 335), `/context/canvas` automatically matches `"/context" + "/"` and is already public —
**no explicit auth wiring task is required**, but this DOES mean `/context/canvas` is
unauthenticated exactly like `/context/{category}` already is; if this endpoint later needs to
be gated (RESEARCH.md's Information Disclosure threat note on `has_credentials`/
`requires_auth`), that is a deliberate `public_paths` edit, not an oversight to "fix" during
this phase.

---

## Shared Patterns

### Client-only ECS module boundary (Pitfall 1)
**Source:** `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md` + confirmed via `ui_service/src/app/pipeline/page.tsx` line 11 (`'use client'`)
**Apply to:** every file under `ui_service/src/ecs/*.ts` that imports or constructs the `World`
**Rule:** explicit `'use client'` at the top of EVERY such file, not just the consuming
component. Never import `src/ecs/world.ts` from a Server Component, `route.ts` handler, or
`generateMetadata`.

### Single mediation path — one world, two writers
**Source:** `.planning/spikes/007-llm-writes-world/mediation.mjs` (whole file architecture)
**Apply to:** `sync.ts` + `mediation.ts` — both must call the SAME `add`/`removeById`/dirty-Set
instance exported from (or closed over by) `world.ts`/`mediation.ts`'s `createMediatedWorld()`.
Do not instantiate a second `World()` or a second dirty `Set` anywhere.

### `useSyncExternalStore` + `touch()` reactivity bridge
**Source:** `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md` lines 47-71
**Apply to:** `page.tsx`'s patch effect, and any future component reading live ECS state
**Rule:** never derive React Flow's `nodes` fresh from `world.entities.map()` — patch by id only.

### Canonical sort-by-id before any serialization
**Source:** `.planning/spikes/006-delta-context-streaming/verbalize.mjs` lines 12-14 (TS side) — port identically to `canvas_context.py` (Python side)
**Apply to:** `verbalize.ts`, `history.ts`'s `SnapshotRing.push`, `canvas_context.py` — every
place a set of entities is turned into text or JSON for comparison/storage.

### Ownership/RBAC for LLM-authored writes
**Source:** `.planning/spikes/007-llm-writes-world/mediation.mjs` lines 17-23, 42-51 (`OWNERSHIP`-equivalent `OPS[op].kinds` check)
**Apply to:** `mediation.ts`'s `validateOp`/zod-based equivalent — enforced at all 3 points (propose, sync, approve), never bypassed for a "trusted" caller.

### Error/degrade-never-raise convention (backend)
**Source:** `dashboard_service/pipeline_stream.py` `_build_pending_approval_list` (lines 192-233, "must never raise... degrade to [] on any unexpected failure") and `_build_stage_index` (lines 147-189, same contract)
**Apply to:** `canvas_context.py` — the new `pipeline_state_to_views()` adapter and `to_compact_dsl()` call inside `get_canvas_context()` should follow the same never-raise-during-a-2s-cycle discipline already established for every other function `_build_pipeline_state()` calls, since this route reuses that same builder.

## No Analog Found

None — every planned file has at least one direct spike-source or production-codebase analog (see table above). The two lowest-confidence items are flagged inline, not listed here as gaps:
- Vitest framework install itself has no in-repo analog (RESEARCH.md Wave 0 gap — `ui_service` has zero unit-test infrastructure today); the spike `run.mjs` scripts are the closest "logic" analog even though the runner is new.
- `dashboard_service/canvas_context.py`'s `pipeline_state_to_views()` adapter function (flattening `_build_pipeline_state()`'s `services`/`modules`/`adapters` shape into verbalizer "view" records) has no existing Python analog to copy structurally — it is new glue code, sized similarly to `_build_adapter_list`/`_build_tool_list` in `pipeline_stream.py` (lines 104-144), which are the nearest shape/size reference even though they solve a different transform.

## Metadata

**Analog search scope:** `.planning/spikes/005b-world-snapshot-miniplex/`, `.planning/spikes/006-delta-context-streaming/`, `.planning/spikes/007-llm-writes-world/`, `.planning/spikes/008-snapshot-replay-and-rewind/`, `.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md`, `ui_service/src/machines/`, `ui_service/src/app/pipeline/`, `ui_service/src/components/pipeline/`, `ui_service/src/store/`, `ui_service/e2e/`, `dashboard_service/*.py`, `shared/auth/middleware.py`, `tools/builtin/context_bridge.py`
**Files scanned:** ~24 (13 spike/skill source files fully read, 8 production files fully or partially read, 3 auth/bridge/test files for the backend seam)
**Pattern extraction date:** 2026-08-23
