# NEXUS Branch, SOLID Validation, and Sandbox Deployment Assessment

**Last Updated**: 2026-04-02  
**Scope**: Current repository state, `origin/main` vs `origin/NEXUS`, and existing deployment/observability assets.

---

## 1. Current SRP / SOLID State

### What is already modular

The codebase is modular at the service and shared-library level:

- **Service boundaries** are explicit: orchestrator, dashboard, sandbox, LLM, chroma, bridge, and UI each live in separate directories and run as separate containers (`docker-compose.yaml`).
- **Shared contracts** are centralized in `shared/proto/`, `shared/clients/`, `shared/modules/`, `shared/adapters/`, and `shared/observability/`.
- **Self-evolving infrastructure** is isolated from runtime orchestration through the module loader, registry, credentials store, and validator (`shared/modules/*`).
- **gRPC concerns** are separated from business logic through generated stubs plus the observability interceptor (`shared/observability/grpc_interceptor.py`).

### Where SRP is still weak

Current planning and audit artifacts show clear SRP pressure points:

1. **Dashboard service**
   - The repository state file still tracks a **Dashboard SRP violation** because one service owns context aggregation, adapter surfacing, finance views, and SSE/pipeline concerns (`.planning/STATE.md`).
2. **Context tooling overlap**
   - The live audit identifies `context_bridge.py`, `user_context.py`, and `finance_query.py` as overlapping responsibilities, including duplicate fetching, formatting, and fallback behavior (`.planning/phases/05-refactoring/LIVE-AUDIT.md`).
3. **Hard-coded extension points**
   - The same audit calls out OCP pressure where new categories require edits across multiple files instead of purely registering a new adapter.

### Current conclusion

- **SRP adherence is mixed**: strong at the service/platform level, weaker inside the dashboard/context tool slice.
- **Maintenance/scalability is good but uneven**: adding whole services or modules is straightforward, while extending context aggregation and dashboard features is still more coupled than ideal.
- **Primary refinement targets**: `dashboard_service/*`, `tools/builtin/user_context.py`, `tools/builtin/context_bridge.py`, and `tools/builtin/finance_query.py`.

---

## 2. NEXUS Branch Findings

Remote branches currently visible for this repository are:

- `main`
- `NEXUS`
- `copilot/validate-solid-compliance-srp`

### Has `NEXUS` implemented SRP-focused work?

Yes. After fetching `origin/main` and `origin/NEXUS`, the `NEXUS` branch shows a dedicated SOLID cleanup wave:

- `docs(05-05): complete tool consolidation & SOLID cleanup plan`
- `refactor(05-05): rewire orchestrator to 8 consolidated tools, remove dead method`
- `refactor(05-05): build all 8 consolidated tool classes`
- `refactor(05-05): ContextBridge class, normalize_for_tools on adapters, delete mock adapters`
- `refactor(05-05): delete dead code files, guard chart_validator import`

That change set is concentrated in:

- `.planning/`
- `shared/`
- `tests/`
- `tools/`
- `dashboard_service/`
- `docs/`

So the `NEXUS` branch is not just feature growth; it includes explicit refactors aimed at reducing overlap and tightening responsibility boundaries.

### Suggested branch strategy

To keep SRP work isolated and reviewable, use:

- **`main`**: stable, releasable branch
- **`NEXUS`**: long-lived architecture and integration branch for self-evolution, observability, and structural refactors
- **short-lived feature/refactor branches** (`copilot/*`, `phase/*`, `fix/*`): focused, reviewable changes merged back into `NEXUS` or `main` as appropriate

---

## 3. What Enforces SOLID Today

There is **no single automated “SOLID score”** in the repository today. Compliance is currently encouraged by a combination of patterns, planning, and tests:

### Patterns already present

- **Adapter abstraction**: `shared/adapters/base.py`
- **Module manifest + registry + credential store**: `shared/modules/*`
- **gRPC contract-first interfaces**: `shared/proto/*`
- **Observability interceptor** for cross-cutting concerns instead of inlining metrics in each RPC handler: `shared/observability/grpc_interceptor.py`

### Tests and metrics already present

- Existing commands: `make test-unit`, `make test-integration`, `make verify`
- Observability metrics include:
  - `grpc_requests_total`
  - `grpc_request_duration_ms`
  - `tool_calls_total`
  - `lidm_delegation_requests_total`
  - `nexus_module_builds_total`
  - `nexus_module_validations_total`
  - `nexus_run_units_total`

### Current gap

The repository has **architectural guardrails**, but not a dedicated automated rule set that fails builds specifically for SRP/SOLID drift. That part still depends on review discipline and the refactoring plans in `.planning/phases/05-refactoring/`.

---

## 4. Self-Evolving System and Sandbox Deployment

### What “self-evolving” work already exists

The current implementation already supports these tasks:

- **module generation / repair / validation / install**
- **sandboxed validation loops**
- **run-unit metering**
- **audit-oriented module lifecycle management**

Planned next-stage self-evolution work is also documented:

- **approval gates / audit trail** (Phase 7)
- **Curriculum Agent / Executor Agent / co-evolution flows** (Track C / Phase 8)

### How the sandbox supports iterative testing

The sandbox is already designed for iterative verification:

- `sandbox_service/sandbox_service.py` enforces **timeouts**, **memory limits**, and **import restrictions**
- `sandbox_service/policy.py` adds **deny-by-default network policy**, import allowlists, and resource policies
- `shared/clients/sandbox_client.py` gives the orchestrator and validators a reusable gRPC client
- `orchestrator/admin_api.py` already exposes draft validation flows that depend on sandbox execution

This is compatible with containerized iteration: generate code, validate in sandbox, inspect results, repair, and re-run.

### Sandbox tools/resources available now

- Docker Compose stack for local multi-service execution
- sandbox gRPC service
- module validator + draft lifecycle
- Prometheus + Grafana + cAdvisor observability
- Makefile workflows for build, test, verify, logs, and health checks

### Deployment status

Current deployment is **primarily manual/ops-driven**:

- local/container workflow uses `make build`, `make up`, `make down`, `make verify`
- `RUNBOOK_DOCKER.md` and `docs/OPERATIONS.md` describe the operator flow
- there is **no `.github/workflows/` directory**, so there is no repository-native GitHub Actions build/deploy pipeline at this time

---

## 5. Metrics to Track for Self-Evolving Behavior

The current stack can already track most of the right signals:

- **gRPC health and latency**: `grpc_requests_total`, `grpc_request_duration_ms`, `grpc_errors_total`
- **tool execution load**: `tool_calls_total`, `tool_duration_ms`, `tool_errors_total`
- **routing behavior**: `lidm_delegation_requests_total`, `lidm_delegation_latency_ms`
- **module evolution**: `nexus_module_builds_total`, `nexus_module_validations_total`, `nexus_module_installs_total`
- **economic control**: `nexus_run_units_total`, `nexus_run_units_per_request`
- **container health**: CPU and memory via cAdvisor + Grafana dashboards

For future self-evolving evaluation, these metrics should be reviewed together:

1. validation pass/fail rate
2. repair-loop count per module
3. sandbox rejection reasons
4. latency/cost impact of self-evolution features
5. install/rollback frequency after validation

---

## 6. Role of gRPC in the Current System

gRPC is a core integration mechanism, not a side detail.

It currently enables:

- orchestrator → LLM service calls
- orchestrator → chroma service calls
- orchestrator → sandbox service calls
- shared contract reuse through protobuf definitions
- health/reflection support for service operations
- cross-cutting telemetry through `ObservabilityServerInterceptor`

That makes cross-component communication efficient and type-safe, while keeping service boundaries cleaner than direct in-process imports.

---

## 7. Refactoring / Code Review Strategies That Would Help Next

To move closer to full SRP alignment, prioritize:

1. **Split dashboard concerns**
   - separate context aggregation, finance projections, adapter registry endpoints, and SSE/pipeline streaming
2. **Finish context-tool consolidation**
   - preserve one source of truth for context fetch + normalization
3. **Treat mock adapters as dev-only assets**
   - keep production paths free of fallback duplication
4. **Add explicit review checklist items**
   - “Does this file own more than one concern?”
   - “Does this new feature require edits in multiple unrelated modules?”
   - “Is there already a shared formatter/client/validator for this?”
5. **Add CI when ready**
   - even a minimal build/test workflow would improve regression detection for future SRP refactors

---

## 8. Target-State Plan: What the Aimed SRP Changes Should Look Like

The most valuable SRP cleanup is not “split everything into more services.” It is to define **one reason to change per module** and keep the individual-user product flow simple.

### A. Dashboard target state

**Current**: one dashboard slice mixes context aggregation, adapter listing, finance projections, module listing, and SSE stream assembly.

**Aimed shape**:

- **Context Aggregator**
  - responsibility: fetch, merge, and normalize user context
  - owns: `/context`, `/context/summary`, `/context/relevance`
- **Pipeline Stream**
  - responsibility: expose live execution and pipeline state to UI
  - owns: SSE and pipeline event formatting only
- **Finance Projection**
  - responsibility: banking summaries, balances, and transaction-specific projections
  - owns: finance-only endpoints and formatting
- **Adapter Catalog**
  - responsibility: adapter/module availability, status, capability metadata
  - owns: adapter listing and enablement-facing read models

This can remain in one deployable service initially, but should be split into separate modules/files with explicit interfaces before turning them into separate containers.

### B. Tooling target state

**Current**: context tools have overlapping fetch/format/fallback behavior.

**Aimed shape**:

- **One context retrieval path**
  - a single `ContextBridge` / context service abstraction fetches context
- **One user-facing context tool**
  - `get_user_context(categories, mode)` becomes the main context entry point
- **Thin convenience wrappers only if justified by UX**
  - keep wrappers like `get_daily_briefing` only when they add distinct product value, not when they just rename the same call
- **Finance querying either becomes context-derived or a truly separate finance analysis tool**
  - avoid two paths for the same data

### C. Self-evolving target state

For an individual-user prototype, the self-evolving loop should look like:

1. user requests a new capability
2. module scaffold/generation produces draft assets
3. sandbox validates imports, network policy, tests, and runtime behavior
4. user reviews concise results
5. user approves or rejects install
6. system records metrics and audit trail

That keeps the product focused on **assistive self-evolution**, not autonomous uncontrolled mutation.

### D. Suggested implementation order

1. **Refactor in-process first**
   - split dashboard concerns into modules without adding new network boundaries
2. **Unify context retrieval**
   - eliminate overlap between context tools
3. **Add approval checkpoint**
   - make self-evolution safe for individuals before making it more autonomous
4. **Only then consider more services**
   - add deployment complexity only if runtime load or team boundaries demand it

---

## 9. Product Decisions That Need Arbitration

These are the main choices that affect value more than code style.

### Decision 1: “Simple personal agent” vs “general module platform”

- **Simple personal agent**
  - best for faster product clarity
  - focuses on daily context, a few integrations, safe module suggestions, and clear approvals
- **General module platform**
  - broader long-term upside
  - higher UX, safety, review, and support burden

**Recommendation for prototype value**: bias toward the **simple personal agent** first.

### Decision 2: Approval-first vs autonomy-first self-evolution

- **Approval-first**
  - user reviews generated code/results before enablement
  - safer and easier to trust
- **Autonomy-first**
  - system installs after passing sandbox gates automatically
  - feels more magical, but increases safety and support risk

**Recommendation for prototype value**: choose **approval-first**.

### Decision 3: Keep one dashboard service vs split into microservices now

- **Keep one deployable service, split internally**
  - less ops complexity
  - enough to get SRP benefits early
- **Split into microservices now**
  - clearer runtime boundaries
  - more moving parts for a single-user product

**Recommendation for prototype value**: **modular monolith first**, microservices later.

### Decision 4: Broad adapter surface vs curated adapter set

- **Broad adapter surface**
  - attractive ecosystem story
  - weakens prototype focus
- **Curated set**
  - stronger end-user experience
  - easier to validate deeply

**Recommendation for prototype value**: keep a **curated set** around the highest-frequency personal workflows.

### Decision 5: Enterprise controls now vs individual utility now

- **Enterprise-first**
  - SSO, marketplace, org policies, large-scale operations
- **Individual-first**
  - faster time to a lovable personal system

**Recommendation for prototype value**: prioritize **individual-first**, while preserving extension seams for later enterprise work.

---

## 10. Segments Most Correlated with the NEXUS Prototype

If NEXUS is positioned as a **simple self-evolving system for individuals**, the most aligned segments are the ones that benefit from automation but still want explicit control.

### Highest-correlation prototype segments

1. **Power users / technical individuals**
   - want a personal system that can search, summarize, execute safe code, and add integrations over time
   - tolerate an evolving prototype and understand approval workflows
2. **Indie builders / solo operators**
   - need one assistant that combines context, finance visibility, calendar/weather, and light automation
   - benefit from module generation without needing enterprise infrastructure
3. **Personal knowledge + operations users**
   - want one interface for daily briefing, lightweight planning, memory, and safe tool execution

### Medium-correlation segments

1. **Small teams**
   - useful later, but pushes the product quickly toward approvals, shared state, and governance
2. **Consultants / analysts**
   - value the workflow orchestration, but may want stronger reporting and trace exports sooner

### Lower-correlation segments for the current prototype

1. **Enterprise IT / compliance-heavy organizations**
   - require SSO, policy layers, centralized logging, approvals, and stronger audit guarantees
2. **Marketplace/ecosystem participants**
   - need versioning, publishing, moderation, billing, and discovery flows beyond the current prototype

### Prototype-aligned capability stack

The simplest high-value NEXUS prototype should emphasize:

- **daily context aggregation**
- **safe gRPC-connected tool execution**
- **module suggestion / generation**
- **sandbox validation**
- **explicit user approval**
- **clear observability for what changed and why**

The following areas are valuable but should stay secondary for the prototype:

- marketplace flows
- heavy multi-tenant governance
- enterprise identity features
- aggressive automatic self-modification

---

## 11. Recommended Product Plan for the Next Iteration

### Phase A — tighten the prototype

- split dashboard responsibilities internally
- consolidate context tooling
- keep the adapter set curated
- improve the user-facing explanation of sandbox results

### Phase B — make self-evolution trustworthy

- add approval gates
- add concise change summaries before install
- track repair-loop and validation metrics in dashboards

### Phase C — expand only after user value is proven

- add more adapters where repeated user demand exists
- consider externalizing more services only when operationally justified
- defer enterprise and marketplace features until the individual workflow is clearly valuable

---

## Bottom Line

- The system is **modular enough to evolve**, especially across services and shared contracts.
- It is **not yet fully SRP-clean**, with the dashboard/context area remaining the main hotspot.
- The `NEXUS` branch has already carried out **exclusive SOLID-focused refactors**, so it is the right base for further cleanup.
- The self-evolving story is **real but incomplete**: sandboxed validation, module repair, metering, and observability exist now; approval gates and co-evolution automation are still upcoming.
- The highest-value path for the product prototype is a **modular, approval-first personal system** rather than a fully autonomous or enterprise-first platform.
