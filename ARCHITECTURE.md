# gRPC LLM Orchestrator Service - Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Docker Host (macOS)                                        │
│                                                             │
│  Browser: http://localhost:5001                             │
│          │                                                  │
│          ▼                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ui_service (Next.js 14)                             │    │
│  │ Container Port: 5000 → Host Port: 5001              │    │
│  │                                                     │    │
│  │ ┌────────────────────────────────────────────────┐  │    │
│  │ │ /api/chat (API Route)                          │  │    │
│  │ │   → grpc-client.ts                             │  │    │
│  │ │      → getAgentAddress()                       │  │    │
│  │ │         reads: process.env['AGENT_SERVICE...'] │  │    │
│  │ │         value: "orchestrator:50054"            │  │    │
│  │ └────────────────────────────────────────────────┘  │    │
│  │         │ gRPC                                      │    │
│  │         ▼                                           │    │
│  └─────────────────────────────────────────────────────┘    │
│              │                                              │
│              │ Docker Network: rag_net                      │
│              ▼                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ orchestrator (Python gRPC)                          │    │
│  │ Container Port: 50054                               │    │
│  │                                                     │    │
│  │ ┌─────────────────────────────────────────────────┐ │    │
│  │ │ SimpleRouter (Keyword-based Routing)            │ │    │
│  │ │  - web_search: search|find|google|latest       │ │    │
│  │ │  - math_solver: calculate|math|equation         │ │    │
│  │ │  - load_web_page: url|https|website            │ │    │
│  │ │  - chroma_service: rag|document|knowledge      │ │    │
│  │ │  Performance: <1ms routing decisions           │ │    │
│  │ └─────────────────────────────────────────────────┘ │    │
│  │ ┌─────────────────────────────────────────────────┐ │    │
│  │ │ AgentWorkflow (LangGraph)                       │ │    │
│  │ │  - Tool Registry (3 builtin tools)             │ │    │
│  │ │  - Workflow Graph with Checkpointing           │ │    │
│  │ │  - Max 5 iterations per query                  │ │    │
│  │ └─────────────────────────────────────────────────┘ │    │
│  │ ┌─────────────────────────────────────────────────┐ │    │
│  │ │ CheckpointManager                               │ │    │
│  │ │  - SQLite persistence (WAL mode)                │ │    │
│  │ │  - Conversation history                         │ │    │
│  │ │  - Crash recovery support                       │ │    │
│  │ └─────────────────────────────────────────────────┘ │    │
│  │                                                     │    │
│  │ Service: agent.AgentService                         │    │
│  │ Method: QueryAgent(user_query, debug_mode)          │    │
│  │                                                     │    │
│  │ Dependencies:                                       │    │
│  │   → llm_service:50051 (via LLMClient)               │    │
│  │   → chroma_service:50052 (via ChromaClient)         │    │
│  └─────────────────────────────────────────────────────┘    │
│              │                           │                  │
│              ▼                           ▼                  │
│  ┌──────────────────┐      ┌──────────────────────────┐    │
│  │  llm_service     │      │  chroma_service          │    │
│  │  Port: 50051     │      │  Port: 50052             │    │
│  │                  │      │                          │    │
│  │  llama.cpp       │      │  ChromaDB                │    │
│  │  Local inference │      │  Vector store            │    │
│  └──────────────────┘      └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Port Mapping Reference
```log
┌──────────────────────────────────────────────────────────────────────────┐
| Service         | Container Port | Host Port | Access URL                |
|-----------------|----------------|-----------|---------------------------|
| ui_service      | 5000           | 5001      | http://localhost:5001     |
| orchestrator    | 50054          | 50054     | (gRPC only, no HTTP)      |
| llm_service     | 50051          | 50051     | (gRPC only)               |
| chroma_service  | 50052          | 50052     | (gRPC only)               |
└──────────────────────────────────────────────────────────────────────────┘
```

## 🎯 Orchestrator Architecture

The orchestrator service is a unified coordination layer combining routing, agent workflows, and service communication.

### Components

#### 1. SimpleRouter (Keyword-Based Routing)
- **Purpose**: Fast, deterministic query routing
- **Performance**: <1ms routing decisions (100x faster than 3B parameter model)
- **Strategy**: Pattern matching on keywords and query analysis

**Routing Rules**:
```python
web_search:      search|find|look up|google|latest|news
math_solver:     calculate|compute|solve|math|equation|sum
load_web_page:   url|https|website|page|fetch|download
chroma_service:  rag|document|knowledge|remember|recall
```

**Decision Process**:
1. Convert query to lowercase
2. Check for keyword matches in each category
3. Calculate confidence scores based on matches
4. Return highest-scoring route + confidence
5. Default to `llm_service/direct` if no matches

#### 2. AgentWorkflow (LangGraph)
- **Purpose**: Execute multi-step reasoning workflows
- **Framework**: LangGraph with StateGraph
- **Checkpointing**: SQLite-based conversation persistence
- **Max Iterations**: 5 per query (configurable via `AGENT_MAX_ITERATIONS`)

**Workflow Nodes**:
- `llm`: Generate response using LLM service
- `tools`: Execute selected tools
- `validate`: Validate responses
- `end`: Terminal node

**State Management**:
```python
AgentState = {
    "messages": List[BaseMessage],
    "iteration": int,
    "tools_used": List[str],
    "current_thought": str,
    "routing_hint": str  # From SimpleRouter
}
```

#### 3. LLMEngineWrapper
- **Purpose**: Adapt LLMClient to AgentWorkflow's expected interface
- **Methods**:
  - `generate(messages, tools, temperature, max_tokens)` → dict
  - `invoke(messages, **kwargs)` → AIMessage
- **Error Handling**: Graceful degradation on LLM failures

#### 4. CheckpointManager
- **Database**: SQLite with WAL mode (Write-Ahead Logging)
- **Location**: `/app/data/agent_memory.sqlite` (in container)
- **Features**:
  - Conversation history persistence
  - Thread-based state management
  - Crash recovery support

### Request Flow

```
1. gRPC Request → orchestrator:50054
   ↓
2. SimpleRouter.route(query)
   ├─ Keyword analysis
   ├─ Confidence scoring
   └─ Route decision (e.g., "agent_service/web_search", 0.75)
   ↓
3. Create AgentState with routing_hint
   ↓
4. AgentWorkflow.invoke(state)
   ├─ LLM Node: Generate response via LLMEngineWrapper
   ├─ Tools Node: Execute tools if needed
   ├─ Validate Node: Check response quality
   └─ Checkpoint: Save state after each step
   ↓
5. Format AgentReply
   ├─ final_answer: LLM response
   ├─ context_used: Tools executed
   ├─ sources: Thread ID and metadata
   └─ execution_graph: Workflow trace
   ↓
6. Return gRPC Response
```

## 🔄 Crash Recovery

The orchestrator implements automatic crash recovery for interrupted workflows using SQLite checkpointing and WAL mode.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator Service Lifecycle                             │
│                                                             │
│  1. Startup → Recovery Scan                                 │
│     ├─ Scan for incomplete threads (>5 min inactive)       │
│     ├─ Validate checkpoint integrity                        │
│     ├─ Load last checkpoint state                           │
│     └─ Attempt recovery (max 3 attempts per thread)         │
│                                                             │
│  2. Query Processing                                        │
│     ├─ Mark thread as "incomplete" (start)                 │
│     ├─ Execute workflow with checkpointing                  │
│     └─ Mark thread as "complete" (success)                  │
│                                                             │
│  3. Crash → Thread remains "incomplete"                     │
│     └─ Recovered on next startup                            │
└─────────────────────────────────────────────────────────────┘
```

### How It Works

1. **Checkpoint Tracking**: Each workflow execution is marked as "incomplete" when started and "complete" when finished successfully.

2. **Startup Scan**: On service restart, the RecoveryManager scans for threads marked "incomplete" that have been inactive for >5 minutes.

3. **Checkpoint Validation**: Each recovered thread's checkpoint is validated for integrity before attempting recovery.

4. **Resume Execution**: Valid checkpoints are loaded and workflows can resume from the last completed step.

5. **Max Attempts**: Threads that fail recovery 3 times are abandoned to prevent infinite loops.

### Configuration

- `AGENT_CHECKPOINT_DB`: Path to SQLite checkpoint database (default: `./data/agent_memory.sqlite`)
- Recovery scan runs automatically on orchestrator startup
- Max recovery attempts: 3 (hardcoded in `core/checkpointing.py`)
- Inactive thread threshold: 5 minutes

### Monitoring

Check orchestrator logs for recovery activity:
```bash
docker logs orchestrator | grep -i recovery
```

Look for:
- "Running startup crash recovery scan"
- "Found N crashed threads"
- "Successfully recovered thread"
- "Recovery complete: X recovered, Y failed"

### Database Structure

**thread_status table**:
```sql
CREATE TABLE thread_status (
    thread_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,  -- 'incomplete' or 'complete'
    last_updated DATETIME NOT NULL
);
```

**WAL Mode**: Enabled via `PRAGMA journal_mode=WAL` for safe concurrent reads/writes.


