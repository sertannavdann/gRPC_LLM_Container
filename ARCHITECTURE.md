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
```
┌──────────────────────────────────────────────────────────────────────────┐
| Service         | Container Port | Host Port | Access URL                |
|----------------|----------------|-----------|----------------------------|
| ui_service     | 5000           | 5001      | http://localhost:5001      |
| agent_service  | 50054          | 50054     | (gRPC only, no HTTP)       |
| llm_service    | 50051          | 50051     | (gRPC only)                |
| chroma_service | 50052          | 50052     | (gRPC only)                |
└──────────────────────────────────────────────────────────────────────────┘
```