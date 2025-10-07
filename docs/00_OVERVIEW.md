# System Overview

## Introduction

The gRPC_LLM_Container is a distributed RAG (Retrieval-Augmented Generation) system built on microservices architecture. The system is designed around a **central agent orchestrator** that acts as the decision-making hub, coordinating multiple specialized services to provide intelligent, context-aware responses.

## Core Philosophy

### Agent as Denominator

The **Agent Service** is the single point of arbitration for all operations. This design principle means:

- **Centralized Intelligence**: All tool selection, context management, and error handling happens in one place
- **Simplified Integration**: External systems (n8n, Temporal, etc.) only need to interface with the agent
- **Consistent Behavior**: Circuit breakers, retries, and fallback logic are applied uniformly
- **Traceable Execution**: Every decision is logged and can be audited through metrics

### Why This Matters

Traditional RAG systems often scatter decision logic across multiple components, leading to:
- Inconsistent error handling
- Duplicate retry logic
- Difficult debugging
- Complex integration points

Our agent-centric approach consolidates all orchestration logic, making the system easier to understand, maintain, and extend.

## System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Orchestrator                      │
│  - Tool Selection (Weighted)                                 │
│  - Context Management                                        │
│  - Circuit Breakers                                          │
│  - Persistent Memory                                         │
└────────┬─────────┬──────────┬──────────┬────────────────────┘
         │         │          │          │
    ┌────▼───┐ ┌──▼────┐ ┌───▼────┐ ┌──▼──────────┐
    │  LLM   │ │Chroma │ │ Tool   │ │  CppLLM     │
    │Service │ │Service│ │Service │ │  Bridge     │
    └────────┘ └───────┘ └────────┘ └──┬──────────┘
                                        │
                                   ┌────▼────────┐
                                   │   Swift     │
                                   │ AppIntents  │
                                   └─────────────┘
```

## Service Responsibilities

### 1. Agent Service (Port 50054)
**Role**: Central orchestrator and decision maker

**Responsibilities**:
- Parse user queries and determine required tools
- Manage conversation context and history
- Apply circuit breakers to failing tools
- Collect and expose metrics
- Maintain SQLite checkpointing for conversation continuity

**Key Technologies**: Python, LangGraph, SQLite, gRPC

### 2. LLM Service (Port 50051)
**Role**: Natural language generation and understanding

**Responsibilities**:
- Generate text responses from prompts
- Stream tokens in real-time
- Enforce JSON schemas when needed
- Provide intent classification

**Key Technologies**: llama.cpp, Metal acceleration, Python bindings

### 3. Chroma Service (Port 50052)
**Role**: Vector database for semantic search

**Responsibilities**:
- Store document embeddings
- Perform similarity searches
- Manage document metadata
- Filter results by relevance scores

**Key Technologies**: ChromaDB, FAISS, Python

### 4. Tool Service (Port 50053)
**Role**: Execute specialized tools and APIs

**Responsibilities**:
- Web search via SERPER API
- Mathematical expression evaluation
- Extensible tool registry
- Tool-specific error handling

**Key Technologies**: Python, sympy, requests

### 5. CppLLM Bridge (Port 50055)
**Role**: Native device integration for macOS/iOS

**Responsibilities**:
- Expose Siri/Shortcuts via gRPC
- Manage EventKit calendar operations
- Provide low-latency native calls
- Bridge between C++ gRPC and Swift App Intents

**Key Technologies**: C++17, Objective-C++, Swift, gRPC

## Data Flow Example

### User Query: "Schedule a meeting with Alex tomorrow at 3pm"

```
1. User → Agent Service
   POST /QueryAgent {"user_query": "Schedule a meeting..."}

2. Agent → Chroma Service
   Query("Alex preferences") → Returns: "Alex prefers afternoon meetings"

3. Agent → LLM Service
   Generate(prompt + context) → Returns: {"function_call": "schedule_meeting"}

4. Agent → CppLLM Bridge
   TriggerScheduleMeeting(...) → Returns: {"event_identifier": "evt-123"}

5. Agent → User
   {"final_answer": "Meeting scheduled with event ID: evt-123"}
```

## Key Architectural Decisions

### 1. gRPC for Inter-Service Communication

**Why**: 
- Strongly typed contracts (protobuf)
- Built-in streaming support
- Language-agnostic
- Excellent performance

**Alternative Considered**: REST + JSON
**Why Not**: Lacks streaming, more overhead, loosely typed

### 2. LangGraph for Agent Orchestration

**Why**:
- Explicit state management
- Checkpointing for conversation continuity
- Conditional edges for dynamic routing
- SQLite persistence

**Alternative Considered**: Custom state machine
**Why Not**: Would duplicate LangGraph's features

### 3. SQLite for Agent Memory

**Why**:
- Embedded, no separate server
- ACID transactions
- Good enough for single-node deployment
- Easy backup and migration

**Alternative Considered**: Redis
**Why Not**: Adds infrastructure complexity for MVP

### 4. Native C++ Bridge for Apple Integration

**Why**:
- Direct access to EventKit/App Intents
- Lower latency than Python/Swift bridge
- Can compile as standalone binary
- Metal acceleration for future ML workloads

**Alternative Considered**: Python → Swift via subprocess
**Why Not**: Higher latency, complex error handling

## Scalability Considerations

### Current State (MVP)
- Single instance per service
- SQLite for agent memory (local only)
- No authentication/authorization
- No rate limiting

### Future Enhancements
- **Horizontal Scaling**: Multiple agent instances with Redis/Postgres for shared memory
- **Load Balancing**: nginx/Envoy in front of agent service
- **Authentication**: JWT tokens, API keys
- **Rate Limiting**: Redis-based token bucket
- **Observability**: OpenTelemetry traces across all services

## Integration Points

### For n8n / Workflow Engines

**Recommended Pattern**:
1. Send query to Agent Service
2. Parse response JSON
3. Branch on `tools_used` field
4. Trigger follow-up actions (email, webhooks, etc.)

**Benefits**:
- No need to duplicate tool selection logic
- Automatic error handling and retries
- Consistent context management

### For Custom Applications

**Recommended Pattern**:
1. Import shared clients (Python)
2. Call agent directly: `AgentClient().query("...")`
3. Process structured response

**Benefits**:
- Type-safe protobuf messages
- Automatic retry and circuit breaking
- Shared metrics and logging

## Next Steps

- [Architecture Details](./01_ARCHITECTURE.md)
- [Agent Service Deep Dive](./02_AGENT_SERVICE.md)
- [Apple Integration Guide](./03_APPLE_INTEGRATION.md)
- [n8n Integration](./04_N8N_INTEGRATION.md)
- [Testing & Development](./05_TESTING.md)
