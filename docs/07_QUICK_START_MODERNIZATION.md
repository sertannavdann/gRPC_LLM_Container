# Quick Start: Modernizing Your gRPC LLM Container

## TL;DR

Transform your gRPC microservices into an ADK-style local agent framework while keeping local inference.

## Key Changes

### Before (Current)
```python
# Tool registration via gRPC stubs
registry.register(
    name="web_search",
    func=tool_client.call_tool,  # gRPC stub
    description="Search the web"
)
```

### After (ADK-Style)
```python
# Tool registration via Python functions
def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web using Google Serper API.
    
    Args:
        query (str): The search query
        max_results (int): Maximum number of results
    
    Returns:
        Dict with status: {"status": "success", "results": [...]}
    """
    # Implementation...
    return {"status": "success", "results": [...]}

registry.register_function(web_search)
```

## What You Get

1. **Better Developer Experience**: Write tools as simple Python functions
2. **ADK Compatibility**: Familiar API for developers from Google ecosystem  
3. **LangChain/CrewAI Integration**: Use community tools directly
4. **MCP Interoperability**: Expose your tools to other agent systems
5. **Local Inference**: Still using llama.cpp - **zero cloud costs**
6. **iOS Ready**: Same code runs on device with CoreML

## Implementation Priority

### Start Here (Highest Impact)
1. **Create Tool Registry** (`agent_service/tools/registry.py`)
   - Auto-extract schemas from docstrings
   - Wrap existing gRPC calls as functions
   - Support LangChain/CrewAI tools

### Then Do This
2. **Refactor Existing Tools** as functions returning `Dict[str, Any]`
3. **Add Agent-as-Tool** pattern for specialized agents
4. **Implement Telemetry** callbacks (before/after inference)

### Future Enhancements
5. **MCP Server** (port 50056) for cross-system interoperability
6. **CoreML Conversion** for iOS Metal acceleration
7. **Swift Agent Framework** for native iOS integration

## File Structure (Proposed)

```
agent_service/
├── agent_service.py          # Existing orchestrator
├── agents/
│   ├── local_agent.py        # NEW: ADK-style agent class
│   └── specialized/          # NEW: Domain-specific agents
│       ├── search_agent.py
│       ├── calendar_agent.py
│       └── research_agent.py
├── tools/
│   ├── registry.py           # NEW: Modern tool registry
│   ├── calendar.py           # NEW: Function tools
│   ├── web.py                # NEW: Function tools
│   ├── math.py               # NEW: Function tools
│   └── wrappers/             # NEW: LangChain/CrewAI wrappers
│       ├── langchain.py
│       └── crewai.py
├── telemetry/
│   └── collector.py          # NEW: Grafana-style metrics
└── mcp/
    └── server.py             # NEW: MCP protocol bridge
```

## Migration Path

### Phase 1: Add Modern Tools (No Breaking Changes)
```python
# In agent_service.py - keep existing code, add new registry
from agent_service.tools.registry import LocalToolRegistry

class AgentOrchestrator:
    def __init__(self):
        # OLD: Keep for backward compatibility
        self.legacy_tools = self._setup_legacy_tools()
        
        # NEW: Add modern tool registry
        self.modern_registry = LocalToolRegistry()
        self._register_modern_tools()
    
    def _register_modern_tools(self):
        """Register ADK-style function tools"""
        from agent_service.tools.calendar import get_date, schedule_meeting
        from agent_service.tools.web import web_search
        from agent_service.tools.math import solve_math
        
        self.modern_registry.register_function(get_date)
        self.modern_registry.register_function(schedule_meeting)
        self.modern_registry.register_function(web_search)
        self.modern_registry.register_function(solve_math)
```

### Phase 2: Gradually Migrate Clients
```python
# Support both old and new interfaces
async def process_query(self, query: str, use_modern: bool = False):
    if use_modern:
        return await self.modern_agent.run(query)
    else:
        return self.legacy_workflow.invoke({"messages": [...]})
```

### Phase 3: Deprecate Old Interface
```python
# Eventually remove legacy code
async def process_query(self, query: str):
    return await self.modern_agent.run(query)
```

## Example: Adding a New Tool

### 1. Write the Function
```python
# agent_service/tools/weather.py
from typing import Dict, Any

def get_weather(city: str, units: str = "celsius") -> Dict[str, Any]:
    """
    Get current weather for a city.
    
    Args:
        city (str): City name
        units (str): Temperature units (celsius or fahrenheit)
    
    Returns:
        Dict with weather data: {"status": "success", "temp": 22, "condition": "sunny"}
    """
    # Your implementation here
    return {"status": "success", "temp": 22, "condition": "sunny", "city": city}
```

### 2. Register It
```python
# agent_service/agent_service.py
from agent_service.tools.weather import get_weather

# In AgentOrchestrator.__init__:
self.modern_registry.register_function(get_weather)
```

### 3. That's It!
The agent automatically:
- Extracts schema from docstring
- Knows when to call it based on description
- Validates parameters
- Handles errors

## Testing

```bash
# Test new tool system without Docker
conda run -n llm python -m examples.adk_style_tools

# Test in full system
make up
adk web  # If you add ADK CLI support
```

## Benefits Recap

| Aspect | Before | After |
|--------|--------|-------|
| Tool Creation | Write gRPC service + proto | Write Python function |
| Time to Add Tool | ~1 hour | ~5 minutes |
| Type Safety | Manual proto definition | Auto-extracted from hints |
| Documentation | Separate proto comments | Docstring = documentation |
| Testing | Requires gRPC stack | Unit test functions directly |
| Community Tools | Manual wrapping | Native LangChain/CrewAI support |
| Inference Cost | Local (free) | Still local (free) ✓ |
| iOS Deployment | Docker + gRPC | CoreML + local calls |

## Next Actions

1. **Read** `docs/06_MODERNIZATION_STRATEGY.md` for full plan
2. **Review** `examples/adk_style_tools.py` for code patterns
3. **Create** `agent_service/tools/registry.py` as first PR
4. **Refactor** one existing tool (e.g., web_search) as proof-of-concept
5. **Test** side-by-side with existing system

## Questions?

- **"Do I lose gRPC?"** No, you can still use gRPC internally. Just wrap calls in functions.
- **"What about existing clients?"** Support both interfaces during migration.
- **"Does this require cloud?"** No! Still 100% local inference with llama.cpp.
- **"Is this production ready?"** The pattern is proven (Google ADK), implementation is phased.
- **"iOS performance?"** Better - CoreML models run faster than GGUF on Metal.

## Resources

- [Google ADK Documentation](https://cloud.google.com/agent-development-kit/docs)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Grafana Agent](https://grafana.com/docs/agent/latest/)
- [LangChain Tools](https://python.langchain.com/docs/modules/tools/)
- [CrewAI Tools](https://docs.crewai.com/core-concepts/Tools/)
