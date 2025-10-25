"""
Shared pytest fixtures for gRPC LLM Container tests.

Provides fixtures for:
- Mock LLM responses
- Temporary checkpoint database
- gRPC channel setup
- Docker container orchestration
- Logging capture
"""

import os
import sys
import pytest
import tempfile
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Iterator
from unittest.mock import Mock, MagicMock
import grpc
# Note: grpc_testing is optional, only needed for advanced gRPC mocking
# from grpc_testing import server_from_dictionary, strict_real_time

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import core modules
from core.state import AgentState, WorkflowConfig, ModelConfig, create_initial_state
from core.checkpointing import CheckpointManager
from tools.registry import LocalToolRegistry
from langchain_core.messages import HumanMessage, AIMessage


# ============================================================================
# Logging Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def configure_test_logging(caplog):
    """Configure logging for all tests."""
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def captured_logs(caplog):
    """
    Capture logs during test execution.
    
    Usage:
        def test_something(captured_logs):
            # Do something that logs
            assert "Expected log message" in captured_logs.text
    """
    caplog.set_level(logging.DEBUG)
    yield caplog
    

# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_workflow_config() -> WorkflowConfig:
    """Create test workflow configuration."""
    return WorkflowConfig(
        max_iterations=3,
        temperature=0.0,  # Deterministic for testing
        enable_streaming=False,
        context_window=2,
        max_tool_calls_per_turn=2,
        timeout_seconds=10  # Min value is 10
    )


@pytest.fixture
def test_model_config() -> ModelConfig:
    """Create test model configuration."""
    return ModelConfig(
        model_path="test_model.gguf",
        n_ctx=1024,
        n_threads=1,
        n_gpu_layers=0,
        use_mlock=False
    )


@pytest.fixture
def test_agent_state() -> AgentState:
    """Create initial agent state for testing."""
    return create_initial_state(
        conversation_id="test-conv-123",
        user_id="test-user",
        metadata={"test": True}
    )


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture
def temp_checkpoint_db() -> Iterator[str]:
    """
    Create temporary SQLite database for checkpointing.
    
    Yields:
        Path to temporary database file
    """
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    
    # Initialize database
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    
    yield db_path
    
    # Cleanup
    try:
        os.unlink(db_path)
        # Remove WAL files if they exist
        for suffix in ["-wal", "-shm"]:
            wal_file = db_path + suffix
            if os.path.exists(wal_file):
                os.unlink(wal_file)
    except Exception as e:
        print(f"Warning: Failed to clean up temp database: {e}")


@pytest.fixture
def checkpoint_manager(temp_checkpoint_db: str):
    """Create CheckpointManager with temporary database and checkpointer."""
    manager = CheckpointManager(db_path=temp_checkpoint_db)
    # Create checkpointer to initialize tables
    checkpointer = manager.create_checkpointer()
    return manager, checkpointer


# ============================================================================
# Mock LLM Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_simple_response() -> Dict[str, Any]:
    """Mock LLM response with simple content."""
    return {
        "content": "This is a test response from the LLM.",
        "model": "test-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 15}
    }


@pytest.fixture
def mock_llm_tool_call_response() -> Dict[str, Any]:
    """Mock LLM response requesting tool call."""
    return {
        "content": "",
        "function_call": {
            "name": "web_search",
            "arguments": {"query": "test query", "num_results": 5}
        },
        "model": "test-model"
    }


@pytest.fixture
def mock_llm_math_tool_response() -> Dict[str, Any]:
    """Mock LLM response for math tool call."""
    return {
        "content": "",
        "function_call": {
            "name": "math_solver",
            "arguments": {"expression": "2 + 2 * 3"}
        },
        "model": "test-model"
    }


@pytest.fixture
def mock_llm_client():
    """
    Mock LLM client for testing.
    
    Usage:
        def test_something(mock_llm_client):
            mock_llm_client.generate.return_value = {"content": "test"}
            result = agent.query("test")
    """
    client = Mock()
    client.generate = Mock(return_value={"content": "Mock LLM response"})
    client.stream = Mock(return_value=iter([{"delta": "Mock"}, {"delta": " response"}]))
    client.is_healthy = Mock(return_value=True)
    return client


# ============================================================================
# Tool Registry Fixtures
# ============================================================================

@pytest.fixture
def empty_tool_registry() -> LocalToolRegistry:
    """Create empty tool registry for testing."""
    return LocalToolRegistry()


@pytest.fixture
def mock_tool_success():
    """Mock tool that always succeeds."""
    def _tool(query: str) -> Dict[str, Any]:
        """
        Mock tool for testing.
        
        Args:
            query (str): Test query
        
        Returns:
            Success result
        """
        return {
            "status": "success",
            "data": f"Processed: {query}",
            "query": query
        }
    return _tool


@pytest.fixture
def mock_tool_failure():
    """Mock tool that always fails."""
    def _tool(query: str) -> Dict[str, Any]:
        """
        Mock tool that fails.
        
        Args:
            query (str): Test query
        
        Returns:
            Error result
        """
        raise ValueError("Simulated tool failure")
    return _tool


@pytest.fixture
def populated_tool_registry(
    empty_tool_registry: LocalToolRegistry,
    mock_tool_success
) -> LocalToolRegistry:
    """Create tool registry with mock tools."""
    registry = empty_tool_registry
    
    # Register mock tools
    registry.register(mock_tool_success)
    
    # Register additional mock tools
    @registry.register
    def calculator(expression: str) -> Dict[str, Any]:
        """
        Mock calculator tool.
        
        Args:
            expression (str): Math expression
        
        Returns:
            Calculation result
        """
        return {
            "status": "success",
            "result": 42,
            "expression": expression
        }
    
    return registry


# ============================================================================
# gRPC Fixtures
# ============================================================================

@pytest.fixture
def grpc_channel():
    """
    Create mock gRPC channel for testing.
    
    Usage:
        def test_grpc_call(grpc_channel):
            stub = MyServiceStub(grpc_channel)
            response = stub.MyMethod(request)
    """
    channel = grpc.insecure_channel('localhost:50051')
    yield channel
    channel.close()


@pytest.fixture
def grpc_test_server():
    """
    Create gRPC test server for unit testing.
    
    Returns a server that can be used with grpc_testing module.
    """
    # This will be implemented when we create gRPC tests
    # For now, return a mock
    return Mock()


# ============================================================================
# Docker Fixtures (for integration tests)
# ============================================================================

@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    """Path to docker-compose.yaml."""
    return str(PROJECT_ROOT / "docker-compose.yaml")


@pytest.fixture(scope="session")
def docker_services_up():
    """
    Start Docker services for integration tests.
    
    This is a session-scoped fixture that starts services once
    and keeps them running for all integration tests.
    
    Note: Requires docker-compose to be installed.
    """
    import subprocess
    import time
    
    # Check if we should run integration tests
    if os.getenv("SKIP_INTEGRATION_TESTS"):
        pytest.skip("Integration tests disabled")
    
    try:
        # Start services
        subprocess.run(
            ["docker-compose", "up", "-d"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True
        )
        
        # Wait for services to be ready
        time.sleep(5)
        
        yield
        
        # Cleanup
        subprocess.run(
            ["docker-compose", "down"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        pytest.skip(f"Failed to start Docker services: {e}")


# ============================================================================
# File System Fixtures
# ============================================================================

@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_env_file(temp_dir: Path) -> Path:
    """
    Create temporary .env file for testing.
    
    Returns:
        Path to test .env file
    """
    env_file = temp_dir / ".env"
    env_content = """
# Test environment variables
AGENT_MAX_ITERATIONS=3
AGENT_TEMPERATURE=0.0
AGENT_ENABLE_STREAMING=false
AGENT_CONTEXT_WINDOW=2

LLM_MODEL_PATH=test_model.gguf
LLM_N_CTX=1024
LLM_N_THREADS=1

SERPER_API_KEY=test_serper_key
"""
    env_file.write_text(env_content.strip())
    return env_file


# ============================================================================
# Mock HTTP Fixtures (for web tools)
# ============================================================================

@pytest.fixture
def mock_requests_get(monkeypatch):
    """
    Mock requests.get for testing web tools.
    
    Usage:
        def test_web_tool(mock_requests_get):
            mock_requests_get.return_value.text = "<html>Test</html>"
            result = load_web_page("http://example.com")
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "<html><title>Test</title><body>Test content</body></html>"
    mock_response.raise_for_status = Mock()
    
    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr("requests.get", mock_get)
    
    return mock_get


@pytest.fixture
def mock_serper_api(monkeypatch):
    """
    Mock Serper API for web_search tests.
    
    Returns mock requests.post that simulates Serper API responses.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={
        "organic": [
            {
                "title": "Test Result 1",
                "link": "https://example.com/1",
                "snippet": "Test snippet 1"
            },
            {
                "title": "Test Result 2",
                "link": "https://example.com/2",
                "snippet": "Test snippet 2"
            }
        ],
        "answerBox": {
            "answer": "42",
            "title": "The Answer"
        }
    })
    mock_response.raise_for_status = Mock()
    
    mock_post = Mock(return_value=mock_response)
    monkeypatch.setattr("requests.post", mock_post)
    
    return mock_post


# ============================================================================
# Utility Functions
# ============================================================================

def create_test_message_history() -> list:
    """Create sample message history for testing."""
    return [
        HumanMessage(content="What is 2+2?"),
        AIMessage(content="Let me calculate that."),
        HumanMessage(content="Thanks!")
    ]


@pytest.fixture
def sample_message_history():
    """Fixture providing sample message history."""
    return create_test_message_history()
