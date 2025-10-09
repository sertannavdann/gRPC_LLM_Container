# Architecture Evolution Diagrams

## Current Architecture (gRPC Microservices)

```
┌─────────────────────────────────────────────────┐
│           External Client (n8n, API)            │
└───────────────────┬─────────────────────────────┘
                    │ gRPC
┌───────────────────▼─────────────────────────────┐
│         Agent Service (LangGraph)               │
│  - ToolRegistry (gRPC stubs)                    │
│  - WorkflowBuilder (LangGraph nodes)            │
│  - Circuit breakers                             │
│  - SQLite checkpointing                         │
└─────┬────────┬──────────┬────────────┬──────────┘
      │        │          │            │
      │ gRPC   │ gRPC     │ gRPC       │ gRPC
      ▼        ▼          ▼            ▼
┌─────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│   LLM   │ │ Chroma │ │  Tool  │ │  CppLLM  │
│ Service │ │Service │ │Service │ │  Bridge  │
│         │ │        │ │        │ │          │
│llama.cpp│ │ Vector │ │Web/Math│ │ EventKit │
└─────────┘ └────────┘ └────────┘ └──────────┘
```

**Limitations:**
- ❌ Tools are gRPC stubs (hard to write)
- ❌ No LangChain/CrewAI integration
- ❌ Complex testing (requires full stack)
- ❌ Can't mix search and non-search tools
- ❌ No standard interoperability (MCP)

---

## Target Architecture (ADK-Inspired + Local Inference)

```
┌─────────────────────────────────────────────────┐
│    External Clients (n8n, MCP, API, iOS App)    │
└────────┬────────────────────────────┬───────────┘
         │ REST/gRPC                  │ MCP
         ▼                            ▼
┌────────────────────┐    ┌──────────────────────┐
│   Agent Service    │    │    MCP Bridge        │
│                    │◄───┤  (Port 50056)        │
│  Modern Tools:     │    │                      │
│  - LocalRegistry   │    │  Exposes tools to    │
│  - Function Tools  │    │  other systems       │
│  - LangChain wrap  │    └──────────────────────┘
│  - CrewAI wrap     │
│  - Agent-as-Tool   │
└─────┬──────────────┘
      │
      ├─────────────────────────────┐
      │                             │
      ▼                             ▼
┌─────────────────────┐   ┌─────────────────────┐
│  Specialized Agents │   │   Direct Services   │
│                     │   │                     │
│ ┌─────────────────┐ │   │ - LLM Service       │
│ │ Search Agent    │ │   │   (llama.cpp)       │
│ │ - Chroma tool   │ │   │                     │
│ │ - Vector search │ │   │ - CppLLM Bridge     │
│ └─────────────────┘ │   │   (EventKit/Swift)  │
│                     │   │                     │
│ ┌─────────────────┐ │   │ - Telemetry         │
│ │ Calendar Agent  │ │   │   (Grafana-style)   │
│ │ - EventKit tool │ │   └─────────────────────┘
│ │ - Date tool     │ │
│ └─────────────────┘ │
│                     │
│ ┌─────────────────┐ │
│ │ Research Agent  │ │
│ │ - Web search    │ │
│ │ - Math solver   │ │
│ └─────────────────┘ │
└─────────────────────┘
```

**Advantages:**
- ✅ Tools are Python functions (easy to write)
- ✅ Native LangChain/CrewAI support
- ✅ Unit testable without Docker
- ✅ Agent-as-Tool solves mixing limitation
- ✅ MCP standard for interoperability
- ✅ Still 100% local inference (zero cloud cost)

---

## Tool Creation: Before vs After

### Before (gRPC Stub)
```
Step 1: Define proto message
┌─────────────────────────────┐
│ // tool.proto               │
│ message ToolRequest {       │
│   string tool_name = 1;     │
│   map<string, Value> params │
│ }                           │
└─────────────────────────────┘
                │
                ▼
Step 2: Generate code
┌─────────────────────────────┐
│ $ make proto-gen            │
│ $ docker build ...          │
└─────────────────────────────┘
                │
                ▼
Step 3: Implement service
┌─────────────────────────────┐
│ class ToolService:          │
│   def CallTool(req, ctx):   │
│     if req.tool_name == ..  │
└─────────────────────────────┘
                │
                ▼
Step 4: Register stub
┌─────────────────────────────┐
│ registry.register(          │
│   func=tool_client.call_tool│
│ )                           │
└─────────────────────────────┘

Total Time: ~1 hour
Lines of Code: ~100+
Testing: Requires full gRPC stack
```

### After (Python Function)
```
Step 1: Write function with docstring
┌─────────────────────────────────────┐
│ def web_search(                     │
│     query: str,                     │
│     max_results: int = 5            │
│ ) -> Dict[str, Any]:                │
│     """Search the web.              │
│                                     │
│     Args:                           │
│         query: Search query         │
│         max_results: Max results    │
│                                     │
│     Returns:                        │
│         Dict with status and results│
│     """                             │
│     # Implementation                │
│     return {"status": "success"...} │
└─────────────────────────────────────┘
                │
                ▼
Step 2: Register (auto-schema extraction)
┌─────────────────────────────────────┐
│ registry.register_function(         │
│     web_search                      │
│ )                                   │
└─────────────────────────────────────┘

Total Time: ~5 minutes
Lines of Code: ~20
Testing: Direct function call
```

---

## Agent-as-Tool Pattern (Solving Tool Mixing)

### Problem: Can't Mix Search and Non-Search Tools
```
❌ DOESN'T WORK:
┌──────────────────────┐
│   Root Agent         │
│                      │
│ Tools:               │
│ - vector_search      │◄─── Search tool
│ - web_search         │◄─── Search tool
│ - schedule_meeting   │◄─── Non-search tool
│ - get_date           │◄─── Non-search tool
└──────────────────────┘

Error: "Cannot mix search and non-search tools"
```

### Solution: Agent-as-Tool Pattern
```
✅ WORKS:
┌──────────────────────────────────┐
│   Root Agent                     │
│                                  │
│ Tools:                           │
│ - search_agent (Agent-as-Tool)   │
│ - calendar_agent (Agent-as-Tool) │
│ - web_search (function)          │
│ - get_date (function)            │
└──────────────────────────────────┘
      │                    │
      ▼                    ▼
┌─────────────┐    ┌──────────────┐
│Search Agent │    │Calendar Agent│
│             │    │              │
│Tools:       │    │Tools:        │
│-vector_srch │    │-schedule_mtg │
│             │    │-get_date     │
└─────────────┘    └──────────────┘

Each specialized agent handles its domain.
Root agent routes to appropriate specialist.
```

---

## Local Inference Flow (iOS Deployment)

### Development (Current)
```
┌──────────────┐   gRPC    ┌──────────────┐
│   Mac Client │◄─────────►│Docker Stack  │
│              │            │              │
│ Python CLI   │            │ 4 services   │
└──────────────┘            └──────────────┘
                                   │
                                   ▼
                            ┌──────────────┐
                            │ llama.cpp    │
                            │ (GGUF model) │
                            └──────────────┘
```

### Production (iOS)
```
┌────────────────────────────────────────┐
│         iOS App (Swift)                │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │   LocalAgent Framework           │ │
│  │   - Function tools               │ │
│  │   - Agent-as-Tool                │ │
│  │   - MCP client (optional)        │ │
│  └─────────────┬────────────────────┘ │
│                │ in-process           │
│                ▼                      │
│  ┌──────────────────────────────────┐ │
│  │   CoreML Model                   │ │
│  │   (Converted from GGUF)          │ │
│  │   - Metal acceleration           │ │
│  │   - Optimized for iOS            │ │
│  └──────────────────────────────────┘ │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │   Native Integrations            │ │
│  │   - EventKit (Calendar)          │ │
│  │   - Contacts                     │ │
│  │   - Siri/Shortcuts               │ │
│  └──────────────────────────────────┘ │
└────────────────────────────────────────┘

No Docker, No Network, 100% On-Device
```

---

## MCP Integration (Future)

```
┌─────────────────────────────────────────────────┐
│           Your gRPC LLM Container               │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │   MCP Server (Port 50056)                 │ │
│  │                                           │ │
│  │   Exposed Tools:                          │ │
│  │   - schedule_meeting                      │ │
│  │   - web_search                            │ │
│  │   - vector_search                         │ │
│  │   - solve_math                            │ │
│  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
                    │ MCP Protocol
                    │ (Standard)
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
┌─────────┐  ┌──────────┐  ┌────────────┐
│ Claude  │  │  Other   │  │   n8n      │
│ Desktop │  │  Agents  │  │  Workflows │
│         │  │          │  │            │
│ (MCP    │  │ (MCP     │  │ (MCP       │
│ client) │  │ client)  │  │ connector) │
└─────────┘  └──────────┘  └────────────┘

Your tools become available to ANY MCP-compatible system!
```

---

## Migration Timeline

```
Week 1-2: Foundation
├── Create LocalToolRegistry
├── Refactor 1-2 tools as functions
└── Prove concept works

Week 3-4: Tool Migration
├── Convert all existing tools
├── Add LangChain/CrewAI wrappers
└── Implement telemetry callbacks

Week 5-6: Agent Framework
├── Build LocalAgent class
├── Create specialized agents
├── Implement Agent-as-Tool
└── Test iOS compatibility

Week 7-8: MCP & iOS
├── MCP server implementation
├── CoreML model conversion
├── Swift framework
└── Siri integration

Week 9-10: Production
├── Performance testing
├── Documentation
├── Migration guide
└── Deprecate old interfaces
```

---

## Cost Comparison

### Cloud-Based (Traditional)
```
GPT-4 Turbo: $0.01 per 1K tokens
100,000 queries/day × 500 tokens avg = 50M tokens
Cost: $500/day = $15,000/month = $180,000/year
```

### Your System (Local Inference)
```
Local llama.cpp: $0 per inference
100,000 queries/day × forever
Cost: $0/day = $0/month = $0/year

Hardware: 1× Mac Mini M2 (~$600)
ROI: 1 day of GPT-4 costs = Your entire hardware cost
```

**This is why local inference matters for iOS!**
