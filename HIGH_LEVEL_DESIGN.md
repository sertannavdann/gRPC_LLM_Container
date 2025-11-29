# High-Level Design (HLD) - gRPC LLM Agent Framework

## 1. Executive Summary

The **gRPC LLM Agent Framework** is a distributed, microservices-based architecture designed to orchestrate autonomous AI agents. It follows the **"Swap, Don't Stack"** philosophy, prioritizing modularity, interface-based design, and strict separation of concerns.

The system implements a **Supervisor-Worker Mesh** pattern where a central Orchestrator (Supervisor) manages conversation state and high-level reasoning, while specialized Worker nodes perform specific tasks (coding, data analysis, etc.). All components communicate via high-performance gRPC channels.

## 2. Architectural Principles

*   **Microservices First**: Each component (LLM, Vector DB, UI, Orchestrator) is an independent container.
*   **Protocol Buffers (gRPC)**: Strongly typed contracts define all inter-service communication.
*   **SOLID Design**:
    *   *Single Responsibility*: Services do one thing well.
    *   *Open/Closed*: New capabilities (Workers) are added without modifying the Orchestrator.
    *   *Dependency Inversion*: High-level logic depends on abstract interfaces (Clients), not concrete implementations.
*   **Resilience**: Circuit breakers for tools, crash recovery for conversation threads.

## 3. System Architecture

### 3.1 High-Level Diagram

```mermaid
graph TD
    User[User / Browser] <-->|HTTP/gRPC-Web| UI[UI Service (Next.js)]
    UI <-->|gRPC| Orch[Orchestrator (Supervisor)]
    
    subgraph "Core Infrastructure"
        Orch <-->|gRPC| LLM[LLM Service (Llama.cpp)]
        Orch <-->|gRPC| Chroma[Chroma Service (Vector DB)]
        Orch <-->|gRPC| Reg[Registry Service]
    end
    
    subgraph "Worker Mesh"
        Reg <-->|Registration| W1[Worker: Coding]
        Reg <-->|Registration| W2[Worker: Analysis]
        Orch -.->|Delegation| W1
        Orch -.->|Delegation| W2
    end
    
    subgraph "Persistence"
        Orch -->|SQLite| State[State Store & Checkpoints]
    end
```

## 4. Component Deep Dive

### 4.1 Orchestrator Service (The Supervisor)
*   **Role**: The central brain of the system. It does not execute heavy tasks itself but coordinates the workflow.
*   **Core Engine**: Uses **LangGraph** to model the agent loop as a state machine (`llm_node` -> `tools_node` -> `validate_node`).
*   **Tooling**:
    *   **LocalToolRegistry**: Manages in-process tools (Math, Search) with **Circuit Breakers** to prevent cascading failures.
    *   **Delegation**: Can delegate complex tasks to Workers via the Registry.
*   **Persistence**: Implements a **CheckpointManager** (SQLite + WAL) to save conversation state after every step, enabling **Crash Recovery**.

### 4.2 Registry Service (The Phonebook)
*   **Role**: Dynamic service discovery for the Worker Mesh.
*   **Function**:
    *   Workers register their capabilities (e.g., `["coding", "python"]`) and endpoints on startup.
    *   Orchestrator queries the Registry to find workers matching a specific capability.
*   **Benefit**: Allows adding new Worker types without restarting the Orchestrator.

### 4.3 Worker Services (The Specialists)
*   **Role**: Stateless execution units for specific domains.
*   **Implementation**:
    *   Lightweight gRPC servers.
    *   Register with `RegistryService` upon boot.
    *   Execute tasks defined by the `WorkerService` protobuf contract.
*   **Examples**: Coding Agent, Data Analysis Agent, Scraper Agent.

### 4.4 LLM Service (The Engine)
*   **Role**: Provides text generation and reasoning capabilities.
*   **Tech Stack**: `llama.cpp` python bindings (via `llama-cpp-python`).
*   **Key Feature**: **Structured Output**. Enforces JSON grammar for tool calling, ensuring 100% valid JSON responses for the Orchestrator to parse.

### 4.5 Chroma Service (The Memory)
*   **Role**: Long-term semantic memory.
*   **Tech Stack**: ChromaDB wrapped in a gRPC service.
*   **Function**: Stores and retrieves vector embeddings for RAG (Retrieval Augmented Generation).

### 4.6 UI Service (The Interface)
*   **Role**: User interaction layer.
*   **Tech Stack**: Next.js 14, Tailwind CSS, gRPC-web.
*   **Features**:
    *   Real-time chat interface.
    *   Markdown rendering.
    *   Visualizes the "Thought Process" (intermediate tool calls).

## 5. Key Workflows

### 5.1 Standard Query Flow
1.  **User** sends query via UI.
2.  **Orchestrator** receives request, creates a new Thread ID.
3.  **LangGraph** loop starts:
    *   **LLM Node**: Generates a plan or response.
    *   **Tool Node**: If tools are needed (e.g., Web Search), executes them locally.
    *   **Validation Node**: Checks for loops or errors.
4.  **Orchestrator** streams final answer back to UI.

### 5.2 Worker Delegation Flow
1.  **Orchestrator** determines a task requires a specialist (e.g., "Write a Python script").
2.  **Orchestrator** calls `delegate_to_worker` tool.
3.  **Tool** queries **Registry Service**: "Who can do 'coding'?"
4.  **Registry** returns `worker_coding` endpoint (e.g., `worker_coding:50056`).
5.  **Orchestrator** sends gRPC `ExecuteTask` request directly to **Worker**.
6.  **Worker** executes and returns result.
7.  **Orchestrator** incorporates result into conversation context.

### 5.3 Crash Recovery Flow
1.  **Orchestrator** crashes mid-conversation.
2.  **Supervisor** (Docker/K8s) restarts the container.
3.  **RecoveryManager** scans the `thread_status` table in SQLite for "incomplete" threads.
4.  **RecoveryManager** loads the last valid checkpoint for those threads.
5.  **Orchestrator** marks them as recovered (or resumes execution if configured).

## 6. Data Models (Protobuf)

The system relies on strict contracts defined in `shared/proto/`:

*   **`agent.proto`**: `QueryAgent` (User -> Orchestrator).
*   **`llm.proto`**: `Generate` (Orchestrator -> LLM).
*   **`registry.proto`**: `Register`, `Discover` (Worker -> Registry -> Orchestrator).
*   **`worker.proto`**: `ExecuteTask` (Orchestrator -> Worker).

## 7. Scalability & Deployment

*   **Containerization**: All services are Dockerized.
*   **Orchestration**: Currently uses `docker-compose` for local dev, ready for Kubernetes (K8s).
*   **Scaling**:
    *   **Workers**: Can be scaled horizontally (e.g., 5 Coding Workers). The Registry handles load balancing (round-robin or random).
    *   **LLM**: Can be swapped for external APIs (OpenAI/Anthropic) or scaled with multiple GPU containers.
    *   **Orchestrator**: Stateless (except for DB), can be scaled if using a shared DB (PostgreSQL) instead of SQLite.

## 8. Agent0 Enhancements (Implemented)

Based on research from the Agent0 paper (arXiv:2511.16043), the following advanced reasoning features have been integrated:

### 8.1 Multi-Turn Tool Rollouts (Phase 1)
*   **Pattern**: "Stop-and-Go" execution where the LLM pauses at each tool call.
*   **Implementation**: `LLMEngineWrapper._generate_with_tools_multi_turn()` in `orchestrator_service.py`.
*   **Flow**:
    1. LLM generates response with potential tool call.
    2. If `type: "tool_call"`, execution pauses, tool is invoked.
    3. Result is appended to context as a `tool` role message.
    4. LLM continues generation with enriched context.
    5. Loop repeats until `type: "answer"` or `max_tool_iterations` reached.
*   **Config**: `max_tool_iterations=5` (configurable).

### 8.2 Self-Consistency Scoring (Phase 2)
*   **Purpose**: Measure model uncertainty via majority voting.
*   **Implementation**: `core/self_consistency.py` + `LLMService.GenerateBatch` RPC.
*   **Algorithm**:
    1. Generate k samples (default k=5) for the same prompt.
    2. Normalize responses for comparison.
    3. Compute p̂ = (count of majority answer) / k.
    4. If p̂ < threshold (0.6), model is uncertain → trigger tool verification.
*   **API**: `llm_client.generate_batch(prompt, num_samples=5)` returns `{responses, self_consistency_score, majority_answer}`.

### 8.3 Sandbox Service (Phase 3)
*   **Purpose**: Secure execution of LLM-generated code.
*   **Implementation**: `sandbox_service/sandbox_service.py`.
*   **Features**:
    *   Timeout enforcement (default 30s, max 60s).
    *   Memory limits (default 256MB, max 512MB).
    *   Import whitelisting (safe modules only).
    *   Process isolation via `multiprocessing`.
    *   Restricted builtins (no `eval`, `exec`, `open`).
*   **API**: `sandbox_client.execute_code(code, language="python", timeout_seconds=30)`.

### 8.4 Curriculum Learning Signal (Future)
*   **Tracking**: `tool_use_count` is now tracked in LangGraph state for future ADPO training.
*   **Purpose**: Reward efficient tool use in curriculum training.

## 9. Future Roadmap

*   **Phase 4**: Enhanced RAG with document ingestion pipeline.
*   **Phase 5**: Multi-modal support (Image/Audio).
*   **Phase 6**: Kubernetes Helm charts for production deployment.
*   **Phase 7**: Full ADPO training loop with curriculum agent integration.
