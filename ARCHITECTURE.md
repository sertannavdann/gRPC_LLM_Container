# gRPC LLM UI Service - Architecture & Routing

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
│  │ │         value: "agent_service:50054"           │  │    │
│  │ └────────────────────────────────────────────────┘  │    │
│  │         │ gRPC                                      │    │
│  │         ▼                                           │    │
│  └─────────────────────────────────────────────────────┘    │
│              │                                              │
│              │ Docker Network: rag_net                      │
│              ▼                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ agent_service (Python gRPC)                         │    │
│  │ Container Port: 50054                               │    │
│  │                                                     │    │
│  │ Service: agent.AgentService                         │    │
│  │ Method: QueryAgent(user_query, debug_mode)          │    │
│  │                                                     │    │
│  │ Dependencies:                                       │    │
│  │   → llm_service:50051                               │    │
│  │   → chroma_service:50052                            │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Port Mapping Reference
```log
┌──────────────────────────────────────────────────────────────────────────┐
| Service         | Container Port | Host Port | Access URL                |
|-----------------|----------------|-----------|---------------------------|
| ui_service      | 5000           | 5001      | http://localhost:5001     |
| agent_service   | 50054          | 50054     | (gRPC only, no HTTP)      |
| llm_service     | 50051          | 50051     | (gRPC only)               |
| chroma_service  | 50052          | 50052     | (gRPC only)               |
└──────────────────────────────────────────────────────────────────────────┘
```

## 🔄 Crash Recovery

The system implements automatic crash recovery for interrupted workflows using SQLite checkpointing and WAL mode.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Service Lifecycle                                    │
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

- `AGENT_CHECKPOINT_DB`: Path to SQLite checkpoint database (default: `./data/agent_checkpoints.db`)
- Recovery scan runs automatically on agent service startup
- Max recovery attempts: 3 (hardcoded in `core/recovery.py`)
- Inactive thread threshold: 5 minutes

### Monitoring

Check agent service logs for recovery activity:
```bash
docker logs agent_service | grep -i recovery
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


