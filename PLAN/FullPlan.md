# Master Plan: Sync-First Resumable Agent Architecture

## 0. Guiding Principles & Success Criteria
- **Authoritative Plan**: This document is the single source of truth, superseding all previous planning documents.
- **Core Architecture**: The system is a **gRPC microservice architecture**. It uses LangGraph for workflow orchestration, SQLite for checkpointing, and a tool registry for capabilities. The "Agent Mesh" is a conceptual influence for patterns like service discovery and observability, not a literal architectural replacement.
- **MVP First**: The immediate goal is a minimal viable product: a sync-first, resumable orchestrator that is observable and efficient for a single user.
- **Resumability & Stability**: The orchestrator must resume from the last stable step after a crash. Container isolation ensures services restart independently.
- **Embedded Router**: A small, quantized model is embedded in the `Agent Service`. Its primary role is to **inform, not decide**. It provides the main arbitrator agent with a structured view of available services and their capabilities, allowing the agent to make the final routing decision.
- **Progressive Resource Management**: Start with minimal resource monitoring (e.g., using `psutil`) and basic container-level capping. Defer strict C++-style enforcement (memory arenas, fixed thread pools) until the core system is stable.
- **Simple Workflows First**: Begin with linear workflows, then introduce bounded cyclic workflows (e.g., max 2 review cycles). Defer complex dynamic graphs.
- **Future-Proofing**: Use correlation IDs and clear schemas to allow for future evolution towards event-driven patterns or more advanced C++ integrations for performance.

## 1. Phased Rollout (MVP First)
- **Phase 1 (Weeks 1-2)**: **Core MVP**. Implement a resumable, debug-friendly synchronous agent with an embedded router, reliable checkpointing, and basic observability.
- **Phase 2 (Weeks 3-5)**: **Collaboration & Hardening**. Introduce Agent-to-Agent messaging, bounded loops, resource monitoring/capping, and UI enhancements.
- **Phase 3 (Weeks 6+)**: **Future-Proofing & Scale**. Solidify async-ready primitives (correlation IDs, idempotent handlers) and prepare for potential Kubernetes migration.

**Assumptions**:
- 3 backend engineers (Agent/Core, LLM/Infra, Observability), 1 frontend engineer.
- Existing CI/CD, Docker Compose, and test harnesses are functional.
- Each task includes engineering, code review, testing, and documentation.

## 2. Phase 1: Core MVP (Weeks 1-2)

### Task P1-T1: Embedded Router for Agent Guidance
- **Context**: The arbitrator agent needs structured information to make routing decisions. An embedded 3B quantized model will provide this context.
- **Objectives**:
  - Package a quantized router model (e.g., Qwen2.5-3B) within the `agent_service` container.
  - The router's function is to analyze the user query and produce a list of recommended services with confidence scores and reasoning.
  - This JSON output is then passed into the main arbitrator agent's prompt, which makes the final decision.
  - Expose the router's recommendation and the agent's final decision via structured logs and span attributes.
- **Deliverables**: Router loading logic, updated agent prompt template that includes router output, unit tests for the router's JSON output.
- **Acceptance Criteria**: The arbitrator agent receives routing recommendations from the router. The final routing decision is logged. Router latency is <100ms.

### Task P1-T2: Checkpoint Reliability and Crash Resume
- **Context**: Existing SQLite checkpoints must be hardened to ensure workflows can resume after a service crash.
- **Objectives**:
  - Audit `core/checkpointing.py` to enforce WAL mode for safe concurrent reads/writes.
  - Implement a recovery routine in `agent_service` on startup to load the last known checkpoint for a given thread and resume the workflow.
  - Create an integration test that simulates a container crash and verifies successful resumption.
- **Deliverables**: Updated checkpointing module, a startup recovery hook in `agent_service.py`, and an integration test (`tests/integration/test_resume.py`).
- **Acceptance Criteria**: On a forced container restart, a running workflow correctly resumes from the last completed step.

### Task P1-T3: Observability Mode Switch (Debug vs. Shipping)
- **Context**: We need controllable observability: lean for production, verbose for debugging.
- **Objectives**:
  - Introduce an environment variable `OBS_MODE` (`debug` or `shipping`).
  - In `shipping` mode (default), only traces (spans) are emitted.
  - In `debug` mode, emit full OTEL data (traces, metrics, logs). After a crash is detected (via the P1-T2 recovery hook), automatically enable `debug` mode for 5 minutes for forensics, then revert to `shipping`.
- **Deliverables**: Configuration in `core/config.py`, instrumentation wrappers in `shared/clients`, and operational documentation.
- **Acceptance Criteria**: Mode can be switched without redeployment. Spans are always on. Full telemetry is enabled only in debug mode or the post-crash window.

### Task P1-T4: Foundational Span Taxonomy
- **Context**: Consistent naming and tagging are required for meaningful traces.
- **Objectives**:
  - Define canonical span names: `agent.arbitrate`, `agent.route_recommendation`, `tool.call`, `checkpoint.save`.
  - Attach key attributes: `service.name`, `thread.id`, `hop.count`, `router.confidence`.
  - Ensure gRPC interceptors in `shared/clients` propagate trace context.
- **Deliverables**: Trace instrumentation, updated interceptors, and a developer guide for span usage.
- **Acceptance Criteria**: Traces are visible end-to-end. The agent's final routing decision and the router's recommendation are both readable in span attributes.

### Task P1-T5: UI Foundations for Observability
- **Context**: The UI needs basic panels to display the system's state for developers.
- **Objectives**:
  - Create three basic UI components: a Service Registry health panel, a Request Timeline (waterfall), and a Router Decisions panel.
  - The timeline should render spans received from the backend.
  - The router panel should show the router's recommendation and the agent's final choice.
- **Deliverables**: React components, updated types in `ui_service/src/types`, and wiring in `page.tsx`.
- **Acceptance Criteria**: UI displays a timeline, router decision summary, and service health status.

## 3. Phase 2: Collaboration & Hardening (Weeks 3-5)

### Task P2-T1: Agent-to-Agent (A2A) Messaging Protocol
- **Context**: Agents in a workflow (e.g., Coder, Reviewer) need a way to exchange structured feedback.
- **Objectives**:
  - Define a protobuf schema for A2A messages in `shared/proto/agent.proto` (fields: `sender_role`, `recipient_role`, `payload`, `hop_index`).
  - Extend the LangGraph state (`core/state.py`) to persist A2A messages in the checkpoint.
  - Expose a tool or gRPC method for agents to send messages, which are then routed to the correct recipient agent in the workflow.
- **Deliverables**: Updated protobuf definitions, modified state graph, and integration tests verifying message persistence and delivery.
- **Acceptance Criteria**: A "Reviewer" agent can send feedback that is received by a "Coder" agent on a subsequent workflow step. Messages survive restarts.

### Task P2-T2: Bounded Cyclic Workflow Support
- **Context**: Workflows need to support simple, finite loops (e.g., for code revisions).
- **Objectives**:
  - Extend the workflow state to include loop metadata (e.g., `max_cycles`, `current_cycle`).
  - Modify `core/graph.py` to enforce the cycle limit and expose `remaining_hops` in the state.
  - The arbitrator agent's prompt will include the remaining hops, allowing it to bias its decisions toward completion as loops are exhausted.
- **Deliverables**: Updated workflow builder, tests for loop exhaustion, and documentation.
- **Acceptance Criteria**: A workflow with a max of 2 review cycles stops after the second review. The UI indicates the current loop status (e.g., "Review Cycle 1 of 2").

### Task P2-T3: Resource Monitoring and Capping
- **Context**: Start with minimal, safe resource management. Strict C++-style enforcement is deferred.
- **Objectives**:
  - **Monitoring**: Use `psutil` within services to periodically report basic resource usage (CPU, memory) as span attributes. This is for observability only.
  - **Capping**: Use Docker Compose to set initial, generous CPU and memory limits on service containers to prevent runaway processes.
  - Defer implementing fixed thread pools and memory arenas until the system is stable and performance bottlenecks are identified.
- **Deliverables**: Instrumentation patches for services, updated `docker-compose.yaml` with resource limits.
- **Acceptance Criteria**: Containers run within their defined resource caps. CPU and memory usage are visible as attributes on service-level spans.

### Task P2-T4: Service Registry with Capability Tags
- **Context**: The router and agent need to know what each service can do.
- **Objectives**:
  - Extend the in-memory service registry. On startup, services register themselves along with a list of "capability tags" (e.g., `coding`, `rag`, `review`).
  - The router uses these tags to identify candidate services to recommend to the agent.
- **Deliverables**: An extended registry implementation, service registration logic, and updated router logic to use the tags.
- **Acceptance Criteria**: The router only recommends services with the relevant capability tag for a given task. The UI can display the capabilities of each registered service.

### Task P2-T5: UI Enhancements for Collaboration
- **Context**: The UI must visualize the new multi-agent and resource-monitoring features.
- **Objectives**:
  - Display A2A messages in the timeline view.
  - Show the current loop count and remaining hops for cyclic workflows.
  - Integrate basic resource metrics (CPU/memory from spans) into the service health panel.
- **Deliverables**: Updated React components for the timeline and registry panels.
- **Acceptance Criteria**: The UI provides a clear, real-time view of workflow collaboration and basic resource consumption.

## 4. Phase 3: Future-Proofing & Scale (Week 6+)

### Task P3-T1: Correlation IDs and Idempotent Handlers
- **Context**: Prepare for a potential evolution to an event-driven architecture.
- **Objectives**:
  - Standardize on a `correlation_id` (UUID) for each request, propagated through all gRPC calls, spans, and A2A messages.
  - Ensure service handlers are idempotent where possible (e.g., a write operation can be safely retried with the same ID without creating duplicates).
- **Deliverables**: Metadata propagation utilities and idempotency checks in key service handlers.
- **Acceptance Criteria**: A request can be traced end-to-end using a single correlation ID. Retrying a failed request does not cause duplicate data.

### Task P3-T2: Event Schema Draft
- **Context**: If we move to eventing (e.g., with Dapr or Solace), we'll need a schema.
- **Objectives**:
  - Draft a conceptual event schema for key actions (e.g., `AgentRouted`, `ToolExecuted`, `MessageSent`).
  - Document the mapping from gRPC calls to these conceptual events. This is a design task; no implementation is required.
- **Deliverables**: A markdown document (`docs/event_schema.md`) outlining the proposed event structures.
- **Acceptance Criteria**: The schema is reviewed and approved as a viable future direction.

### Task P3-T3: Kubernetes Migration Prep
- **Context**: Prepare for eventual deployment on Kubernetes.
- **Objectives**:
  - Create a skeleton Helm chart or Kustomize templates that mirror the Docker Compose setup.
  - Define resource requests/limits based on the caps from Phase 2.
  - Document readiness/liveness probes and configuration strategies (e.g., using ConfigMaps).
- **Deliverables**: Deployment templates and documentation.
- **Acceptance Criteria**: Templates are linted and render successfully. No actual migration is performed.

## 5. Edge Case Handling and QA Strategy
- **Crash/Restart**: The integration test from P1-T2 will be the primary validation. Test crashes at each step of a multi-agent workflow.
- **Latency Budgets**: Add performance tests to verify that router recommendations remain fast (<100ms) and overall hop budgets are respected.
- **Agent Hops**: Validate that linear flows are limited to 3 steps and bounded cyclic flows to 5 total hops. The arbitrator agent should be aware of the remaining hops.
- **Router Accuracy**: The router's job is to provide good recommendations. Collect a small labeled set (50-100 queries) to tune the router's prompt and validate its recommendations. In low-confidence cases, the arbitrator agent can choose a safe default or ask the user for clarification.
- **Resource Limits**: Stress test services to ensure the Docker-level caps prevent system-wide instability.

## 6. Documentation and Developer Enablement
- Update `ARCHITECTURE.md` to reflect the refined router role and multi-agent workflow patterns.
- Create `docs/observability.md` covering telemetry modes and span taxonomy.
- Create `docs/workflows.md` describing how to build and configure linear and bounded-cyclic workflows.
- Maintain `UI_SERVICE_SETUP.md` with details on the new UI panels.

## 7. Testing and Automation Enhancements
- Expand unit tests for the router's recommendation logic and the new workflow node types.
- Add integration tests for multi-agent flows, including A2A messaging and loop termination.
- Configure CI to run all tests and capture artifacts (spans, logs) for easier debugging of failures.

## 8. Risk Register and Mitigations
- **Router Model Footprint**: An embedded 3B model adds ~2-3 GB to the Agent Service memory. **Mitigation**: Document the resource requirement. If it becomes an issue, fall back to a smaller model or a simpler heuristic-based router.
- **Checkpoint Corruption**: SQLite WAL is robust, but file corruption is still possible. **Mitigation**: Implement automated backups of the checkpoint database. Add monitoring for write errors.
- **Observability Overhead**: Debug mode can be verbose. **Mitigation**: Keep it time-bounded (5 mins post-crash) and off by default in production.
- **UI Complexity**: New panels could become cluttered. **Mitigation**: Use a clean, minimal design. Keep advanced views optional or collapsed by default.

## 9. Jira Task Creation Cheatsheet
- **Summary**: `[Phase X] Task Name` (e.g., `[P1] Embedded Router for Agent Guidance`)
- **Description**: Copy the full task details (Context, Objectives, Deliverables, Acceptance Criteria).
- **Labels**: `phase-1`, `router`, `mvp`, `observability`.
- **Story Points**: Use estimates from the original plans as a baseline (e.g., P1 tasks: 3-5 pts; P2 tasks: 5-8 pts).

## 10. Reference Architecture Visuals

### System Overview (Sync gRPC + Informed Agent)
```
┌────────────────────────────────────────────────────────────────┐
│                     Developer / UI (Next.js)                   │
│      • Timeline • Router Decisions • Registry Health Panels    │
└───────────────▲───────────────────────────────▲────────────────┘
                │ WebSocket/SSE (spans/events)  │ gRPC (Query)    
┌───────────────┴───────────────────────────────┴───────────────┐
│                        Agent Service                          │
│  • Arbitrator Agent (Makes Final Decision)                    │
│  • Embedded Router (Provides Recommendations)                 │
│  • LangGraph Workflow (Linear → Bounded Cyclic)               │
│  • SQLite Checkpoints (Resume After Crash)                    │
└───────┬───────────────┬──────────────────────┬────────────────┘
        │ gRPC          │ gRPC                 │ gRPC
        ▼               ▼                      ▼
┌─────────────┐   ┌─────────────┐        ┌─────────────┐
│ RAG Service │   │ Coding Svc  │        │ Tools Svc   │
│ (Mistral)   │   │ (DeepSeek)  │        │ (Llama 8B)  │
└─────────────┘   └─────────────┘        └─────────────┘
```

### Resumability and Bounded Loops
```
User Query
  → Router Recommendation (span)
  → Arbitrator Agent Decision (span)
  → Graph: RAG → Coder → Reviewer
       │          ▲
       └──(≤2)────┘   (bounded loop)

Checkpoints at each node:
  • On crash: restart service, load last checkpoint, resume next hop.
  • Agent state includes "remaining_hops: 1/2".
```

### Agent-to-Agent Messaging
```
Reviewer Agent ──► A2A Message (persisted in checkpoint) ──► Coder Agent
  • Message includes trace-id and hop index.
  • UI shows message in timeline.
  • Arbitrator agent sees message in state for next decision.
```

## 11. Next Steps for Program Managers
- Review Phase 1 tasks for the MVP, confirm dependencies, and groom the backlog.
- Validate resource estimates for the router model with the infrastructure team.
- Prepare a stakeholder demo focused on the core MVP: crash-resume, basic observability (timeline, router panel), and a simple linear workflow.

---
This master plan equips the team to build a robust, observable, and resumable agent architecture, starting with a minimal viable product and providing a clear path for future enhancements.
