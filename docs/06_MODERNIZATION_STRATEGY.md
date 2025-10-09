# Modernization Strategy: Aligning with Google ADK Patterns

## Executive Summary

This document outlines how to evolve the gRPC LLM Container system to align with modern agent frameworks (Google ADK, LangChain, CrewAI) while **maintaining local inference** as a core differentiator. The goal is to provide ADK-like developer experience with zero cloud costs.

## Current State vs. Target State

### Current Architecture
```
Agent Service (LangGraph) → LLM Service (llama.cpp) → Local Model
                          ↘ Tool Service (gRPC)
                          ↘ Chroma Service (gRPC)
                          ↘ CppLLM Bridge (gRPC)
```

### Target Architecture (ADK-Inspired)
```
Local Agent Framework → Local LLM Service → GGUF Models (iOS/macOS optimized)
                     ↘ Tool Registry (LangChain/CrewAI compatible)
                     ↘ Function Tools (Python/Swift)
                     ↘ RAG Tools (Chroma local)
                     ↘ MCP Tools (standardized protocol)
```

## Key Learnings from Google ADK

### 1. **Tool Design Philosophy**

**ADK Pattern:**
- Tools are functions with structured docstrings
- Return dictionaries with `status` keys
- Type hints for all parameters
- No default parameter values (LLMs don't handle them)

**Current Implementation Gap:**
Your `tool_service.py` uses gRPC stubs, not Python functions. This creates friction.

**Recommendation:**
```python
# NEW: agent_service/tools/registry.py
from typing import Dict, Any, Callable
import inspect

class LocalToolRegistry:
    """ADK-style tool registry for local inference"""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, Dict] = {}
    
    def register_function(self, func: Callable):
        """Register a Python function as a tool"""
        # Extract schema from docstring and type hints
        schema = self._extract_schema(func)
        self.tools[func.__name__] = func
        self.schemas[func.__name__] = schema
    
    def register_langchain_tool(self, tool):
        """Wrap LangChain tools for compatibility"""
        wrapped = self._wrap_langchain(tool)
        self.tools[tool.name] = wrapped
        self.schemas[tool.name] = tool.schema
    
    def register_crewai_tool(self, tool, name: str, description: str):
        """Wrap CrewAI tools"""
        wrapped = self._wrap_crewai(tool)
        self.tools[name] = wrapped
        self.schemas[name] = {"description": description}
    
    def _extract_schema(self, func: Callable) -> Dict:
        """Parse Google-style docstrings"""
        doc = inspect.getdoc(func)
        sig = inspect.signature(func)
        
        # Parse Args: and Returns: sections
        schema = {
            "name": func.__name__,
            "description": doc.split("Args:")[0].strip(),
            "parameters": {},
            "returns": {}
        }
        
        for param_name, param in sig.parameters.items():
            schema["parameters"][param_name] = {
                "type": self._python_type_to_json(param.annotation),
                "required": param.default == inspect.Parameter.empty
            }
        
        return schema
```

### 2. **Function Tool Best Practices**

**From ADK Documentation:**
- Fewer parameters (< 5 recommended)
- Simple types (str, int, bool)
- Meaningful names that LLMs understand
- Return `{"status": "success/error", "data": ...}`

**Implementation Example:**
```python
# NEW: agent_service/tools/calendar.py
from datetime import datetime
from typing import Dict

def schedule_meeting(
    person: str,
    start_time_iso8601: str,
    duration_minutes: int
) -> Dict[str, Any]:
    """
    Schedule a meeting with a person using native calendar integration.
    
    Args:
        person (str): Full name of the person to meet with
        start_time_iso8601 (str): Meeting start time in ISO 8601 format
        duration_minutes (int): Duration of the meeting in minutes
    
    Returns:
        A dict with status and event details. For example:
        {"status": "success", "event_id": "evt_123", "message": "Meeting scheduled"}
        or
        {"status": "error", "message": "Calendar access denied"}
    """
    try:
        # Call CppLLM bridge for native EventKit access
        from shared.clients.cpp_llm_client import CppLLMClient
        
        client = CppLLMClient(host="localhost", port=50055)
        result = client.trigger_schedule_meeting(
            person=person,
            start_time=start_time_iso8601,
            duration=duration_minutes
        )
        
        return {
            "status": "success",
            "event_id": result.get("event_id"),
            "message": f"Meeting with {person} scheduled"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def get_date(x_days_from_today: int) -> Dict[str, str]:
    """
    Retrieves a date for today or a day relative to today.
    
    Args:
        x_days_from_today (int): how many days from today? (use 0 for today)
    
    Returns:
        A dict with the date in a formal writing format. For example:
        {"date": "Wednesday, May 7, 2025"}
    """
    from datetime import timedelta
    
    target_date = datetime.today() + timedelta(days=x_days_from_today)
    date_string = target_date.strftime("%A, %B %d, %Y")
    
    return {"date": date_string}
```

### 3. **Agent-as-Tool Pattern**

**Critical for iOS:** This solves the "search tools can't mix with other tools" limitation.

**Implementation:**
```python
# NEW: agent_service/agents/specialized_agents.py

class LocalAgent:
    """Lightweight agent for local inference - ADK-inspired"""
    
    def __init__(
        self,
        name: str,
        model_path: str,  # Path to GGUF model
        description: str,
        instruction: str,
        tools: List[Callable] = None,
        before_inference_callback: Callable = None,
        after_inference_callback: Callable = None
    ):
        self.name = name
        self.description = description
        self.instruction = instruction
        self.tools = tools or []
        self.before_callback = before_inference_callback
        self.after_callback = after_inference_callback
        
        # Local LLM client
        from shared.clients.llm_client import LLMClient
        self.llm = LLMClient(host="localhost", port=50051)
    
    async def run(self, query: str) -> Dict[str, Any]:
        """Execute agent workflow"""
        context = self._build_context(query)
        
        if self.before_callback:
            self.before_callback(context)
        
        # Generate with local model
        response = self.llm.generate(
            prompt=self._build_prompt(context),
            max_tokens=512,
            temperature=0.2
        )
        
        if self.after_callback:
            self.after_callback(response)
        
        # Handle tool calls
        parsed = json.loads(response)
        if "function_call" in parsed:
            tool_result = await self._execute_tool(parsed["function_call"])
            return {"response": tool_result}
        
        return {"response": parsed.get("content")}
    
    def _build_prompt(self, context: Dict) -> str:
        """Build prompt with tool descriptions"""
        tool_descriptions = "\n".join(
            f"- {t.__name__}: {t.__doc__.split('Args:')[0].strip()}"
            for t in self.tools
        )
        
        return f"""{self.instruction}

Available tools:
{tool_descriptions}

User query: {context['query']}

Respond in JSON format with either:
{{"content": "your answer"}}
OR
{{"function_call": {{"name": "tool_name", "arguments": {{...}}}}}}
"""

# Usage: Create specialized agents
search_agent = LocalAgent(
    name="chroma_search_agent",
    model_path="./models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
    instruction="Search the vector database for relevant information",
    tools=[chroma_search_tool]
)

calendar_agent = LocalAgent(
    name="calendar_agent",
    model_path="./models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
    instruction="Help users manage their calendar",
    tools=[schedule_meeting, get_date]
)

# Root agent uses agents-as-tools
root_agent = LocalAgent(
    name="root_orchestrator",
    model_path="./models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
    instruction="Route requests to specialized agents",
    tools=[
        AgentTool(search_agent),
        AgentTool(calendar_agent),
        web_search,  # Regular function tool
        math_solver  # Regular function tool
    ]
)
```

## 4. **Model Context Protocol (MCP) Integration**

**Why This Matters:** MCP is the future of agent interoperability. Your microservices should expose MCP endpoints.

**Implementation Strategy:**
```python
# NEW: agent_service/mcp/server.py
from mcp import MCPServer, Tool as MCPTool

class gRPCtoMCPBridge:
    """Expose gRPC services as MCP tools"""
    
    def __init__(self, tool_registry: LocalToolRegistry):
        self.registry = tool_registry
        self.server = MCPServer(name="grpc_llm_container")
    
    def register_all_tools(self):
        """Convert all registered tools to MCP format"""
        for name, func in self.registry.tools.items():
            schema = self.registry.schemas[name]
            
            mcp_tool = MCPTool(
                name=name,
                description=schema["description"],
                inputSchema=schema["parameters"],
                execute=func
            )
            
            self.server.add_tool(mcp_tool)
    
    def start(self, port: int = 50056):
        """Start MCP server"""
        self.server.run(host="0.0.0.0", port=port)

# In agent_service.py
mcp_bridge = gRPCtoMCPBridge(tool_registry)
mcp_bridge.register_all_tools()
mcp_bridge.start(port=50056)
```

**Docker Compose Addition:**
```yaml
# docker-compose.yaml
services:
  # ... existing services ...
  
  mcp_bridge:
    build:
      context: .
      dockerfile: agent_service/Dockerfile
    container_name: mcp_bridge
    ports:
      - "50056:50056"
    command: python -m agent_service.mcp.server
    networks:
      - rag_net
```

## 5. **Telemetry & Observability (Grafana-Inspired)**

**Current Gap:** Metrics are collected but not exposed.

**Implementation:**
```python
# NEW: agent_service/telemetry/collector.py
import logging
from typing import Dict, Any
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass
class InferenceMetrics:
    timestamp: str
    agent_name: str
    query: str
    response_time_ms: float
    tokens_generated: int
    tools_used: List[str]
    success: bool
    error_message: str = None

class TelemetryCollector:
    """Grafana Agent-inspired telemetry"""
    
    def __init__(self, output_dir: str = "./telemetry"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Configure structured logging
        logging.basicConfig(
            filename=str(self.output_dir / "agent.log"),
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )
        self.logger = logging.getLogger("telemetry")
    
    def log_inference(self, metrics: InferenceMetrics):
        """Log inference event in JSON format"""
        self.logger.info(json.dumps(asdict(metrics)))
        
        # Write to metrics file for Grafana ingestion
        metrics_file = self.output_dir / "metrics.jsonl"
        with open(metrics_file, "a") as f:
            f.write(json.dumps(asdict(metrics)) + "\n")
    
    def before_inference(self, context: Dict[str, Any]):
        """Pre-inference callback"""
        self.logger.info(f"Query: {context['query'][:100]}...")
    
    def after_inference(self, response: Dict[str, Any]):
        """Post-inference callback"""
        self.logger.info(f"Response: {str(response)[:100]}...")

# Usage in agent
telemetry = TelemetryCollector()
agent = LocalAgent(
    name="my_agent",
    model_path="./models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
    instruction="Help the user",
    tools=[...],
    before_inference_callback=telemetry.before_inference,
    after_inference_callback=telemetry.after_inference
)
```

## 6. **iOS-Specific Optimizations**

### CoreML Model Conversion
```bash
# Convert GGUF to CoreML for Metal acceleration
python scripts/convert_gguf_to_coreml.py \
    --input llm_service/models/qwen2.5-0.5b-instruct-q5_k_m.gguf \
    --output ios/Models/qwen.mlmodel \
    --quantize int4
```

### Swift Agent Framework
```swift
// NEW: external/CppLLM/Sources/AgentKit/LocalAgent.swift
import Foundation
import CoreML

class LocalAgent {
    let name: String
    let model: MLModel
    let tools: [any AgentTool]
    
    init(name: String, modelPath: String, tools: [any AgentTool]) throws {
        self.name = name
        self.model = try MLModel(contentsOf: URL(fileURLWithPath: modelPath))
        self.tools = tools
    }
    
    func run(query: String) async throws -> AgentResponse {
        // Build prompt with tool descriptions
        let prompt = buildPrompt(query: query, tools: tools)
        
        // Local inference
        let input = ModelInput(prompt: prompt)
        let output = try model.prediction(from: input)
        
        // Parse response
        let parsed = try JSONDecoder().decode(AgentOutput.self, from: output.data)
        
        // Execute tools if needed
        if let functionCall = parsed.functionCall {
            return try await executeTool(functionCall)
        }
        
        return AgentResponse(content: parsed.content)
    }
}

// Example usage in iOS app
let calendarAgent = try LocalAgent(
    name: "calendar_agent",
    modelPath: Bundle.main.path(forResource: "qwen", ofType: "mlmodel")!,
    tools: [ScheduleMeetingTool(), GetDateTool()]
)

let response = try await calendarAgent.run(query: "Schedule a meeting with Alex tomorrow at 2pm")
```

## Implementation Roadmap

### Phase 1: Tool Modernization (Week 1-2)
- [ ] Create `LocalToolRegistry` with ADK-style function registration
- [ ] Refactor `tool_service` functions to return `Dict[str, Any]` with status keys
- [ ] Add docstring parser for automatic schema extraction
- [ ] Implement LangChain/CrewAI tool wrappers

### Phase 2: Agent Framework (Week 3-4)
- [ ] Build `LocalAgent` class with ADK-inspired API
- [ ] Implement Agent-as-Tool pattern
- [ ] Add telemetry callbacks system
- [ ] Create specialized agents (search, calendar, etc.)

### Phase 3: MCP Integration (Week 5-6)
- [ ] Implement MCP server bridge
- [ ] Expose all tools via MCP protocol
- [ ] Add MCP client for consuming external MCP tools
- [ ] Document MCP usage patterns

### Phase 4: iOS Optimization (Week 7-8)
- [ ] Convert GGUF models to CoreML
- [ ] Build Swift agent framework
- [ ] Implement on-device gRPC (no Docker)
- [ ] Add Siri Shortcuts integration

### Phase 5: Observability (Week 9-10)
- [ ] Implement structured telemetry
- [ ] Add Grafana dashboard configs
- [ ] Create metrics export pipeline
- [ ] Build performance monitoring

## Migration Strategy

### Backward Compatibility
Keep existing gRPC services running while adding new framework:

```python
# agent_service/agent_service.py - UPDATED
class AgentOrchestrator:
    def __init__(self):
        # OLD: Keep existing LangGraph workflow
        self.legacy_workflow = self._build_legacy_workflow()
        
        # NEW: Add ADK-style agent
        self.modern_agent = LocalAgent(
            name="orchestrator",
            model_path="./models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
            instruction="Route requests intelligently",
            tools=self._build_tool_registry()
        )
    
    async def process_query(self, query: str, use_modern: bool = False):
        """Support both architectures during migration"""
        if use_modern:
            return await self.modern_agent.run(query)
        else:
            return self.legacy_workflow.invoke({"messages": [HumanMessage(content=query)]})
```

## Testing Strategy

### Unit Tests
```python
# tests/test_tool_registry.py
def test_function_tool_registration():
    registry = LocalToolRegistry()
    
    def sample_tool(name: str, age: int) -> Dict[str, Any]:
        """A sample tool for testing.
        
        Args:
            name (str): Person's name
            age (int): Person's age
        
        Returns:
            A dict with status and data
        """
        return {"status": "success", "data": f"{name} is {age}"}
    
    registry.register_function(sample_tool)
    
    assert "sample_tool" in registry.tools
    assert registry.schemas["sample_tool"]["description"] == "A sample tool for testing."
    assert "name" in registry.schemas["sample_tool"]["parameters"]
```

### Integration Tests
```bash
# Run modern agent flow
conda run -n llm python -m testing_tool.modern_agent_flow
```

## Benefits of This Approach

1. **Zero Cloud Costs**: All inference local via llama.cpp
2. **ADK Compatibility**: Familiar API for developers coming from Google ecosystem
3. **MCP Interoperability**: Future-proof agent communication
4. **iOS Ready**: CoreML optimization for mobile deployment
5. **Incremental Migration**: Run old and new systems side-by-side
6. **Better DX**: Function tools are easier to write than gRPC services
7. **Observability**: Grafana-inspired telemetry for production monitoring

## Next Steps

1. Review this strategy with team
2. Prioritize phases based on iOS deployment timeline
3. Set up development branches for parallel work
4. Create proof-of-concept for Phase 1
5. Document API changes for external consumers
