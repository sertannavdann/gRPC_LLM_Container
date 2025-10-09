# Refactoring Plan: ADK-Style Architecture

## Branch Strategy
- **Branch**: `demo` (current pivot branch)
- **Approach**: Incremental refactoring with backward compatibility
- **Testing**: Each stage must pass tests before proceeding

## Stage Overview

```
Stage 1: Foundation (Tool Registry)      → 2-3 days
Stage 2: Function Tools                  → 2-3 days  
Stage 3: Agent Refactor                  → 3-4 days
Stage 4: Integration & Cleanup           → 2-3 days
Stage 5: LangChain/CrewAI Support        → 2-3 days
```

---

## Stage 1: Foundation - Modern Tool Registry

### Objective
Create ADK-style tool registry that coexists with current gRPC stubs.

### Changes
1. **New**: `agent_service/tools/__init__.py`
2. **New**: `agent_service/tools/registry.py` - LocalToolRegistry class
3. **New**: `agent_service/tools/base.py` - Base tool classes
4. **Update**: `agent_service/agent_service.py` - Add modern_registry alongside legacy

### Files to Create

#### `agent_service/tools/__init__.py`
```python
from .registry import LocalToolRegistry
from .base import ToolResult, ToolError

__all__ = ['LocalToolRegistry', 'ToolResult', 'ToolError']
```

#### `agent_service/tools/base.py`
```python
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class ToolResult:
    """Standard tool result format"""
    status: str  # "success" | "error"
    data: Any = None
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        return result

class ToolError(Exception):
    """Tool execution error"""
    pass
```

#### `agent_service/tools/registry.py`
```python
import inspect
import json
from typing import Dict, Any, Callable, Optional
from .base import ToolResult, ToolError

class LocalToolRegistry:
    """ADK-style tool registry with automatic schema extraction"""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, Dict] = {}
        self.circuit_breakers: Dict[str, int] = {}
        self.max_failures = 3
    
    def register_function(self, func: Callable) -> None:
        """Register a Python function as a tool"""
        name = func.__name__
        schema = self._extract_schema(func)
        
        self.tools[name] = func
        self.schemas[name] = schema
        self.circuit_breakers[name] = 0
        
    def call_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool and return standardized result"""
        if name not in self.tools:
            return {"status": "error", "message": f"Tool '{name}' not found"}
        
        if self.circuit_breakers.get(name, 0) >= self.max_failures:
            return {"status": "error", "message": f"Circuit breaker open for '{name}'"}
        
        try:
            result = self.tools[name](**kwargs)
            
            # Ensure result is dict with status
            if isinstance(result, dict) and "status" in result:
                self.circuit_breakers[name] = 0  # Reset on success
                return result
            else:
                # Wrap non-standard results
                return {"status": "success", "data": result}
                
        except Exception as e:
            self.circuit_breakers[name] += 1
            return {
                "status": "error",
                "message": str(e),
                "tool": name
            }
    
    def _extract_schema(self, func: Callable) -> Dict[str, Any]:
        """Extract schema from function signature and docstring"""
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""
        
        schema = {
            "name": func.__name__,
            "description": self._extract_description(doc),
            "parameters": {},
            "required": []
        }
        
        for param_name, param in sig.parameters.items():
            param_type = self._python_type_to_json_type(param.annotation)
            schema["parameters"][param_name] = {
                "type": param_type,
                "description": self._extract_param_description(doc, param_name)
            }
            
            if param.default == inspect.Parameter.empty:
                schema["required"].append(param_name)
        
        return schema
    
    def _extract_description(self, docstring: str) -> str:
        """Extract main description from docstring"""
        lines = docstring.split('\n')
        description = []
        for line in lines:
            line = line.strip()
            if line.startswith('Args:') or line.startswith('Returns:'):
                break
            if line:
                description.append(line)
        return ' '.join(description)
    
    def _extract_param_description(self, docstring: str, param_name: str) -> str:
        """Extract parameter description from Args section"""
        in_args = False
        for line in docstring.split('\n'):
            line = line.strip()
            if 'Args:' in line:
                in_args = True
                continue
            if in_args:
                if 'Returns:' in line or 'Raises:' in line:
                    break
                if param_name in line and ':' in line:
                    return line.split(':', 1)[1].strip()
        return ""
    
    def _python_type_to_json_type(self, python_type) -> str:
        """Convert Python type hints to JSON schema types"""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        return type_map.get(python_type, "string")
    
    def get_available_tools(self) -> list[str]:
        """Get list of non-circuit-broken tools"""
        return [
            name for name, failures in self.circuit_breakers.items()
            if failures < self.max_failures
        ]
    
    def reset_circuit_breaker(self, tool_name: str):
        """Reset circuit breaker for a tool"""
        if tool_name in self.circuit_breakers:
            self.circuit_breakers[tool_name] = 0
```

### Testing
```bash
# New test file
tests/unit/test_tool_registry.py
```

### Success Criteria
- [ ] LocalToolRegistry created and importable
- [ ] Schema extraction works for simple functions
- [ ] Circuit breaker logic functional
- [ ] Unit tests pass (>90% coverage)

---

## Stage 2: Function Tools - Convert Existing Tools

### Objective
Convert gRPC-wrapped tools to direct Python functions.

### Changes
1. **New**: `agent_service/tools/web.py` - web_search function
2. **New**: `agent_service/tools/math.py` - solve_math function
3. **New**: `agent_service/tools/calendar.py` - get_date, schedule_meeting
4. **Update**: `agent_service/agent_service.py` - Register modern tools

### Files to Create

#### `agent_service/tools/web.py`
```python
from typing import Dict, Any
import os
from shared.clients.tool_client import ToolClient

def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web using Google Serper API.
    
    Args:
        query (str): The search query
        max_results (int): Maximum number of results to return
    
    Returns:
        Dict with search results: {"status": "success", "results": [...]}
        or error: {"status": "error", "message": "..."}
    """
    try:
        # Wrap existing gRPC call
        client = ToolClient()
        response = client.call_tool(
            tool_name="web_search",
            params={"query": query, "max_results": str(max_results)}
        )
        
        if response and hasattr(response, 'success') and response.success:
            # Parse JSON data from response
            import json
            results = json.loads(response.data) if hasattr(response, 'data') else []
            return {
                "status": "success",
                "results": results,
                "count": len(results)
            }
        else:
            return {
                "status": "error",
                "message": getattr(response, 'message', 'Unknown error')
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Web search failed: {str(e)}"
        }
```

#### `agent_service/tools/math.py`
```python
from typing import Dict, Any
from sympy import sympify

def solve_math(expression: str) -> Dict[str, Any]:
    """
    Solve a mathematical expression.
    
    Args:
        expression (str): Mathematical expression (e.g., "2+2", "sqrt(16)")
    
    Returns:
        Dict with result: {"status": "success", "result": "4", "expression": "2+2"}
        or error: {"status": "error", "message": "..."}
    """
    try:
        result = sympify(expression)
        return {
            "status": "success",
            "result": str(float(result)),
            "expression": expression
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Cannot solve: {str(e)}"
        }
```

#### `agent_service/tools/calendar.py`
```python
from typing import Dict, Any
from datetime import datetime, timedelta

def get_date(x_days_from_today: int) -> Dict[str, str]:
    """
    Get a date relative to today.
    
    Args:
        x_days_from_today (int): Number of days from today (0 for today)
    
    Returns:
        Dict with formatted date: {"status": "success", "date": "Monday, January 1, 2025"}
    """
    try:
        target_date = datetime.today() + timedelta(days=x_days_from_today)
        date_string = target_date.strftime("%A, %B %d, %Y")
        return {
            "status": "success",
            "date": date_string
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def schedule_meeting(
    person: str,
    start_time_iso8601: str,
    duration_minutes: int
) -> Dict[str, Any]:
    """
    Schedule a meeting using native calendar integration.
    
    Args:
        person (str): Person's full name
        start_time_iso8601 (str): Start time in ISO 8601 format
        duration_minutes (int): Meeting duration in minutes
    
    Returns:
        Dict with event details: {"status": "success", "event_id": "...", "message": "..."}
        or error: {"status": "error", "message": "..."}
    """
    try:
        from shared.clients.cpp_llm_client import CppLLMClient
        
        client = CppLLMClient(host="localhost", port=50055)
        # Note: Adjust based on actual CppLLMClient API
        result = client.trigger_schedule_meeting(
            person=person,
            start_time_iso8601=start_time_iso8601,
            duration_minutes=duration_minutes
        )
        
        return {
            "status": "success",
            "event_id": result.get("event_id", "unknown"),
            "message": f"Meeting with {person} scheduled"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to schedule: {str(e)}"
        }
```

### Update Agent Service

#### `agent_service/agent_service.py` (partial update)
```python
# Add imports at top
from agent_service.tools.registry import LocalToolRegistry
from agent_service.tools import web, math, calendar

# In AgentOrchestrator.__init__:
def __init__(self):
    # ... existing code ...
    
    # NEW: Modern tool registry (coexists with legacy)
    self.modern_registry = LocalToolRegistry()
    self._register_modern_tools()
    
    # Keep legacy for backward compatibility
    self.legacy_registry = ToolRegistry()
    # ... existing legacy setup ...

def _register_modern_tools(self):
    """Register ADK-style function tools"""
    self.modern_registry.register_function(web.web_search)
    self.modern_registry.register_function(math.solve_math)
    self.modern_registry.register_function(calendar.get_date)
    self.modern_registry.register_function(calendar.schedule_meeting)
    
    logger.info(f"Registered {len(self.modern_registry.tools)} modern tools")
```

### Testing
```bash
# New test files
tests/unit/test_web_tools.py
tests/unit/test_math_tools.py
tests/unit/test_calendar_tools.py
tests/integration/test_modern_tools.py
```

### Success Criteria
- [ ] All 4 functions created and documented
- [ ] Functions return Dict with "status" key
- [ ] Functions registered in modern_registry
- [ ] Unit tests for each function pass
- [ ] Integration test calling through registry passes

---

## Stage 3: Agent Refactor - Dual Mode Operation

### Objective
Refactor AgentOrchestrator to support both legacy and modern tool execution.

### Changes
1. **Update**: `agent_service/agent_service.py` - Add modern execution path
2. **New**: `agent_service/agents/__init__.py`
3. **New**: `agent_service/agents/executor.py` - Modern tool executor

### Implementation

#### `agent_service/agents/executor.py`
```python
from typing import Dict, Any
import json
import logging
from agent_service.tools.registry import LocalToolRegistry

logger = logging.getLogger(__name__)

class ModernToolExecutor:
    """Execute tools using modern registry"""
    
    def __init__(self, registry: LocalToolRegistry):
        self.registry = registry
    
    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return result"""
        logger.info(f"Executing modern tool: {tool_name} with args: {arguments}")
        
        try:
            result = self.registry.call_tool(tool_name, **arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "tool": tool_name
            }
    
    def get_tool_descriptions(self) -> str:
        """Generate tool descriptions for LLM prompt"""
        descriptions = []
        for name, schema in self.registry.schemas.items():
            if self.registry.circuit_breakers.get(name, 0) < self.registry.max_failures:
                desc = f"- {name}: {schema['description']}"
                if schema.get('parameters'):
                    params = ', '.join(schema['parameters'].keys())
                    desc += f" (params: {params})"
                descriptions.append(desc)
        return '\n'.join(descriptions)
```

#### Update `agent_service/agent_service.py`
```python
from agent_service.agents.executor import ModernToolExecutor

class AgentOrchestrator:
    def __init__(self):
        # ... existing code ...
        
        # NEW: Modern infrastructure
        self.modern_registry = LocalToolRegistry()
        self._register_modern_tools()
        self.modern_executor = ModernToolExecutor(self.modern_registry)
        
        # Mode flag for testing
        self.use_modern_tools = os.getenv("USE_MODERN_TOOLS", "false").lower() == "true"
    
    def ProcessQuery(self, request, context):
        """gRPC endpoint - support both modes"""
        query = request.query
        thread_id = request.thread_id or str(uuid.uuid4())
        
        logger.info(f"Processing query (modern={self.use_modern_tools}): {query[:100]}")
        
        if self.use_modern_tools:
            return self._process_query_modern(query, thread_id, context)
        else:
            return self._process_query_legacy(query, thread_id, context)
    
    def _process_query_modern(self, query: str, thread_id: str, context):
        """Process using modern tool registry"""
        try:
            # Build prompt with modern tool descriptions
            tool_descriptions = self.modern_executor.get_tool_descriptions()
            
            prompt = f"""You are a helpful assistant with access to these tools:
{tool_descriptions}

User query: {query}

If you need a tool, respond with JSON: {{"function_call": {{"name": "tool_name", "arguments": {{...}}}}}}
Otherwise respond with JSON: {{"content": "your answer"}}
"""
            
            # Call LLM
            llm_response = self.llm_client.generate(prompt, max_tokens=512, temperature=0.2)
            
            # Parse response
            try:
                parsed = json.loads(llm_response)
            except json.JSONDecodeError:
                parsed = {"content": llm_response}
            
            # Execute tool if requested
            if "function_call" in parsed:
                func_call = parsed["function_call"]
                tool_result = self.modern_executor.execute(
                    func_call["name"],
                    func_call.get("arguments", {})
                )
                
                # Generate final response with tool result
                final_prompt = f"""Tool {func_call['name']} returned: {json.dumps(tool_result)}

Original query: {query}

Provide a natural language response to the user based on this result."""
                
                final_response = self.llm_client.generate(final_prompt, max_tokens=256)
                
                return agent_pb2.QueryResponse(
                    response=final_response,
                    thread_id=thread_id,
                    sources=agent_pb2.Sources(
                        tools_used=[func_call["name"]],
                        context_used=[]
                    )
                )
            else:
                return agent_pb2.QueryResponse(
                    response=parsed.get("content", ""),
                    thread_id=thread_id
                )
                
        except Exception as e:
            logger.error(f"Modern query processing failed: {e}", exc_info=True)
            context.abort(grpc.StatusCode.INTERNAL, str(e))
    
    def _process_query_legacy(self, query: str, thread_id: str, context):
        """Existing legacy implementation"""
        # ... keep existing code ...
        pass
```

### Testing
```bash
# New test file
tests/integration/test_dual_mode.py
```

Test cases:
1. Legacy mode still works
2. Modern mode with no tools works
3. Modern mode with tool call works
4. Circuit breaker in modern mode
5. Mode switching via env var

### Success Criteria
- [ ] Both legacy and modern modes work
- [ ] Environment variable controls mode
- [ ] Modern mode calls tools correctly
- [ ] LLM generates proper function_call JSON
- [ ] Integration tests pass for both modes

---

## Stage 4: Integration & Cleanup

### Objective
Connect everything, add comprehensive tests, document changes.

### Changes
1. **New**: `tests/integration/test_end_to_end_modern.py`
2. **Update**: `README.md` - Add modern usage examples
3. **New**: `docs/09_REFACTORING_GUIDE.md`
4. **Update**: `docker-compose.yaml` - Add USE_MODERN_TOOLS env var

### Testing Suite
```python
# tests/integration/test_end_to_end_modern.py
import pytest
import os

def test_web_search_modern():
    """Test web search in modern mode"""
    os.environ["USE_MODERN_TOOLS"] = "true"
    # ... test implementation ...

def test_math_solver_modern():
    """Test math solver in modern mode"""
    os.environ["USE_MODERN_TOOLS"] = "true"
    # ... test implementation ...

def test_circuit_breaker_modern():
    """Test circuit breaker triggers correctly"""
    # ... test implementation ...

def test_mode_switching():
    """Test switching between legacy and modern"""
    # ... test implementation ...
```

### Docker Compose Update
```yaml
agent_service:
  environment:
    - USE_MODERN_TOOLS=true  # Toggle modern tools
```

### Success Criteria
- [ ] All end-to-end tests pass
- [ ] Documentation updated
- [ ] Docker deployment tested
- [ ] Performance benchmarks show no regression

---

## Stage 5: LangChain/CrewAI Support (Future)

### Objective
Add wrappers for external tool ecosystems.

### Changes (Future PR)
1. **New**: `agent_service/tools/wrappers/langchain.py`
2. **New**: `agent_service/tools/wrappers/crewai.py`
3. **Example**: Using WikipediaQueryRun from LangChain

---

## Testing Strategy Per Stage

### Stage 1
```bash
pytest tests/unit/test_tool_registry.py -v
pytest tests/unit/test_tool_base.py -v
```

### Stage 2
```bash
pytest tests/unit/test_*_tools.py -v
pytest tests/integration/test_modern_tools.py -v
```

### Stage 3
```bash
pytest tests/integration/test_dual_mode.py -v
USE_MODERN_TOOLS=true pytest tests/integration/ -v
```

### Stage 4
```bash
pytest tests/ -v  # All tests
make test  # If make target exists
```

---

## Rollback Plan

Each stage is backward compatible:
- Stage 1: Only adds new files, doesn't modify existing behavior
- Stage 2: Tools coexist with legacy, not replacing
- Stage 3: Mode flag controls which path executes
- Stage 4: Legacy mode still works if modern fails

To rollback:
```bash
git checkout main -- agent_service/agent_service.py  # Restore original
rm -rf agent_service/tools/  # Remove new tools
```

---

## Success Metrics

- **Code Coverage**: >85% for new code
- **Performance**: <10% regression in response time
- **Compatibility**: All existing tests still pass
- **Documentation**: Each stage documented
- **Team Velocity**: Can add new tool in <15 minutes

---

## Timeline

- **Week 1**: Stages 1-2 (Foundation + Function Tools)
- **Week 2**: Stage 3 (Agent Refactor)
- **Week 3**: Stage 4 (Integration) + Buffer
- **Week 4**: Stage 5 (Optional enhancements)

---

## Next Immediate Steps

1. Review this plan with team
2. Set up `demo` branch protection (require tests to pass)
3. Start Stage 1: Create `agent_service/tools/` directory
4. Implement `LocalToolRegistry` with tests
5. Daily standups to track progress

**Ready to start Stage 1? Let's begin! 🚀**
