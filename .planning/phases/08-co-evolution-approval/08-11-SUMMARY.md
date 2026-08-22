---
phase: 08-co-evolution-approval
plan: 11
subsystem: ui
tags: [chat, action-card, module-approval, blueprint, framer-motion]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: "08-10's chat approve_module/reject_module strategies on ModuleAdminTool (RBAC-gated via _require_admin_session()); 08-09's BlueprintCard component (expandable prop) and adminClient.getModuleReview/ModuleReview/ModuleBlueprint types"
provides:
  - "ApprovalActionCard.tsx — chat approval card extending ActionCard's shell/state-machine with a collapsed BlueprintCard summary, optional feedback textarea, and two-click terminal-rejection confirmation (D-02)"
  - "ChatContainer.tsx moduleApprovalIntent() discriminator routing module_admin approve_module/reject_module tool calls to ApprovalActionCard, all other tool calls unaffected"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CSS container query (styled-jsx <style jsx>, container-type: inline-size) for the <360px icon-only button variant — no ResizeObserver/layout effect, matching the plan's 'free of layout effects on every render' directive"
    - "AbortController-free unmount guard via a local `ignore` flag in the blueprint-fetch useEffect (Phase 6 no-silent-fallback: loading skeleton -> BlueprintCard or DegradedBanner, never a blank space)"
    - "Reject-flow UX: feedback textarea content reactively drives destructive-vs-reversible copy (D-09), matching 08-09's NodeDetailPanel footer precedent exactly — no modal, inline two-click confirmation"

key-files:
  created:
    - ui_service/src/components/chat/ApprovalActionCard.tsx
  modified:
    - ui_service/src/components/chat/ChatContainer.tsx

key-decisions:
  - "Approve/Reject semantics reuse base ActionCard's literal contract verbatim: 'Approve Module' confirms/executes the tool call exactly as the LLM proposed it (arguments.action is whatever the agent chose — approve_module or reject_module — with the optional feedback textarea merged in via handleApproveToolCall's new feedback param), while 'Reject Module' is the existing client-side decline/dismiss (handleRejectToolCall, no backend call), gated behind the D-09 two-click destructive-vs-reversible copy before it fires. This is the plan's own literal task wording ('Approve calls onApprove(id, feedback)... Reject calls onReject(id)...') rather than an independent approve_module/reject_module button-override design — kept because the onApprove/onReject prop signatures (id + optional feedback only, no action override) make the override design impossible to express without changing ChatContainer's dispatch beyond what Task 2 specifies"
  - "handleApproveToolCall's feedback merge is unconditional on which button fired it — it always spreads `{ ...toolCallData.call.arguments, feedback }` when feedback is present, per Task 2's exact wording, so the repair path only activates when the underlying toolCall.arguments.action is already 'reject_module' (agent proposed rejecting) and the user confirms with feedback text"
  - "Blueprint fetch failure renders DegradedBanner (not a blank card) — Phase 6 no-silent-fallback rule applied to the chat surface exactly as it was to NodeDetailPanel in 08-09"

requirements-completed: ["REQ-014"]

# Metrics
duration: ~35min
completed: 2026-08-22
---

# Phase 08 Plan 11: Chat Approval Card Summary

**`ApprovalActionCard` extends the Phase 6 `ActionCard` structured-action pattern with a collapsed blueprint summary, optional feedback textarea, and two-click terminal-rejection confirmation, routed into `ChatContainer` via a pure `moduleApprovalIntent()` discriminator — closing D-02's chat half of REQ-014.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 2/2 completed
- **Files modified:** 1 created, 1 modified

## Accomplishments

- `ApprovalActionCard.tsx` (new): reuses `ActionCard`'s exact shell (`rounded-lg border border-border bg-card p-4 space-y-3 max-w-md`), the four `AnimatePresence mode="wait"` state blocks (pending/executing/completed/failed) including the verbatim `failed` shake keyframes and `completed` spring entrance, and imports `ToolCall` from `./ActionCard` rather than redeclaring it. `Puzzle` header icon (vs. `parseToolName`'s category icon map) marks every card as a module action.
- Blueprint fetch: on mount (and on `moduleId` change), splits `moduleId` on `/` and calls `adminApi.getModuleReview(category, platform)`; guards against unmount with a local `ignore` flag; renders a skeleton while loading, `<BlueprintCard blueprint={review.blueprint} moduleName={moduleId} expandable={false} />` (collapsed summary only — UI-SPEC Surface 5's "never the expanded React Flow graph in chat") on success, `DegradedBanner` on failure.
- Optional feedback `<textarea>` (`text-sm bg-zinc-950 border border-zinc-700 rounded-md p-2`, 2 rows) shown only while `status === 'pending'`. Approve calls `onApprove(toolCall.id, feedback || undefined)`. Reject calls `onReject(toolCall.id)`, gated by the D-09 contracted copy: non-empty feedback shows the reversible repair line and fires immediately; empty feedback shows the destructive terminal line and requires a second click on a red "Confirm Reject" state (button label and background darken on the first click) — matching the pipeline panel's inline confirmation pattern, no modal.
- "Open in Pipeline" `next/link` to `/pipeline` (`text-orange-400 text-xs`).
- Icon-only compact button variant below a 360px **container** width (not viewport width) via a `styled-jsx` `@container` query on a `container-type: inline-size` wrapper — no `ResizeObserver`/layout effect on every render, per the plan's explicit constraint. Each icon button carries `aria-label="Approve Module"` / `aria-label="Reject Module"` and a 44px `minHeight`/`minWidth` hit area (WCAG 2.5.5).
- `ChatContainer.tsx`: `moduleApprovalIntent(call: ToolCall)` is a pure module-scope helper reading `call.arguments.action` (`"approve_module"` / `"reject_module"`) and `call.arguments.module_id` (`"category/platform"`) — the exact key names `ModuleAdminTool`'s `CompositeTool.validate_input`/`ApproveModuleStrategy`/`RejectModuleStrategy` (plan 08-10, `tools/builtin/module_admin.py`) actually use, confirmed by reading the strategy `execute()` bodies before writing the discriminator. The `pendingToolCalls` render block branches per entry: a non-null result renders `ApprovalActionCard`, otherwise the existing `ActionCard` is rendered completely unchanged.
- `handleApproveToolCall` gained an optional `feedback?: string` parameter; when present it is spread into the executed-tool arguments (`{ ...toolCallData.call.arguments, feedback }`) sent to `/api/orchestrator`, so a chat approval that carries user feedback on an agent-proposed `reject_module` call reaches the backend's bounded repair path (D-09). No endpoint, request envelope key, or executing/completed/failed transition changed. No client-side role/permission gate was added anywhere in the file — authorization stays exclusively server-side via plan 08-10's `_require_admin_session()`; a 403 surfaces through the card's existing `failed` state.

## Task Commits

Each task was committed atomically:

1. **Task 1: ApprovalActionCard component** - `e25c011` (feat)
2. **Task 2: Route module-approval tool calls to the approval card** - `edd6624` (feat)

**Plan metadata:** committed by orchestrator after merge (worktree mode — this agent does not write STATE.md/ROADMAP.md)

## Files Created/Modified

- `ui_service/src/components/chat/ApprovalActionCard.tsx` - New: `ApprovalActionCard` component, blueprint fetch effect, feedback/confirmation state machine, compact-button container query
- `ui_service/src/components/chat/ChatContainer.tsx` - Modified: `moduleApprovalIntent()` helper, `ApprovalActionCard` import and conditional render branch, `handleApproveToolCall(toolCallId, feedback?)` signature + argument merge

## Decisions Made

See `key-decisions` in frontmatter for the three substantive decisions (Approve/Reject semantics fidelity to the plan's literal ActionCard-reuse contract, unconditional feedback merge in `handleApproveToolCall`, DegradedBanner on blueprint-fetch failure).

## Deviations from Plan

None — plan executed exactly as written. Both tasks' acceptance-criteria greps (`expandable={false}`, the three exact button/confirmation strings, `aria-label` count, zero `ReactFlow` occurrences, no duplicated `ToolCall` interface, `moduleApprovalIntent` present in both the helper and render branch, `ActionCard` still rendered on the non-approval branch, `feedback` merged into executed arguments, no client-side `role` authorization check) were verified directly against the committed files before each commit.

## Issues Encountered

- This worktree's HEAD was initially on an unrelated, much older commit (`6b2027b "Cohesion (#14)"`, no `.planning/` directory) despite being on the correct `worktree-agent-*` branch — the same pre-existing worktree-provisioning issue documented in 08-03/08-07/08-08/08-09's summaries. `git merge-base` against the expected base (`930972c...`) did not match, so `git reset --hard 930972c...` was performed (working tree was already clean) before any plan file could be read, per the mandatory `worktree_branch_check` step.
- `ui_service/node_modules` was absent; `npm ci` was run first (no `package.json`/lockfile changes) so `tsc --noEmit`, `next lint`, and `next build` could execute — same recurring pattern noted in every prior UI plan in this phase.
- `ui_service/tsconfig.tsbuildinfo` is a pre-existing tracked build artifact that `tsc --noEmit` regenerates on every run; left out of both task commits (not part of `files_modified`, no reviewable content), consistent with 08-09's precedent.

## User Setup Required

None — no external service configuration required. Manual/browser verification (asking the assistant to approve/reject a validated module renders the approval card with a blueprint summary; rejecting with empty feedback requires two clicks; a viewer-role session shows the backend's permission error in the card's failed state) is deferred to a services-up environment, consistent with this plan's own `<verification>` section.

## Next Phase Readiness

- D-02 is now delivered end to end across both surfaces: the pipeline `NodeDetailPanel` review (08-09) and this chat `ApprovalActionCard` (08-11), both extending the same Phase 6 `ActionCard`/panel visual language with no bolted-on look.
- `cd ui_service && npx tsc --noEmit`, `npx next lint --dir src/components/chat`, and `npm run build` all pass cleanly against this worktree's changes (pre-existing `ChatContainer.tsx` `exhaustive-deps` warnings are unrelated to this plan's edits and were present before this plan started).
- No blockers for downstream plans in this wave. This plan did not touch `dashboard_service/` or the module panel components reserved for the concurrent 08-12 executor.

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-22*
