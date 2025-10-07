# Testing Guide

## Testing Philosophy

**Core Principles**:
1. **Test at Multiple Levels**: Unit → Integration → E2E
2. **Mock External Dependencies**: Don't rely on real LLM/Chroma in tests
3. **Deterministic Tests**: No flaky tests due to LLM randomness
4. **Fast Feedback**: Unit tests < 1s, integration tests < 10s
5. **Realistic Scenarios**: Test actual user workflows

## Testing Pyramid

```
         ╱╲
        ╱  ╲       E2E Tests (5%)
       ╱────╲      - Full system with Docker
      ╱      ╲     - Expensive, slow, brittle
     ╱────────╲    
    ╱          ╲   Integration Tests (25%)
   ╱────────────╲  - Service interactions
  ╱              ╲ - Mock external services
 ╱────────────────╲
╱                  ╲ Unit Tests (70%)
────────────────────  - Individual functions
                      - Fast, isolated
```

## Test Setup

### Prerequisites

```bash
# Install test dependencies
cd testing_tool
pip install -r requirements-test.txt

# Contents of requirements-test.txt:
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-mock==3.12.0
grpcio-testing==1.60.0
```

### Directory Structure

```
testing_tool/
├── client.py              # Test client utilities
├── config.py              # Test configuration
├── mock_agent_flow.py     # Mock harness for local testing
├── requirements-test.txt
├── run_tests.sh           # Test runner script
└── tests/
    ├── test_unit.py           # Unit tests (individual tools)
    ├── test_integration.py    # Integration tests (service interactions)
    ├── test_e2e.py            # End-to-end tests (full workflows)
    ├── test_services_modular.py  # Modular service tests
    └── test_agent_mock_flow.py   # Mock flow tests
```

## Unit Tests

**Purpose**: Test individual functions in isolation

**Location**: `tests/test_unit.py`

### Example: Testing Tool Validation

```python
import pytest
from agent_service.agent_service import AgentOrchestrator

def test_schedule_meeting_validation():
    """Test input validation for schedule_meeting tool"""
    orchestrator = AgentOrchestrator()
    
    # Test missing participant
    result = orchestrator._schedule_meeting(
        participant="",
        start_time="2024-01-15T14:00:00",
        duration_minutes=30
    )
    assert result["success"] is False
    assert "participant" in result["error"].lower()
    
    # Test invalid duration
    result = orchestrator._schedule_meeting(
        participant="Alex",
        start_time="2024-01-15T14:00:00",
        duration_minutes=-10
    )
    assert result["success"] is False
    assert "duration" in result["error"].lower()
    
    # Test invalid date format
    result = orchestrator._schedule_meeting(
        participant="Alex",
        start_time="not-a-date",
        duration_minutes=30
    )
    assert result["success"] is False
    assert "time" in result["error"].lower()
```

### Example: Testing Response Parsing

```python
def test_llm_response_parsing():
    """Test parsing of LLM responses"""
    from agent_service.agent_service import ResponseValidator
    
    validator = ResponseValidator()
    
    # Test valid tool call
    response = '{"function_call": {"name": "search_web", "arguments": {"query": "AI news"}}}'
    result = validator.process_response(response, {})
    
    assert "pending_tool" in result
    assert result["pending_tool"]["name"] == "search_web"
    assert result["pending_tool"]["arguments"]["query"] == "AI news"
    
    # Test valid direct answer
    response = '{"content": "The answer is 42"}'
    result = validator.process_response(response, {})
    
    assert "messages" in result
    assert "The answer is 42" in result["messages"][0].content
    
    # Test malformed JSON
    response = '{"function_call": {incomplete'
    result = validator.process_response(response, {})
    
    assert "errors" in result
    assert "JSON" in result["errors"][0]
```

### Example: Testing Circuit Breaker

```python
def test_circuit_breaker_trips():
    """Test that circuit breaker trips after threshold"""
    from agent_service.agent_service import ToolRegistry, ToolConfig
    
    registry = ToolRegistry()
    
    # Register tool with threshold=3
    registry.register(
        "test_tool",
        lambda x: x,
        ToolConfig(description="Test", parameters={}, circuit_breaker_threshold=3)
    )
    
    # First 2 failures: tool still available
    registry.record_failure("test_tool")
    assert registry.get_tool("test_tool") is not None
    
    registry.record_failure("test_tool")
    assert registry.get_tool("test_tool") is not None
    
    # 3rd failure: circuit trips
    registry.record_failure("test_tool")
    assert registry.get_tool("test_tool") is None
    
    # Success resets
    registry.record_success("test_tool")
    assert registry.get_tool("test_tool") is not None
```

### Running Unit Tests

```bash
# Run all unit tests
pytest tests/test_unit.py -v

# Run specific test
pytest tests/test_unit.py::test_schedule_meeting_validation -v

# Run with coverage
pytest tests/test_unit.py --cov=agent_service --cov-report=html
```

## Integration Tests

**Purpose**: Test interactions between services

**Location**: `tests/test_integration.py`

### Example: Testing LLM Client Integration

```python
import pytest
import grpc
from llm_service import llm_pb2, llm_pb2_grpc

@pytest.fixture
def llm_client():
    """Fixture providing LLM client"""
    channel = grpc.insecure_channel('localhost:50051')
    yield llm_pb2_grpc.LLMServiceStub(channel)
    channel.close()

def test_llm_generate(llm_client):
    """Test LLM generation"""
    request = llm_pb2.GenerateRequest(
        prompt="What is 2+2?",
        max_tokens=50,
        temperature=0.0  # Deterministic
    )
    
    response_text = ""
    for chunk in llm_client.Generate(request):
        response_text += chunk.token
    
    assert len(response_text) > 0
    assert "4" in response_text.lower()

def test_llm_json_response(llm_client):
    """Test LLM with JSON format"""
    request = llm_pb2.GenerateRequest(
        prompt='Respond with JSON: {"result": "success"}',
        response_format="json"
    )
    
    response_text = ""
    for chunk in llm_client.Generate(request):
        response_text += chunk.token
    
    import json
    parsed = json.loads(response_text)
    assert "result" in parsed
```

### Example: Testing Agent-Tool Integration

```python
def test_agent_calls_tool(mock_tool_service):
    """Test that agent correctly calls tools"""
    from agent_service.agent_service import AgentOrchestrator
    
    orchestrator = AgentOrchestrator()
    orchestrator.tool_client = mock_tool_service
    
    # Simulate agent decision to search web
    state = {
        "messages": [],
        "pending_tool": {
            "name": "search_web",
            "arguments": {"query": "AI news", "max_results": 5}
        }
    }
    
    result = orchestrator.tool_executor.execute(state)
    
    # Verify tool was called
    assert mock_tool_service.calls["search_web"] == 1
    
    # Verify result structure
    assert "messages" in result
    assert isinstance(result["messages"][0], FunctionMessage)
    assert "context" in result
    assert result["context"][-1]["source"] == "search_web"
```

### Running Integration Tests

**Requires services running**:
```bash
# Start services
docker-compose up -d

# Wait for health checks
sleep 10

# Run integration tests
pytest tests/test_integration.py -v

# Cleanup
docker-compose down
```

## Mock Harness Testing

**Purpose**: Test agent orchestration without Docker

**Location**: `testing_tool/mock_agent_flow.py`

### Mock Client Architecture

```python
class _MockLLMClient:
    """Stateful mock that simulates LLM reasoning"""
    
    def __init__(self):
        self.call_count = 0
    
    def generate_stream(self, prompt: str):
        """
        First call: Return tool call
        Second call: Return final answer
        """
        self.call_count += 1
        
        if self.call_count == 1:
            # Simulate LLM deciding to use tool
            response = {
                "function_call": {
                    "name": "schedule_meeting",
                    "arguments": {
                        "participant": "Alex",
                        "start_time": "2024-01-15T14:00:00",
                        "duration_minutes": 30
                    }
                }
            }
            yield type('Response', (), {'token': json.dumps(response)})
        else:
            # Simulate LLM generating final answer
            response = {
                "content": "Meeting with Alex scheduled successfully"
            }
            yield type('Response', (), {'token': json.dumps(response)})

class _MockToolClient:
    """Mock tool service"""
    
    def call_tool(self, tool_name: str, params: dict):
        """Simulate tool execution"""
        if tool_name == "schedule_meeting":
            return type('Response', (), {
                'success': True,
                'result': json.dumps({
                    "message": "Meeting created",
                    "event_id": "mock_event_123"
                })
            })()
```

### Example: Testing Mock Flow

```python
# In tests/test_agent_mock_flow.py
import pytest
from testing_tool.mock_agent_flow import run_mock_flow

@pytest.mark.parametrize("query,expected_tool,expected_context", [
    ("Schedule meeting with Alex", "schedule_meeting", "Alex"),
    ("Search for AI news", "search_web", "AI"),
])
def test_mock_agent_flow(query, expected_tool, expected_context):
    """Test agent flow with mocks"""
    result = run_mock_flow(query)
    
    # Verify final answer
    assert result["final_answer"]
    assert len(result["final_answer"]) > 0
    
    # Verify tool was used
    assert expected_tool in result["tools_used"]
    
    # Verify context captured
    assert any(expected_context.lower() in str(c).lower() 
               for c in result["context"])
```

### Running Mock Tests

```bash
# No services needed!
pytest tests/test_agent_mock_flow.py -v

# Fast feedback loop for development
pytest tests/test_agent_mock_flow.py --tb=short
```

## End-to-End Tests

**Purpose**: Test complete workflows with real services

**Location**: `tests/test_e2e.py`

### Example: Full Scheduling Workflow

```python
import pytest
import grpc
from agent_service import agent_pb2, agent_pb2_grpc

@pytest.fixture(scope="module")
def agent_client():
    """Connect to agent service"""
    channel = grpc.insecure_channel('localhost:50054')
    yield agent_pb2_grpc.AgentServiceStub(channel)
    channel.close()

def test_schedule_meeting_e2e(agent_client):
    """Test complete scheduling workflow"""
    # Send query
    request = agent_pb2.AgentRequest(
        user_query="Schedule a meeting with Alex tomorrow at 2pm for 1 hour",
        debug_mode=True
    )
    
    response = agent_client.QueryAgent(request)
    
    # Verify response
    assert response.final_answer
    assert "alex" in response.final_answer.lower()
    assert "meeting" in response.final_answer.lower()
    
    # Verify tools used
    assert "schedule_meeting" in response.context_used
    
    # Verify calendar (requires EventKit mock or test calendar)
    # TODO: Query calendar to verify event exists
```

### Example: Multi-Turn Conversation

```python
def test_multi_turn_conversation(agent_client):
    """Test conversation with context preservation"""
    thread_id = "test_thread_123"
    
    # Turn 1
    response1 = agent_client.QueryAgent(agent_pb2.AgentRequest(
        user_query="What's the weather in Paris?",
        thread_id=thread_id
    ))
    assert "paris" in response1.final_answer.lower()
    
    # Turn 2 (with pronoun reference)
    response2 = agent_client.QueryAgent(agent_pb2.AgentRequest(
        user_query="What about the population there?",
        thread_id=thread_id
    ))
    # Should understand "there" = Paris from context
    assert "paris" in response2.final_answer.lower() or "million" in response2.final_answer.lower()
```

### Running E2E Tests

```bash
# Requires full stack
docker-compose up -d

# Run E2E tests
pytest tests/test_e2e.py -v -s

# With retry on failure (for flaky network issues)
pytest tests/test_e2e.py --maxfail=1 --reruns=3
```

## Modular Service Tests

**Purpose**: Test each service independently

**Location**: `tests/test_services_modular.py`

### Test Structure

```python
import pytest

class TestLLMService:
    """Tests for LLM service"""
    
    def test_generate_basic(self):
        # Test basic generation
        pass
    
    def test_generate_json_format(self):
        # Test JSON-constrained output
        pass
    
    def test_generate_streaming(self):
        # Test streaming responses
        pass

class TestChromaService:
    """Tests for Chroma service"""
    
    def test_add_document(self):
        # Test document ingestion
        pass
    
    def test_query_documents(self):
        # Test retrieval
        pass
    
    def test_query_with_filters(self):
        # Test filtered search
        pass

class TestToolService:
    """Tests for Tool service"""
    
    def test_web_search(self):
        # Test web search tool
        pass
    
    def test_math_solver(self):
        # Test math tool
        pass

class TestAgentService:
    """Tests for Agent service"""
    
    def test_agent_schedule_meeting_bridge(self):
        """Test agent can bridge to CppLLM for scheduling"""
        # Covered in existing tests
        pass
```

### Running Modular Tests

```bash
# Run all modular tests
pytest tests/test_services_modular.py -v

# Run only LLM tests
pytest tests/test_services_modular.py::TestLLMService -v

# Run specific test
pytest tests/test_services_modular.py::TestAgentService::test_agent_schedule_meeting_bridge -v
```

## Test Automation

### CI/CD Pipeline (GitHub Actions)

**File**: `.github/workflows/test.yml`

```yaml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r testing_tool/requirements-test.txt
      
      - name: Run unit tests
        run: |
          pytest testing_tool/tests/test_unit.py -v --cov=agent_service
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Start services
        run: |
          docker-compose up -d
          sleep 30  # Wait for services
      
      - name: Run integration tests
        run: |
          docker-compose exec -T agent_service pytest tests/test_integration.py -v
      
      - name: Cleanup
        run: docker-compose down

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      
      - name: Start full stack
        run: docker-compose up -d
      
      - name: Run E2E tests
        run: |
          pytest testing_tool/tests/test_e2e.py -v
      
      - name: Cleanup
        if: always()
        run: docker-compose down
```

### Local Test Script

**File**: `testing_tool/run_tests.sh`

```bash
#!/bin/bash
set -e

echo "Running test suite..."

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Unit tests (no services needed)
echo -e "${GREEN}[1/4] Running unit tests...${NC}"
pytest tests/test_unit.py -v
if [ $? -ne 0 ]; then
    echo -e "${RED}Unit tests failed!${NC}"
    exit 1
fi

# 2. Mock flow tests
echo -e "${GREEN}[2/4] Running mock flow tests...${NC}"
pytest tests/test_agent_mock_flow.py -v
if [ $? -ne 0 ]; then
    echo -e "${RED}Mock flow tests failed!${NC}"
    exit 1
fi

# 3. Start services for integration tests
echo -e "${GREEN}[3/4] Starting services for integration tests...${NC}"
docker-compose up -d
sleep 20

# 4. Integration tests
echo -e "${GREEN}Running integration tests...${NC}"
pytest tests/test_integration.py -v
INTEGRATION_RESULT=$?

# 5. Modular service tests
echo -e "${GREEN}Running modular service tests...${NC}"
pytest tests/test_services_modular.py -v
MODULAR_RESULT=$?

# 6. E2E tests (optional, commented out by default)
# echo -e "${GREEN}[4/4] Running E2E tests...${NC}"
# pytest tests/test_e2e.py -v
# E2E_RESULT=$?

# Cleanup
echo -e "${GREEN}Cleaning up...${NC}"
docker-compose down

# Report results
if [ $INTEGRATION_RESULT -eq 0 ] && [ $MODULAR_RESULT -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
```

**Run**:
```bash
cd testing_tool
chmod +x run_tests.sh
./run_tests.sh
```

## Debugging Tests

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
pytest tests/test_integration.py -v -s
```

### Capture Output

```bash
# Show print statements
pytest tests/test_unit.py -v -s

# Capture logs to file
pytest tests/test_unit.py -v --log-file=test.log
```

### Isolate Failing Tests

```bash
# Run only failed tests from last run
pytest --lf

# Run until first failure
pytest -x

# Drop into debugger on failure
pytest --pdb
```

### Inspect Mock Calls

```python
from unittest.mock import Mock

mock_client = Mock()
# ... use in test ...

# Inspect calls
print(mock_client.call_count)
print(mock_client.call_args_list)
mock_client.assert_called_once_with(expected_arg)
```

## Performance Testing

### Load Testing Agent

**Using Locust**:
```python
# In tests/locustfile.py
from locust import HttpUser, task, between
import json

class AgentUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def query_agent(self):
        self.client.post("/agent/query", json={
            "query": "What is the weather today?",
            "user_id": f"user_{self.user_id}"
        })

# Run:
# locust -f tests/locustfile.py --host=http://localhost:8080
```

**Metrics to Track**:
- Requests per second
- p50, p95, p99 latency
- Error rate
- Circuit breaker trips

## Coverage Goals

**Targets**:
- Unit tests: > 80% coverage
- Integration tests: Critical paths covered
- E2E tests: Main user workflows covered

**Generate Coverage Report**:
```bash
pytest tests/ --cov=agent_service --cov=llm_service --cov=chroma_service --cov-report=html

# Open report
open htmlcov/index.html
```

## Best Practices

1. **Keep Tests Isolated**: Each test should be independent
2. **Use Fixtures**: Reuse setup code with pytest fixtures
3. **Descriptive Names**: `test_schedule_meeting_fails_with_invalid_date` vs `test_1`
4. **Test Error Cases**: Don't just test happy path
5. **Mock External Services**: Use mocks for LLM, APIs, databases
6. **Fast Tests**: Unit tests should complete in milliseconds
7. **Cleanup**: Always teardown resources after tests
8. **Deterministic**: Avoid random values, use seeds or fixed inputs
9. **Document Flaky Tests**: If a test is occasionally flaky, document why
10. **Continuous Integration**: Run tests on every commit

## Troubleshooting Common Issues

### Issue: "Connection Refused" in Integration Tests

**Cause**: Services not fully started

**Solution**:
```bash
# Increase wait time
docker-compose up -d
sleep 30  # Instead of 10

# Or check health
docker-compose ps
```

### Issue: Mock Tests Pass, Integration Tests Fail

**Cause**: Mocks don't match real service behavior

**Solution**: Update mocks to reflect actual responses

### Issue: Flaky E2E Tests

**Causes**:
- Network latency
- LLM non-determinism
- Race conditions

**Solutions**:
- Add retries for network calls
- Use `temperature=0` for deterministic LLM
- Add explicit waits/polling

### Issue: Slow Test Suite

**Causes**:
- Too many E2E tests
- Services not properly cleaned up

**Solutions**:
- Move more tests to unit/mock level
- Parallelize tests: `pytest -n 4`
- Use faster test database (in-memory SQLite)

## Next Steps

Now that you have comprehensive testing coverage:
1. Run tests before every commit
2. Add tests for new features
3. Maintain >80% coverage
4. Monitor CI/CD pipeline
5. Fix flaky tests immediately

For more details on specific services, refer to:
- [01_ARCHITECTURE.md](./01_ARCHITECTURE.md) - System design
- [02_AGENT_SERVICE.md](./02_AGENT_SERVICE.md) - Agent implementation
- [03_APPLE_INTEGRATION.md](./03_APPLE_INTEGRATION.md) - Native integration
- [04_N8N_INTEGRATION.md](./04_N8N_INTEGRATION.md) - Workflow automation
