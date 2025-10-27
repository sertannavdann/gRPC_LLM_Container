# Full Plan: Sync-First Resumable Agent Mesh

## 0. Guiding Constraints and Success Criteria
- Honor existing gRPC microservice architecture, LangGraph workflows, SQLite checkpointing, tool registry, and llama.cpp LLM service. No disruptive rewrites.
- Deliver a sync-first orchestrator that can resume after crashes, expose routing decisions, and operate efficiently for 1-2 local users.
- Maintain container isolation so each service (Agent, LLM, Chroma, Tools, UI) restarts independently and respects fixed CPU/memory limits.
- Embed a quantized router model in Agent Service now; design interfaces so a standalone router service can be swapped in later with minimal changes.
- Support Debug vs Shipping observability modes: Debug enables full OpenTelemetry logs/metrics for 5 minutes post-crash, Shipping keeps spans only.
- Keep workflows linear initially, then introduce bounded cyclic loops (max 2 review cycles); track remaining hops in state and UI.
- Add Agent2Agent messaging so roles (e.g., Reviewer, Coder) exchange structured messages while staying resumable via checkpoints.
- Document correlation IDs, span naming, and message schemas so an event-driven future (Dapr/Solace-style) remains viable.

## 1. Phase Overview and Timeline Assumptions
- Phase 1 (Weeks 1-2): Resumable, debug-friendly synchronous mesh with embedded router, tightened checkpointing, and observability toggles.
- Phase 2 (Weeks 3-5): Agent2Agent protocol, bounded loops, UI visibility upgrades, resource caps, and container hardening.
- Phase 3 (Weeks 6+ / optional): Async-ready primitives (correlation IDs, idempotent handlers), Dapr/K8s prep, deeper telemetry automation.

Assumptions:
- 3 backend engineers (Agent/Core tooling, LLM/infra, Observability), 1 frontend engineer, 1 SRE shared across phases.
- Existing CI/CD, Docker Compose, and test harnesses remain available.
- Each task includes engineering, code review, testing, documentation, and rollout plan.

## 2. Phase 1: Resumable Sync Mesh (Weeks 1-2)

### Task P1-T1: Embedded Router Model Integration
- **Context**: Architect recommends embedding a 3B quantized router (e.g., Qwen2.5-3B) inside Agent Service for minimal latency.
- **Objectives**:
  - Package the router model artifact (quantized) within `agent_service` container.
  - Extend `agent_service/llm_wrapper.py` to load the router model separately from main inference model.
  - Implement deterministic, low-temperature prompt template with strict JSON schema (decision + confidence + fallback).
  - Expose router decisions via structured log/span attributes and gRPC response metadata.
- **Deliverables**: Router load configuration, model placement guidance, updated adapter logic, unit tests for routing decisions, sample router output in docs.
- **Acceptance Criteria**: Decision latency <100 ms P95 locally; fallback path triggered on invalid JSON; confidence thresholds configurable in `core/config.py`.
- **Dependencies**: Quantized model availability; llama.cpp bindings for router if reusing; otherwise Python inference pipeline.

### Task P1-T2: Checkpoint Reliability and Crash Resume
- **Context**: SQLite checkpoints already exist; need WAL tuning and resume workflow on service restart.
- **Objectives**:
  - Audit `core/checkpointing.py` for WAL mode enforcement, durable writes, and journaling settings.
  - Add recovery routine on Agent Service startup: detect last checkpoint per thread, resume pending workflows.
  - Implement integration test simulating crash + resume using Docker Compose restart.
  - Document restart procedure for developers (Makefile target, expected logs).
- **Deliverables**: Updated checkpointing module, restart handler in `agent_service/agent_service.py`, integration test in `tests/integration/test_checkpoint_resume.py`, doc section covering operations.
- **Acceptance Criteria**: On forced container restart, workflow resumes from last persisted hop without data loss; tests run in CI.
- **Dependencies**: Task P1-T1 for hop metadata; Compose health-check to ensure service restarts properly.

### Task P1-T3: Observability Mode Switch (Debug vs Shipping)
- **Context**: Need environment-variable driven mode toggles with time-bounded full telemetry.
- **Objectives**:
  - Introduce configuration flag (e.g., `OBS_MODE=debug|shipping`) recognized by Agent, LLM, Chroma services.
  - Integrate OTEL exporters to emit traces by default; in Debug mode also emit structured logs and metrics for 5 minutes after crash detection.
  - Implement crash detector hooking into checkpoint recovery (Task P1-T2) and toggling enhanced telemetry window.
  - Update `docker-compose.yaml` and `Makefile` to pass mode to containers; add docs describing toggling.
- **Deliverables**: Config updates in `core/config.py`, instrumentation wrappers in `shared/clients` and Agent Service, tests verifying span emission, operational docs in `FullPlan.md`.
- **Acceptance Criteria**: Mode switch applied without redeploy; spans available in both modes; Debug mode auto-reverts to spans-only after 5 minutes.
- **Dependencies**: Task P1-T2 for crash detection hook; Task P1-T4 for span naming convention.

### Task P1-T4: Span Taxonomy and Router Decision Surfacing
- **Context**: Provide consistent span names/tags for route, tool execution, checkpoint operations.
- **Objectives**:
  - Define canonical span names: `agent.route`, `agent.tool_call`, `agent.checkpoint.save`, etc.
  - Attach attributes: service name, thread-id, hop count, remaining loops (if available), router confidence.
  - Ensure `shared/clients` include interceptors to propagate spans through gRPC metadata.
  - Update UI (minimal) to consume spans for the timeline (foundation for P2 UI work).
- **Deliverables**: Trace instrumentation in Agent Service and clients, metadata propagation, developer guide for span usage.
- **Acceptance Criteria**: Spans visible end-to-end in Debug mode; timeline data available for UI ingestion; router decisions readable in span attributes.
- **Dependencies**: Task P1-T3 instrumentation; Task P1-T1 for router output schema.

### Task P1-T5: UI Foundations for Timeline and Router Panel
- **Context**: Provide developer-facing timeline and router decision panel in Next.js UI.
- **Objectives**:
  - Introduce basic pages/components for Service Registry health, Request Timeline waterfall (using spans), Router Decision panel.
  - Integrate existing gRPC client (`ui_service/src/lib/grpc-client.ts`) with new metadata (decision, confidence).
  - Provide mock data mode for UI when backend spans unavailable.
- **Deliverables**: React components with Tailwind styling, types in `ui_service/src/types`, wiring in `page.tsx`, tests/stories if applicable.
- **Acceptance Criteria**: UI displays timeline of spans for a request, router decision summary, service health status; responsive for desktop; accessible within existing layout.
- **Dependencies**: Task P1-T4 for span data shape; Task P1-T3 for modes; existing UI infra.

## 3. Phase 2: Agent Collaboration and Resource Hardening (Weeks 3-5)

### Task P2-T1: Agent2Agent Protocol and Persistence
- **Context**: Need structured messaging between roles (Coder, Reviewer) with visibility and checkpointing.
- **Objectives**:
  - Define protobuf schema for Agent2Agent messages (e.g., `shared/proto/agent.proto` update) with fields: sender role, recipient role, message type, payload, hop index, remaining loops, correlation-id.
  - Extend LangGraph state to record Agent2Agent exchanges; ensure `core/graph.py` and `state.py` persist messages into checkpoints.
  - Provide gRPC method or tool invocation path to send/receive messages; update AgentServiceAdapter to notify UI via spans/metadata.
  - Add unit/integration tests verifying message persistence across crash/restart scenarios.
- **Deliverables**: Updated proto + generated code, state graph modifications, documentation on message schema, tests.
- **Acceptance Criteria**: Agents can send/receive messages during workflow; messages survive restarts; UI can display message history.
- **Dependencies**: Task P1-T2 checkpoint reliability; Task P1-T4 spans for correlating messages.

### Task P2-T2: Bounded Cyclic Workflow Support
- **Context**: Introduce loops with max iterations for reviewer feedback.
- **Objectives**:
  - Extend workflow configuration to include loop metadata (e.g., max cycles, current cycle count).
  - Modify `core/graph.py` to enforce cycle limits and surface remaining hops in state and spans.
  - Update router prompt to respect remaining hops, biasing toward completion when loops near exhaustion.
  - Add tests covering loop exhaustion and resume mid-loop after crash.
- **Deliverables**: Updated workflow builder, config schema, loop tracking logic, tests, documentation.
- **Acceptance Criteria**: Loop iterations capped at configured max; state shows `remaining_loops`; UI indicates progress; router behavior adjusts near limits.
- **Dependencies**: Task P2-T1 message schema (to display loops), Task P1-T1 router config.

### Task P2-T3: Resource Capping and Container Hardening
- **Context**: Ensure predictable resource consumption per container.
- **Objectives**:
  - Update Compose/Dockerfiles to set CPU quotas, memory limits, fixed thread pools (4-8 threads) per service.
  - Configure llama.cpp invocation with pre-sized KV cache, pinned threads, and environment variables for reproducibility.
  - Surface resource usage data as span tags (threads, memory) and in service registry heartbeat.
  - Provide documentation and scripts to override caps for power users.
- **Deliverables**: Dockerfile updates, Compose configuration, instrumentation patches, doc updates.
- **Acceptance Criteria**: Containers respect resource limits; metrics visible in spans; failure when exceeding limits triggers circuit breaker or fallback with logging.
- **Dependencies**: Task P1-T3 instrumentation; Task P2-T4 registry enhancements.

### Task P2-T4: Service Registry Capability Tags
- **Context**: Router needs capability hints per service/tool.
- **Objectives**:
  - Extend registry data model (likely `shared/clients` and `tools/registry.py`) to attach capability tags (threads, memory, tool type).
  - Update heartbeat messages to include capacity hints.
  - Modify router prompt to reference capability tags and recent health status.
- **Deliverables**: Registry updates, new gRPC messages if needed, docs on tag schema, tests verifying router decisions change with capabilities.
- **Acceptance Criteria**: Router sees capability tags at runtime; UI displays service health + capacities; tests simulate degraded capacity and confirm router fallback.
- **Dependencies**: Task P1-T1 router integration; Task P2-T3 resource instrumentation.

### Task P2-T5: UI Enhancements for Agent Collaboration
- **Context**: UI must show Agent2Agent messages, loop counts, resource health.
- **Objectives**:
  - Add components to display message timeline, remaining loops, and service resource stats.
  - Provide filtering by request/thread, highlight message send/receive events, and show router confidence.
  - Integrate health data into registry panel with capability tags and resource usage.
- **Deliverables**: React components, updates to `ui_service/src/lib/utils.ts` for formatting, tests/stories.
- **Acceptance Criteria**: UI shows Agent2Agent conversation context, loops progress, resource data; handles empty states; accessible via keyboard.
- **Dependencies**: Tasks P2-T1, P2-T2, P2-T3, P2-T4.

## 4. Phase 3: Async/Event Future-Proofing (Week 6+)

### Task P3-T1: Correlation IDs and Idempotent Handlers
- **Context**: Prepare for optional async/event-driven evolution.
- **Objectives**:
  - Standardize correlation ID format (UUID4) propagated through gRPC metadata, spans, checkpoints, Agent2Agent messages.
  - Ensure handlers in Agent Service and downstream services are idempotent based on correlation ID + hop index.
  - Document guidelines for event bus integration preserving contracts.
- **Deliverables**: Metadata propagation utilities, idempotency checks, documentation, tests verifying duplicate event handling.
- **Acceptance Criteria**: Duplicate requests with same correlation ID do not re-execute side-effectful actions; logs/spans show consistent IDs.
- **Dependencies**: Phase 1 span taxonomy; Phase 2 message schema.

### Task P3-T2: Event Schema Draft and Dapr Compatibility
- **Context**: Align with Solace/Dapr style eventing.
- **Objectives**:
  - Draft event schema for Agent2Agent and router events (JSON/Protobuf) with versioning, correlation IDs, payload signatures.
  - Document mapping between gRPC API and prospective event topics; identify required headers for trace propagation.
  - Prototype Dapr sidecar configuration file for Agent Service (no deployment yet).
- **Deliverables**: Schema definitions, documentation in `FullPlan.md` or new doc, configuration examples.
- **Acceptance Criteria**: Schema reviewed and approved; Dapr config validated locally (lint) though not deployed.
- **Dependencies**: Task P3-T1 correlation IDs; Phase 2 messaging design.

### Task P3-T3: Kubernetes Migration Prep
- **Context**: Containers already isolated; need readiness for K8s.
- **Objectives**:
  - Create Helm/chart skeleton or Kustomize templates reflecting Compose setup.
  - Define resource requests/limits matching Phase 2 caps; include OTEL collector deployment instructions.
  - Document readiness/liveness probes, config maps for OBS_MODE, router model mounting strategy.
- **Deliverables**: Deployment templates, documentation, pipeline checklist.
- **Acceptance Criteria**: Templates render successfully; manual testing instructions provided; no actual migration required yet.
- **Dependencies**: Phase 2 resource caps; Phase 1 observability modes.

## 5. Edge Case Handling and QA Strategy
- **Crash/Restart**: Use integration suite to simulate container crash mid-tool call; expect resume from last checkpoint with 5-minute Debug telemetry window.
- **Latency Budget**: Add performance tests (pytest markers) verifying P95 < real-time targets; router response <100 ms, overall hop budgets tracked.
- **Agent Hops and Loops**: Validate linear (3 steps) and bounded cyclic (max 5 hops) flows; ensure UI and state reflect remaining hops.
- **Router Accuracy**: Collect 50-100 labeled routing samples; run regression tests to compare decisions pre/post changes; implement low-confidence fallback logic.
- **Resource Limits**: Stress test each service under heavy load to confirm circuit breakers engage and spans capture thread/mem usage.

## 6. Documentation and Developer Enablement
- Update `ARCHITECTURE.md` with new router, Agent2Agent communication, and observability modes (Phase 1/2 milestone).
- Create `docs/observability.md` covering telemetry modes, span taxonomy, OTEL exporters.
- Add `docs/workflows.md` describing linear vs bounded cyclic flows, loop configuration, and Agent2Agent usage.
- Maintain `UI_SERVICE_SETUP.md` with new panels/components and local dev instructions.
- Provide onboarding checklist for new developers covering router model setup, debug mode usage, and test suites.

## 7. Testing and Automation Enhancements
- Expand unit tests in `tests/unit` for router decision logic, Tool registry capability tags, and Agent2Agent message handling.
- Add integration tests in `tests/integration` simulating end-to-end flows with loops and restarts.
- Configure CI to run new test suite segments and capture artifacts (spans, logs) for debugging.
- Introduce performance test harness (potentially in `testing_tool/`) to measure latency budgets automatically.

## 8. Risk Register and Mitigations
- **Router Model Footprint**: Embedded 3B model increases memory usage (~3-4 GB). Mitigation: Document resource requirement, ensure container limit fits host; fall back to lighter model if needed.
- **Checkpoint Corruption**: SQLite WAL issues could block resume. Mitigation: Frequent backups, WAL checkpointing on graceful shutdown, instrumentation for errors.
- **Observability Overhead**: Debug mode OTEL flood could impact latency. Mitigation: Time-bound to 5 minutes, sample logs where possible.
- **UI Complexity**: Additional panels could overwhelm users. Mitigation: Feature flag for advanced panels, maintain minimal default view.
- **Async Migration Drift**: Without documentation, future event-driven shift could break contracts. Mitigation: Maintain schemas and idempotency checks early (Phase 3 tasks).

## 9. Jira Task Creation Cheatsheet
Each task above maps to a Jira epic or story. Suggested format:
- **Summary**: `[Phase X] Task Name`
- **Description**: Copy task section (Context, Objectives, Deliverables, Acceptance Criteria, Dependencies).
- **Labels**: `phase-x`, `router`, `observability`, etc.
- **Story Points**: Estimate based on team velocity (guideline: Phase 1 tasks 3-5 pts each, Phase 2 tasks 5-8 pts, Phase 3 tasks 3-5 pts).
- **Attachments**: Link to relevant doc sections or diagrams (e.g., include ASCII diagram from Section 10).

## 10. Reference Architecture Visuals

### System Overview (Current Focus: Sync gRPC + Embedded Router + Containers)
```
┌────────────────────────────────────────────────────────────────┐
│                     Developer / UI (Next.js)                   │
│      • Timeline • Router Decisions • Registry Health Panels    │
└───────────────▲───────────────────────────────▲────────────────┘
                │ WebSocket/SSE (spans/events)  │ gRPC (Query)    
┌───────────────┴───────────────────────────────┴───────────────┐
│                        Agent Service                          │
│  • LangGraph workflow (linear → bounded cyclic)               │
│  • Embedded Router (≈3B quantized)                            │
│  • SQLite checkpoints (resume after crash)                    │
│  • OBS_MODE: Debug → full OTEL (5m post-crash), Shipping spans│
└───────┬─────────────────────┬────────────────────────┬─────────────┘
        │ gRPC                │ gRPC                   │ gRPC             
        ▼                     ▼                        ▼                 
┌─────────────┐         ┌─────────────┐        ┌─────────────┐        
│ Chroma Svc  │         │ LLM Service │        │ Tool Svc    │        
│ (Vector DB) │         │ (llama.cpp) │        │ (Registry)  │        
│ • Indexed   │         │ • Fixed thr │        │ • Circuit   │        
│ • WAL logs  │         │ • KV cache  │        │   breakers  │        
└─────────────┘         └─────────────┘        └─────────────┘        
    ▲                          ▲                        ▲                
    └──────  Spans/metrics/logs (mode-dependent)  ──────┘
```

### Resumability and Bounded Loops
```
User Query
  → Router span (decision + confidence)
  → Graph: RAG → Coder → Reviewer
        │          ▲
        └──(≤2)────┘  (bounded loop)

At each node:
  • Checkpoint saved (state + messages + remaining loops)
  • On crash: reload last checkpoint, resume next hop
  • UI displays "remaining loops: 1/2"
```

### Agent2Agent Messaging Visibility
```
Reviewer ──► Agent2Agent Message (proto) ──► Coder
  • Persists with trace-id + hop index
  • Router may re-evaluate route if service health changed
  • UI timeline shows structured message payloads
```

## 11. Next Steps for Program Managers
- Review Phase 1 tasks, confirm dependencies, and schedule backlog grooming session.
- Validate resource allocation (model hosting requirements) with infrastructure team.
- Prepare stakeholder demo criteria focusing on timeline panel, router decision visibility, and crash resume scenario.
- Plan regular checkpoints (end of each phase) to reassess need for Phase 3 scope based on business priority.

## 12. Appendix: Configuration Snapshots
- **Environment Variables**: `OBS_MODE`, `ROUTER_MODEL_PATH`, `ROUTER_CONFIDENCE_THRESHOLD`, `CHECKPOINT_DB_PATH`.
- **Compose Overrides**: Provide sample `docker-compose.override.yml` enabling Debug mode and resource caps.
- **Testing Commands**:
  - `pytest tests/unit/test_router.py -k decision`
  - `pytest tests/integration/test_checkpoint_resume.py`
  - `make up && pytest tests/integration/test_agent_service_e2e.py`
- **Manual Verification Checklist**:
  - Start stack in Debug mode, trigger crash, observe 5-minute telemetry.
  - Trigger query requiring loop (review cycle) and confirm UI displays hops.
  - Validate Agent2Agent message visible in timeline with correct correlation ID.

---
This plan equips the team to implement the sync-first, resumable, observable agent mesh while preserving future flexibility for event-driven expansion.
