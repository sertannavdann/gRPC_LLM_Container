# Deferred Items — Phase 09 ecs-context-canvas

Items discovered during execution that are out of scope for the plan that found them.

## From 09-07

- **`ui_service/e2e/pipeline-sse.spec.ts` "error handling on SSE failure" test fails in this
  agent's environment**, independent of plan 09-07's changes. Reproduced in isolation: after
  `context.setOffline(true)`, `getByText('Disconnected')` never becomes visible within the 20s
  timeout. The test file was not modified by 09-07, and the failure reproduces against the same
  `pipelinePageMachine` connection-state logic 09-07 did not touch. Suspected cause: `next dev`
  (used for this worktree's verification, since the running `ui_service` Docker container serves
  the main checkout's image) may handle `context.setOffline` timing differently than the
  production nginx/Docker image `pipeline-sse.spec.ts` was written against. Needs investigation
  against the actual `ui_service` Docker image, not a `next dev` server, before concluding
  whether this is a real regression or an artifact of the verification method.
