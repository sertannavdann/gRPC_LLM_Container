# Agent Mesh Architecture Plan: C++-Style Resource Management with gRPC Microservices

## Executive Summary

This document defines the implementation plan for evolving the existing gRPC LLM Agent Framework into a **production-grade Agent Mesh** that combines:
- **Service mesh patterns** for LLM orchestration (router as control plane, services as data plane)
- **C++-style resource management** (fixed thread pools, process isolation, memory arenas) for deterministic performance on M4 Pro Max hardware
- **LangGraph workflow coordination** for multi-agent collaboration (AutoGen-inspired roles like Planner/Coder/Reviewer)
- **Comprehensive observability** with OpenTelemetry-compatible tracing and resource metrics
- **Hardware-aware routing** that respects capacity limits and circuit breakers

This plan **augments and extends** the base architecture defined in `FullPlan.md`, adding mesh-specific capabilities while maintaining the sync-first, resumable foundation.

---

## 0. Architectural Philosophy & Differentiators

### Core Principles
1. **Service Mesh for LLMs**: Services are nodes in a dynamic graph; registry discovers, router routes, LangGraph coordinates.
2. **C++ Resource Discipline**: Fixed thread pools (4-8 threads), process isolation (one model per process), pre-allocated memory arenas (2-4GB KV cache) to prevent contention and fragmentation.
3. **Observable by Default**: Every mesh operation emits spans with resource metrics (thread utilization, memory peak, PID) for UI visualization.
4. **Capacity-Aware Routing**: Router scores services by semantic fit **and** available resources; circuit breakers enforce isolation.
5. **Hardware Optimization**: Designed for M4 Pro Max constraints (8-16 cores, 32-64GB RAM); caps prevent thrashing.

### Advantages Over Alternatives
| Framework | Single Runtime | gRPC Mesh | C++ Resources | Observability | Hardware Aware |
|-----------|---------------|-----------|---------------|---------------|----------------|
| **AutoGen** | ✅ Python | ❌ No isolation | ❌ GIL/GC | Basic | ❌ No caps |
| **CrewAI** | ✅ Python | ❌ No isolation | ❌ GC pauses | Basic | ❌ No caps |
| **LangGraph** | ✅ Python | ⚠️ Requires adapter | ❌ Python | Good | ❌ No caps |
| **This Mesh** | ❌ Distributed | ✅ gRPC + Polyglot | ✅ Fixed pools/arenas | ✅ Full OTEL | ✅ Capacity hints |

**Key Edge**: Unlike single-runtime frameworks, this mesh treats agents as **distributed RPC endpoints with capacity hints**, enabling hot-swaps, backpressure, and deterministic resource budgets—critical for production and local hardware constraints.

---

## 1. Architecture Layers (HLD)

The agent mesh is structured as three interacting planes:

### 1.1 Control Plane (Routing & Policy)
```
┌────────────────────────────────────────────────────────────────┐
│                          CONTROL PLANE                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Service     │  │ Router      │  │ Policy      │            │
│  │ Registry    │  │ Arbitrator  │  │ Layer       │            │
│  │             │  │             │  │             │            │
│  │ • Caps:     │  │ • 3B LLM    │  │ • Breakers  │            │
│  │   threads,  │  │ • Semantic  │  │ • Timeouts  │            │
│  │   memory,   │  │   analysis  │  │ • Budgets   │            │
│  │   PID       │  │ • Resource  │  │ • Fallbacks │            │
│  │ • Health    │  │   scoring   │  │             │            │
│  │   checks    │  │ • Confidence│  │             │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└───────────────────┬─────────────────┬─────────────────────────┘
                    │                 │
                    ▼                 ▼
```

**Components**:
- **Service Registry**: Maintains service inventory with C++ resource metadata (max_threads, memory_arena_size, process_id). Services heartbeat every 30s.
- **Router Arbitrator**: Embedded 3B quantized LLM (Qwen2.5) performs semantic routing with resource scoring. Returns JSON: `{service, confidence, fallback, reasoning}`.
- **Policy Layer**: Circuit breakers per service (3 failures → open for 60s), timeout budgets (5s default), resource thresholds (memory >80% → demote).

### 1.2 Data Plane (Execution & Coordination)
```
┌────────────────────────────────────────────────────────────────┐
│                          DATA PLANE                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ LangGraph   │  │ LLM Mesh    │  │ Tool/       │            │
│  │ Orchestrator│  │ Services    │  │ Extensions  │            │
│  │             │  │             │  │             │            │
│  │ • Nodes:    │  │ • RAG:      │  │ • C++ Infra:│            │
│  │   Planner,  │  │   Mistral 7B│  │   Threads,  │            │
│  │   Coder,    │  │   (4 thr,   │  │   Arenas,   │            │
│  │   Reviewer  │  │   4GB arena)│  │   Processes │            │
│  │ • Checkpts  │  │ • Coding:   │  │ • llama.cpp │            │
│  │ • Agent2Agt │  │   DeepSeek  │  │   wrappers  │            │
│  │   messages  │  │   (6 thr,   │  │ • Heartbeat │            │
│  │             │  │   8GB arena)│  │   reporters │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└────────────────────────────────────────────────────────────────┘
```

**Components**:
- **LangGraph Orchestrator**: Workflow engine executing multi-agent patterns (AutoGen-inspired roles). Checkpoints to SQLite; emits spans for each node transition.
- **LLM Mesh Services**: Isolated processes per model. Each service uses fixed thread pools and pre-allocated arenas. Registered with capability tags.
- **Tool/Extensions**: Polyglot support via gRPC (Python, C++, future Swift). Circuit breakers protect tool calls.

### 1.3 Observability Plane (Traces & UI)
```
┌────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY PLANE                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Tracing     │  │ UI Dashboard│  │ OTEL Export │            │
│  │ Service     │  │             │  │             │            │
│  │             │  │ • Registry  │  │ • Jaeger    │            │
│  │ • Spans:    │  │   View      │  │ • Tempo     │            │
│  │   route,    │  │ • Timeline  │  │ • Custom    │            │
│  │   execute,  │  │   Waterfall │  │   backends  │            │
│  │   threads,  │  │ • Router    │  │             │            │
│  │   memory    │  │   Decisions │  │             │            │
│  │ • Buffers   │  │ • Resource  │  │             │            │
│  │ • Sampling  │  │   Graphs    │  │             │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└────────────────────────────────────────────────────────────────┘
```

**Components**:
- **Tracing Service**: In-memory buffer with OTEL export. Spans include resource tags (`threads_used=3/4`, `memory_peak=3.2GB`, `pid=1234`).
- **UI Dashboard**: Real-time panels for service health, request waterfalls, router reasoning, resource utilization. Built with Next.js + Tailwind.
- **OTEL Export**: Compatible with Jaeger, Tempo, or custom sinks. Debug mode: full export; Shipping mode: spans only.

---

## 2. C++-Style Resource Management Deep Dive

### 2.1 Process Isolation Strategy
**Principle**: One model per process to eliminate shared memory contention and enable clean crash recovery.

```
┌──────────────────────────────┐
│     LLM Service Process      │  (e.g., RAG Service, PID: 1234)
│  ┌────────────────────────┐  │
│  │ Memory Arena (4GB)     │  │  - Pre-alloc for KV cache/tensors
│  │ - Fixed slab allocator │  │  - No fragmentation; deterministic
│  │ - Track peak usage     │  │  - Exposed via /proc/self/status
│  └──────────┬─────────────┘  │
│             │                │
│  ┌──────────▼────────────┐  │
│  │ Thread Pool (4 fixed) │  │  - llama.cpp: n_threads=4
│  │ - Worker queue        │  │  - Queue depth: 10 requests
│  │ - No oversub          │  │  - Utilization span tag
│  └──────────┬─────────────┘  │
│             │                │
│  ┌──────────▼────────────┐  │
│  │ gRPC Handler          │  │  - Receives request w/ trace-id
│  │ - Dispatch to pool    │  │  - Emits span: alloc → complete
│  │ - Resource budgets    │  │  - Circuit breaker check
│  └───────────────────────┘  │
└──────────────────────────────┘
         ▲
         │ gRPC Call (metadata: trace-id, max_threads=4)
         │ from Orchestrator
```

**Implementation Details**:
- **Process Launch**: Docker containers with `--cpus=2.0 --memory=8g` limits (Phase 2, Task P2-T3).
- **Arena Allocation**: Use llama.cpp's mmap for model weights; pre-allocate KV cache at startup to avoid runtime allocations.
- **Thread Pinning**: Pin threads to physical cores via `pthread_setaffinity_np` (C++ wrapper) or `psutil` affinity (Python).
- **Monitoring**: Emit span tags `threads_active`, `memory_used_mb`, `arena_peak_mb` on every inference request.

### 2.2 Thread Pool Configuration
**Principle**: Fixed-size pools prevent oversubscription; queue depth prevents OOM.

| Service       | Threads | Queue Depth | Timeout | Justification |
|---------------|---------|-------------|---------|---------------|
| RAG (Mistral) | 4       | 10          | 5s      | Lightweight embeddings; prefer parallelism |
| Coding (DeepSeek) | 6   | 5           | 10s     | Heavy reasoning; balance throughput/latency |
| Reviewer (Llama 8B) | 4 | 8           | 7s      | Moderate load; match RAG for symmetry |

**llama.cpp Integration**:
```cpp
// In src/llm_engine.cpp
llama_context_params ctx_params = llama_context_default_params();
ctx_params.n_ctx = 4096;           // Context window
ctx_params.n_batch = 512;          // Batch size
ctx_params.n_threads = 4;          // Fixed thread count
ctx_params.n_threads_batch = 4;    // Batch threads

// Pre-allocate KV cache
ctx_params.type_k = LLAMA_FTYPE_F16;
ctx_params.type_v = LLAMA_FTYPE_F16;
```

**Span Emission** (Python wrapper):
```python
# In llm_service/llm_service.py
import psutil
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def run_inference(prompt: str):
    with tracer.start_as_current_span("llm.inference") as span:
        span.set_attribute("service", "llm-rag")
        span.set_attribute("threads_total", 4)
        
        # Call llama.cpp
        result = subprocess.run([...], capture_output=True)
        
        # Report resource usage
        proc = psutil.Process()
        span.set_attribute("threads_active", proc.num_threads())
        span.set_attribute("memory_mb", proc.memory_info().rss // 1024**2)
        
        return result.stdout
```

### 2.3 Memory Arena Management
**Principle**: Pre-allocate fixed-size arenas to avoid fragmentation and GC pauses.

**Allocation Strategy**:
- **Model Weights**: mmap read-only (shared across forks if needed, but default: isolated).
- **KV Cache**: Pre-allocated at startup based on `n_ctx * hidden_dim * sizeof(float16)`.
- **Scratch Buffers**: Reuse per-thread buffers for intermediate activations.

**Monitoring**:
```python
# In shared/clients/llm_client.py
import resource

def get_memory_stats():
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "maxrss_mb": rusage.ru_maxrss / 1024,  # Peak resident set size
        "arena_peak_mb": read_arena_stats(),    # Custom arena tracker
    }
```

---

## 3. Phased Implementation Plan

This plan **extends** `FullPlan.md` phases with mesh-specific tasks. Refer to `FullPlan.md` for base tasks (P1-T1 through P3-T3).

### Phase 1 Extensions: Core Mesh Foundations (Weeks 1-2)

#### Task AM-P1-T1: Service Registry with C++ Resource Metadata
**Builds on**: FullPlan P1-T4 (Span Taxonomy)

**Context**: Router needs capacity hints (threads, memory, PID) to make hardware-aware decisions.

**Objectives**:
- Extend registry schema in `shared/proto/` to include `ResourceCapabilities` message:
  ```protobuf
  message ResourceCapabilities {
    int32 max_threads = 1;
    int32 memory_arena_mb = 2;
    int32 process_id = 3;
    int32 queue_depth = 4;
    float cpu_quota = 5;  // Docker CPU limit
  }
  
  message ServiceRegistration {
    string name = 1;
    string endpoint = 2;
    ResourceCapabilities capabilities = 3;
    repeated string tags = 4;  // e.g., "rag", "coding"
  }
  ```
- Update each service's startup to report capabilities via gRPC `RegisterService` call.
- Store registry in-memory (Agent Service) with heartbeat refresh (30s interval).
- Emit registry state as span attribute `registry.services` (JSON dump) on router queries.

**Deliverables**:
- Proto updates + generated code
- Registry handler in `agent_service/adapter.py`
- Heartbeat client in `shared/clients/base_client.py`
- Unit tests for registration/expiry logic
- Documentation in `docs/service_registry.md`

**Acceptance Criteria**:
- Services register on startup with accurate resource metadata.
- Heartbeat failures cause service removal after 90s (3 missed beats).
- UI (Phase 2) can query registry for display.

**Dependencies**: FullPlan P1-T4 (span taxonomy for metadata propagation).

**Effort**: 5 story points (Medium)

---

#### Task AM-P1-T2: Resource-Aware Router Arbitrator
**Builds on**: FullPlan P1-T1 (Embedded Router), AM-P1-T1 (Registry)

**Context**: Router must score services by semantic fit **and** available capacity.

**Objectives**:
- Update router prompt template to include registry data:
  ```python
  # In agent_service/llm_wrapper.py
  prompt = f"""
  Route this query to the best service.
  Query: {user_query}
  
  Available services:
  {json.dumps(registry.get_services(), indent=2)}
  
  For each service, consider:
  1. Semantic match (0-100)
  2. Resource availability (threads_used/max_threads)
  3. Recent failures (circuit breaker state)
  
  Return JSON:
  {{
    "service": "<name>",
    "confidence": 0-100,
    "reasoning": "<why>",
    "fallback": "<alternative>"
  }}
  """
  ```
- Implement scoring formula:
  ```python
  score = semantic_confidence * 0.6 + resource_score * 0.4
  resource_score = (1 - threads_used/max_threads) * 100
  if circuit_open:
      score = 0
  ```
- Add fallback logic: if top service unavailable, try second-best with confidence >70%.

**Deliverables**:
- Updated router logic in `agent_service/llm_wrapper.py`
- Scoring unit tests with mock registry
- Integration test simulating degraded service (high thread usage)
- Documentation in `docs/router_scoring.md`

**Acceptance Criteria**:
- Router selects less-loaded service when semantic scores are close (within 10%).
- Fallback triggers when primary service circuit is open.
- Decision reasoning visible in span attributes and UI panel.

**Dependencies**: AM-P1-T1 (registry data); FullPlan P1-T1 (router model).

**Effort**: 8 story points (High)

---

#### Task AM-P1-T3: C++ Thread Pool Instrumentation
**Builds on**: FullPlan P1-T3 (Observability Mode)

**Context**: Spans must expose thread/memory usage for debugging bottlenecks.

**Objectives**:
- Wrap llama.cpp inference calls in `llm_service/llm_service.py` with resource tracking:
  ```python
  import psutil
  from opentelemetry import trace
  
  def run_inference(prompt):
      proc = psutil.Process()
      with tracer.start_as_current_span("llm.inference") as span:
          span.set_attribute("threads_total", 4)
          span.set_attribute("threads_pre", proc.num_threads())
          
          # Call llama.cpp
          result = call_llama_cpp(prompt)
          
          span.set_attribute("threads_post", proc.num_threads())
          span.set_attribute("memory_mb", proc.memory_info().rss // 1024**2)
          span.set_attribute("cpu_percent", proc.cpu_percent(interval=0.1))
          
          return result
  ```
- Add environment variable `LLAMA_THREADS` to Docker Compose; default to 4.
- Update `Dockerfile` to install `psutil` for resource introspection.

**Deliverables**:
- Instrumented LLM service wrapper
- Compose env var configuration
- Integration test verifying span attributes
- Documentation snippet in `FullPlan.md` Appendix

**Acceptance Criteria**:
- Spans show `threads_active` and `memory_mb` tags in Debug mode.
- UI timeline (Phase 2) can render resource graphs.

**Dependencies**: FullPlan P1-T3 (OTEL setup).

**Effort**: 3 story points (Low)

---

### Phase 2 Extensions: Multi-Agent Patterns & Resource Hardening (Weeks 3-5)

#### Task AM-P2-T1: LangGraph Multi-Agent Workflow Templates
**Builds on**: FullPlan P2-T2 (Bounded Cyclic Workflows)

**Context**: Encode AutoGen-inspired roles (Planner, Coder, Reviewer) as reusable LangGraph nodes.

**Objectives**:
- Define workflow templates in `core/workflows/` directory:
  - `plan_code_review.py`: Linear 3-step workflow (RAG → Coding → Reviewer).
  - `iterative_refinement.py`: Bounded cyclic (Coder ↔ Reviewer, max 2 loops).
- Each node dispatches to appropriate service via router:
  ```python
  # In core/workflows/plan_code_review.py
  def planner_node(state):
      query = state["messages"][-1].content
      service = router.route(query, intent="planning")
      response = llm_client.run_inference(service, query)
      state["messages"].append(AIMessage(response))
      state["plan"] = extract_plan(response)
      return state
  
  def coder_node(state):
      plan = state["plan"]
      service = router.route(f"Implement: {plan}", intent="coding")
      code = llm_client.run_inference(service, plan)
      state["code"] = code
      return state
  
  def reviewer_node(state):
      code = state["code"]
      service = router.route(f"Review: {code}", intent="review")
      feedback = llm_client.run_inference(service, code)
      state["feedback"] = feedback
      return state
  ```
- Integrate with `core/graph.py` via dynamic node registration.
- Add checkpointing at each node transition.

**Deliverables**:
- Workflow templates in `core/workflows/`
- Updated `core/graph.py` to load templates dynamically
- Integration tests for each workflow
- Documentation in `docs/workflows.md`

**Acceptance Criteria**:
- `plan_code_review` workflow completes end-to-end with 3 distinct services.
- `iterative_refinement` loops up to 2 times and stops.
- Checkpoints allow resume after crash mid-workflow.

**Dependencies**: FullPlan P2-T2 (bounded loops); AM-P1-T2 (router).

**Effort**: 8 story points (High)

---

#### Task AM-P2-T2: Circuit Breakers with Resource Thresholds
**Builds on**: FullPlan P2-T3 (Resource Capping)

**Context**: Prevent cascading failures when services exceed resource limits.

**Objectives**:
- Extend `tools/circuit_breaker.py` to include resource-based triggers:
  ```python
  class ResourceAwareCircuitBreaker(CircuitBreaker):
      def __init__(self, threshold=3, timeout=60, memory_limit_mb=7000):
          super().__init__(threshold, timeout)
          self.memory_limit_mb = memory_limit_mb
      
      def check_resources(self, service_name):
          stats = registry.get_service_stats(service_name)
          if stats["memory_mb"] > self.memory_limit_mb:
              self.record_failure()
              raise CircuitOpenError(f"{service_name} memory exceeded")
  ```
- Update router to query circuit breaker state before dispatching:
  ```python
  def route(query, registry, breakers):
      candidates = registry.get_services()
      for svc in candidates:
          if breakers[svc.name].is_open():
              continue  # Skip unhealthy service
          score = compute_score(query, svc)
          # ... select best
  ```
- Add metrics for breaker state transitions (closed → open → half-open).

**Deliverables**:
- Enhanced circuit breaker in `tools/circuit_breaker.py`
- Router integration in `agent_service/adapter.py`
- Unit tests for resource threshold triggers
- Documentation update in `docs/circuit_breakers.md`

**Acceptance Criteria**:
- Service breaker opens when memory exceeds 7GB (80% of 8GB limit).
- Router skips open-breaker services and logs fallback decision.
- Breaker auto-recovers after 60s timeout (half-open test).

**Dependencies**: AM-P1-T1 (registry stats); FullPlan P2-T3 (resource caps).

**Effort**: 5 story points (Medium)

---

#### Task AM-P2-T3: Process Isolation Enforcement
**Builds on**: FullPlan P2-T3 (Container Hardening)

**Context**: Ensure one model per process with isolated memory spaces.

**Objectives**:
- Update `docker-compose.yaml` to enforce process limits:
  ```yaml
  llm_service_rag:
    image: llm_service:latest
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 8G
        reservations:
          cpus: '1.0'
          memory: 4G
    environment:
      MODEL_PATH: /app/models/mistral-7b-instruct-q5.gguf
      LLAMA_THREADS: 4
      MEMORY_ARENA_MB: 4096
    pids_limit: 50  # Prevent fork bombs
  ```
- Add startup validation in `llm_service/llm_service.py`:
  ```python
  import os
  
  def validate_isolation():
      pid = os.getpid()
      arena_mb = int(os.getenv("MEMORY_ARENA_MB", 4096))
      # Check if running in isolated container
      with open("/proc/self/cgroup") as f:
          if "docker" not in f.read():
              raise RuntimeError("Must run in container for isolation")
      logging.info(f"Process {pid} validated with {arena_mb}MB arena")
  ```
- Document process architecture in `ARCHITECTURE.md`.

**Deliverables**:
- Updated Compose configuration
- Validation logic in LLM services
- Architecture diagram in `ARCHITECTURE.md`
- Docker health check script

**Acceptance Criteria**:
- Each LLM service runs in separate container with enforced limits.
- Services fail to start if isolation checks fail.
- Resource limits visible in `docker stats` output.

**Dependencies**: FullPlan P2-T3 (resource caps); AM-P1-T3 (thread tracking).

**Effort**: 5 story points (Medium)

---

### Phase 3 Extensions: Observability & Polyglot Support (Weeks 6+)

#### Task AM-P3-T1: Full Resource Tracing with C++ Hooks
**Builds on**: FullPlan P3-T1 (Correlation IDs)

**Context**: Expose llama.cpp internals (thread starts, memory allocations) for deep debugging.

**Objectives**:
- Add tracing hooks in `external/CppLLM/src/llm_engine.cpp`:
  ```cpp
  #include <opentelemetry/trace/provider.h>
  
  void run_inference(const std::string& prompt) {
      auto tracer = trace::Provider::GetTracerProvider()->GetTracer("llama_cpp");
      auto span = tracer->StartSpan("llama.inference.cpp");
      span->SetAttribute("thread_id", std::this_thread::get_id());
      
      // Track memory allocation
      size_t mem_before = get_arena_usage();
      // ... inference logic
      size_t mem_after = get_arena_usage();
      
      span->SetAttribute("memory_delta_mb", (mem_after - mem_before) / 1024.0 / 1024.0);
      span->End();
  }
  ```
- Expose C++ spans to Python wrapper via gRPC metadata.
- Aggregate spans in Tracing Service for unified waterfall view.

**Deliverables**:
- C++ tracing instrumentation
- gRPC metadata propagation bridge
- Waterfall view in UI showing C++ spans
- Documentation in `docs/cpp_tracing.md`

**Acceptance Criteria**:
- C++ spans appear in UI timeline with correct parent-child relationships.
- Memory delta visible for each inference call.
- Overhead <5ms per span in Shipping mode.

**Dependencies**: FullPlan P3-T1 (correlation IDs); AM-P2-T3 (process isolation).

**Effort**: 8 story points (High)

---

#### Task AM-P3-T2: Polyglot Service Template (Swift/Objective-C++)
**Builds on**: FullPlan P3-T3 (K8s Prep)

**Context**: Enable native iOS integrations (e.g., EventKit bridges) as mesh services.

**Objectives**:
- Create template for Swift/ObjC++ services in `external/`:
  ```swift
  // In external/SwiftLLM/Sources/GrpcServer.swift
  import GRPC
  import NIO
  
  class LLMServiceProvider: Llm_LlmServiceProvider {
      func runInference(request: Llm_InferenceRequest, context: StatusOnlyCallContext) -> EventLoopFuture<Llm_InferenceResponse> {
          let span = tracer.startSpan("swift.inference")
          defer { span.end() }
          
          // Call native API (e.g., EventKit)
          let result = callNativeAPI(request.prompt)
          
          return context.eventLoop.makeSucceededFuture(
              Llm_InferenceResponse.with {
                  $0.result = result
              }
          )
      }
  }
  ```
- Register Swift service in registry with capability tags.
- Document polyglot setup in `docs/polyglot_services.md`.

**Deliverables**:
- Swift service template with gRPC server
- Registration example
- Cross-language integration test (Python client → Swift service)
- Documentation

**Acceptance Criteria**:
- Swift service registers successfully and responds to queries.
- Spans from Swift service appear in UI timeline.
- No performance degradation vs Python services.

**Dependencies**: AM-P1-T1 (registry); FullPlan P3-T3 (deployment templates).

**Effort**: 8 story points (High)

---

## 4. UI Dashboard Enhancements

### 4.1 Registry View Panel
**Location**: `ui_service/src/components/mesh/RegistryView.tsx`

**Features**:
- **Service List**: Name, endpoint, status (healthy/degraded/down), uptime.
- **Resource Metrics**: Threads (used/total), memory (MB used/arena size), CPU quota.
- **Circuit Breaker State**: Visual indicator (green/yellow/red) with failure count.
- **Capability Tags**: Badges showing service specializations (RAG, Coding, Review).

**Mock Data**:
```typescript
// In ui_service/src/components/mesh/RegistryView.tsx
const mockServices = [
  {
    name: "llm-rag",
    endpoint: "localhost:50051",
    status: "healthy",
    capabilities: {
      max_threads: 4,
      threads_used: 2,
      memory_arena_mb: 4096,
      memory_used_mb: 3200,
      cpu_quota: 2.0,
    },
    circuit_breaker: { state: "closed", failures: 0 },
    tags: ["rag", "embeddings"],
    uptime_seconds: 3600,
  },
  // ... more services
];
```

**Visual**: Table with collapsible rows for detailed metrics; real-time updates via WebSocket.

---

### 4.2 Router Decision Panel
**Location**: `ui_service/src/components/mesh/RouterPanel.tsx`

**Features**:
- **Query Display**: Original user query.
- **Decision Output**: Selected service, confidence score, reasoning summary.
- **Candidate Comparison**: Table of all services with semantic/resource scores.
- **Fallback Path**: If triggered, show why primary failed and fallback chosen.

**Example**:
```
Query: "Analyze this code for bugs"
Decision: llm-coding (DeepSeek)
Confidence: 92%
Reasoning: High semantic match for "code" + "bugs"; 5/6 threads available.

Candidates:
| Service    | Semantic | Resource | Total | Breaker |
|------------|----------|----------|-------|---------|
| llm-coding | 95       | 83       | 92    | Closed  |
| llm-rag    | 40       | 100      | 64    | Closed  |
| llm-review | 70       | 50       | 62    | Open    |

Fallback: llm-rag (if llm-coding unavailable)
```

---

### 4.3 Timeline Waterfall with Resource Overlays
**Location**: `ui_service/src/components/mesh/TimelineView.tsx`

**Features**:
- **Span Hierarchy**: Tree view of operations (route → dispatch → inference → tool call).
- **Resource Overlays**: Line graphs showing threads/memory usage over time.
- **C++ Span Integration**: Spans from llama.cpp shown as nested children.
- **Correlation ID Linking**: Click span to see all related operations across services.

**Visual**: Horizontal bars (Gantt-style) with color-coded resource usage (green <50%, yellow 50-80%, red >80%).

---

## 5. Testing & Validation Strategy

### 5.1 Unit Tests (Expand `tests/unit/`)
- **Router Scoring**: Mock registry with varying resource states; verify scoring formula.
- **Circuit Breaker**: Simulate memory threshold breaches; confirm breaker opens.
- **Registry**: Test heartbeat expiry, service updates, capability parsing.

### 5.2 Integration Tests (Expand `tests/integration/`)
- **Multi-Agent Flow**: End-to-end `plan_code_review` workflow; verify 3 services called.
- **Resource Exhaustion**: Spawn heavy load on one service; confirm router redirects to fallback.
- **Crash & Resume**: Kill LLM service mid-inference; verify checkpoint recovery and re-routing.

### 5.3 Performance Benchmarks (New: `tests/benchmarks/`)
- **Router Latency**: Measure P50/P95/P99 for routing decisions (<100ms target).
- **Throughput**: Concurrent requests across services; confirm no thread pool saturation.
- **Memory Stability**: Run 1000 inferences; verify no memory leaks (arena usage stable).

### 5.4 Stress Tests
- **Thread Starvation**: Submit requests > thread pool capacity; confirm graceful queueing.
- **Circuit Breaker Recovery**: Trigger breaker with artificial failures; verify auto-recovery after timeout.

---

## 6. Risk Register & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Router model footprint** (3-4GB) exceeds Agent Service memory | High | Medium | Use lighter model (1.5B); fall back to heuristic routing if OOM |
| **Thread pool exhaustion** under heavy load | High | High | Enforce queue depth limits; return 503 with retry-after header |
| **Memory leaks** in C++ arena management | High | Low | Automated leak detection with Valgrind in CI; arena usage dashboards |
| **Circuit breaker false positives** (transient failures) | Medium | Medium | Increase threshold to 5 failures; add jitter to timeout |
| **UI lag** from real-time span streaming | Medium | Medium | Sample spans (10-20%); buffer/batch updates to 100ms intervals |
| **Polyglot gRPC versioning** (proto mismatches) | Low | Low | Pin proto versions; use buf for schema validation in CI |

---

## 7. Documentation Deliverables

### 7.1 New Documents (Create in `docs/`)
- `docs/service_registry.md`: Registration protocol, capability schema, heartbeat mechanics.
- `docs/router_scoring.md`: Scoring formula, prompt templates, fallback logic.
- `docs/cpp_tracing.md`: Instrumentation guide for C++ services, span propagation.
- `docs/workflows.md`: Multi-agent workflow templates, node definitions, checkpointing.
- `docs/polyglot_services.md`: Swift/ObjC++ service setup, gRPC bindings, registration.

### 7.2 Updates to Existing Docs
- **`ARCHITECTURE.md`**: Add mesh architecture diagrams (control/data/observability planes).
- **`README.MD`**: Add "Agent Mesh" section summarizing differentiators and C++ resource management.
- **`FullPlan.md`**: Reference `AgentMeshPlan.md` for mesh-specific extensions; maintain as base plan.

---

## 8. Jira Epic Structure

### Epic: Agent Mesh - Control Plane
- **AM-P1-T1**: Service Registry with C++ Resource Metadata (5 pts)
- **AM-P1-T2**: Resource-Aware Router Arbitrator (8 pts)
- **AM-P2-T2**: Circuit Breakers with Resource Thresholds (5 pts)

### Epic: Agent Mesh - Data Plane
- **AM-P2-T1**: LangGraph Multi-Agent Workflow Templates (8 pts)
- **AM-P2-T3**: Process Isolation Enforcement (5 pts)
- **AM-P1-T3**: C++ Thread Pool Instrumentation (3 pts)

### Epic: Agent Mesh - Observability Plane
- **AM-P3-T1**: Full Resource Tracing with C++ Hooks (8 pts)
- **UI Dashboard**: Registry View (5 pts), Router Panel (5 pts), Timeline Overlays (8 pts)

### Epic: Agent Mesh - Polyglot Extensions
- **AM-P3-T2**: Swift/ObjC++ Service Template (8 pts)

**Total Effort**: ~68 story points (~7-9 weeks for 3-person team)

---

## 9. Rollout Plan

### Week 1-2: Foundation (Phase 1 Extensions)
- Complete AM-P1-T1, AM-P1-T2, AM-P1-T3.
- **Demo**: Router selects services based on resource availability; spans show thread usage.

### Week 3-5: Hardening (Phase 2 Extensions)
- Complete AM-P2-T1, AM-P2-T2, AM-P2-T3.
- **Demo**: Multi-agent workflow (plan-code-review) with automatic fallback when service degraded.

### Week 6-7: Observability (Phase 3 Extensions)
- Complete AM-P3-T1 and UI panels.
- **Demo**: Full timeline showing C++ spans; registry view with live resource graphs.

### Week 8-9: Polyglot (Optional)
- Complete AM-P3-T2.
- **Demo**: Swift service integrated into mesh; EventKit bridge callable from Python orchestrator.

---

## 10. Appendix: Configuration Examples

### A. Environment Variables
```bash
# Agent Service
ROUTER_MODEL_PATH=/app/models/qwen2.5-3b-q5.gguf
ROUTER_CONFIDENCE_THRESHOLD=70
ROUTER_FALLBACK_ENABLED=true
REGISTRY_HEARTBEAT_INTERVAL=30
CIRCUIT_BREAKER_THRESHOLD=3
CIRCUIT_BREAKER_TIMEOUT=60

# LLM Service (RAG)
MODEL_PATH=/app/models/mistral-7b-instruct-q5.gguf
LLAMA_THREADS=4
MEMORY_ARENA_MB=4096
MAX_QUEUE_DEPTH=10
SERVICE_TAGS=rag,embeddings

# Observability
OBS_MODE=debug
OTEL_EXPORTER_ENDPOINT=http://jaeger:4318
SPAN_SAMPLE_RATE=1.0  # 100% in debug, 10% in shipping
```

### B. Docker Compose Override for Debug
```yaml
# docker-compose.override.yml
version: '3.8'
services:
  agent_service:
    environment:
      OBS_MODE: debug
      SPAN_SAMPLE_RATE: 1.0
  
  llm_service_rag:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 8G
    environment:
      LLAMA_THREADS: 4
      MEMORY_ARENA_MB: 4096
```

### C. Manual Testing Commands
```bash
# Start mesh in debug mode
OBS_MODE=debug make up

# Trigger multi-agent workflow
curl -X POST http://localhost:50054/agent.v1.AgentService/QueryAgent \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan, code, and review a fibonacci function"}'

# Check service registry
curl http://localhost:50054/agent.v1.AgentService/GetRegistry

# Simulate high load (stress test)
for i in {1..100}; do
  curl -X POST http://localhost:50054/agent.v1.AgentService/QueryAgent \
    -d '{"message": "What is 2+2?"}' &
done
wait

# Verify circuit breakers
docker exec agent_service python -c "from tools.circuit_breaker import get_breaker_states; print(get_breaker_states())"
```

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Router Decision Latency (P95) | <100ms | Span duration for `agent.route` |
| Service Throughput | >10 req/s per service | gRPC request rate metrics |
| Memory Stability | <5% variance over 1hr | Arena usage monitoring |
| Circuit Breaker Accuracy | <5% false positives | Manual review of breaker events |
| Thread Utilization | 60-80% average | Span attributes `threads_used/max_threads` |
| Crash Recovery Time | <5s | Time from crash to checkpoint resume |
| UI Responsiveness | <200ms for panel updates | WebSocket message latency |

---

## 12. Conclusion

This Agent Mesh plan transforms the existing gRPC LLM framework into a **production-grade, observable, resource-aware orchestration platform** by:
1. **Adopting service mesh patterns** (control/data/observability planes) for clarity and scalability.
2. **Enforcing C++-style resource discipline** (fixed threads, arenas, process isolation) for deterministic performance on constrained hardware.
3. **Integrating capacity-aware routing** to prevent overload and enable graceful degradation.
4. **Exposing comprehensive observability** through spans, UI dashboards, and resource metrics.
5. **Enabling polyglot extensibility** with Swift/C++ service templates for future native integrations.

The plan **extends** `FullPlan.md` phases with mesh-specific tasks while preserving the sync-first, resumable foundation. Teams can prioritize control plane → data plane → observability → polyglot based on business needs, with each phase delivering incremental value and validatable milestones.

For Jira ticketing, use the epic structure in Section 8; for operational setup, reference configuration examples in Section 10. Questions or refinements should be raised during Phase 1 grooming to ensure alignment with hardware constraints and team capacity.

---
**Status**: Ready for review and team estimation.
**Maintained by**: Architecture Team
**Last Updated**: October 27, 2025
