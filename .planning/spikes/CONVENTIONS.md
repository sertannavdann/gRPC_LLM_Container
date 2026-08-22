# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these unless the
question requires otherwise.

## Stack

- **Frontend spikes:** Vite + React 18 + TypeScript, one spike = one standalone `npm` package
  under `.planning/spikes/NNN-name/` (own `package.json`, own dev server port in the 53xx range
  so multiple spikes can run concurrently without colliding).
- **ECS:** miniplex (not bitECS) — see `003a-ecs-lib-miniplex` / `003b-ecs-lib-bitecs`. Only
  reconsider bitECS if a future spike genuinely needs thousands of numeric entities in a
  per-frame loop; NEXUS's UI domains so far are dozens of entities with string-heavy data.
- **Canvas/graph rendering:** `@xyflow/react` (React Flow v12), matching `ui_service`'s existing
  dependency.
- **State machines:** `xstate` v5 + `@xstate/react`, matching `ui_service`'s existing dependency
  and its locked Phase 6 architecture decision.
- **Automated verification:** Playwright, installed per-spike as a devDependency
  (`npm install -D playwright && npx playwright install chromium`) when the Claude-in-Chrome
  browser extension isn't connected. Chromium binaries are cached at `~/Library/Caches/
  ms-playwright/` and shared across spikes after the first install.

## Structure

- Dev server ports: 5301, 5302, 5304, ... (one per spike, sequential, gaps are fine — matches
  spike number, not necessarily contiguous).
- Comparison spikes (`NNNa-name` / `NNNb-name`) are separate npm packages, each with its own
  README, cross-linked via the `related` frontmatter field. The head-to-head verdict and
  comparison table live in the "a" (first-built / winning, when there is one) spike's README;
  the "b" spike's README documents its own investigation trail and points back to "a" for the
  verdict.
- Automated verification scripts live at the spike root as `verify.mjs` (or `verify-*.mjs` for
  focused follow-ups), run via plain `node verify.mjs` — not part of the npm `dev`/`build`
  scripts.
- Evidence (screenshots, etc.) goes to `evidence/` inside the spike directory — gitignored
  (`.planning/spikes/*/evidence/`), since findings belong in the README as text, not as
  accumulated binary artifacts.

## Patterns

- **Reactivity bridge for ECS:** neither miniplex nor bitECS notify React on component *value*
  mutation (only miniplex-react's `<Entities>`/`useEntities` fire on add/remove). The working
  pattern: a module-level `touch()` + `subscribeWorld()` pub-sub pair, exposed to React via
  `useSyncExternalStore`. Systems/handlers call `touch()` after mutating the world.
- **React Flow + external state:** never derive the `nodes` prop fresh from an external store on
  every mutation (breaks rendering entirely — see spike 001). Always buffer: React Flow owns
  local state via `useNodesState`, external-store changes patch matching nodes by id, and
  position writes flow back to the external store only on drag-stop.
- **XState as source of truth for entity existence:** when an external store (ECS or otherwise)
  mirrors an XState-owned snapshot, XState must remain the sole owner of add/remove — the mirror
  only reacts to snapshot changes. Any XState state that cross-references an entity by id must be
  explicitly re-validated against every new snapshot in the same transition (see spike 002's
  `clearSelectionIfMissing`); this does not happen for free.
- **Prefer plain derivation functions over "systems" for stateless per-interaction behavior.**
  NEXUS's existing pattern (`resolveLifecycle`-style: a pure function deriving state from a data
  object, called from a component or `useMemo`) already does what an ECS "system" would do for
  read-only derivations. Reserve ECS/systems for the live, churning entity collection itself
  (spike 004).
- **Ground every spike in the real code first.** Read the actual file being modeled (e.g.
  `ui_service/src/machines/pipelinePage.ts`, `ModuleNode.tsx`) before writing a stand-in — a
  simplified-from-imagination version risks testing the wrong shape entirely. All four spikes in
  this session used real production source as their starting point.
- **Verify library API assumptions against installed source, not memory or docs alone.** Spike
  003b's `set()`/`onSet` finding came from reading `node_modules/bitecs/test/*.test.ts` after the
  documented pattern silently produced wrong data — `docs/API.md` alone was misleading here.

## Tools & Libraries

- `miniplex` ^2.0.0 / `miniplex-react` ^2.0.1 — worked as documented, no surprises.
- `bitecs` ^0.4.0 — avoid `set()`/`addComponent(world, eid, set(C, data))` unless you've also
  registered an `onSet` observer via `observe(world, onSet(C), writerFn)`; otherwise it's a
  silent no-op. Use `addComponent(world, eid, C)` + direct array writes (`C.field[eid] = value`)
  for simple cases.
- `@xyflow/react` ^12.10.0, `xstate` ^5.28.0, `@xstate/react` ^4.1.3 — match `ui_service`'s
  pinned versions; keep spikes on the same majors so findings transfer directly.
- `playwright` ^1.62 — reliable for scripted drag/hover/click verification and DOM-based
  assertions when the Claude-in-Chrome extension isn't connected.
