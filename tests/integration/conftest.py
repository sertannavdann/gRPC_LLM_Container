"""
pytest configuration for integration tests.

Sets up logging, markers, and common fixtures.
"""

import pytest
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def pytest_configure(config):
    """
    Configure pytest markers and logging.
    
    Registers custom markers:
        - integration: Integration tests requiring Docker
        - e2e: End-to-end tests with full stack
        - slow: Tests that take > 5 seconds
    """
    # Register markers
    config.addinivalue_line(
        "markers",
        "integration: Integration tests requiring Docker services"
    )
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests with full service stack"
    )
    config.addinivalue_line(
        "markers",
        "slow: Tests that take longer than 5 seconds"
    )
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # Set specific loggers
    logging.getLogger("docker_manager").setLevel(logging.INFO)
    logging.getLogger("grpc_test_client").setLevel(logging.INFO)
    logging.getLogger("grpc").setLevel(logging.WARNING)


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """
    Setup test environment.
    
    Validates that required tools are available.
    Assumes Docker services are already running (started via make up).
    Logs diagnostic information about model, memory, and container state.
    """
    import subprocess
    import socket
    
    # Try common Docker paths
    docker_paths = [
        "docker",
        "/usr/local/bin/docker",
        "/Applications/Docker.app/Contents/Resources/bin/docker",
    ]
    
    docker_cmd = None
    for path in docker_paths:
        try:
            result = subprocess.run(
                [path, "--version"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            docker_cmd = path
            logging.info(f"✓ Found Docker: {result.stdout.decode().strip()}")
            break
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    if not docker_cmd:
        pytest.skip("Docker not found in PATH. Please ensure Docker is installed and services are running via 'make up'.")

    # ── Diagnostic: container status ──
    try:
        ps_result = subprocess.run(
            [docker_cmd, "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, timeout=10,
        )
        logging.info("── Docker containers ──\n%s", ps_result.stdout.decode().strip())
    except Exception:
        pass

    # ── Diagnostic: memory usage ──
    try:
        stats_result = subprocess.run(
            [docker_cmd, "stats", "--no-stream", "--format",
             "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"],
            capture_output=True, timeout=15,
        )
        logging.info("── Docker memory ──\n%s", stats_result.stdout.decode().strip())
    except Exception:
        pass

    # ── Diagnostic: which model is loaded in llm_service ──
    try:
        logs_result = subprocess.run(
            [docker_cmd, "logs", "--tail", "20", "llm_service"],
            capture_output=True, timeout=10,
        )
        llm_logs = logs_result.stderr.decode() + logs_result.stdout.decode()
        for line in llm_logs.splitlines():
            if any(kw in line.lower() for kw in ["model", "loaded", "registry", "preload", "gguf", "ctx="]):
                logging.info("  [llm_service] %s", line.strip())
    except Exception:
        pass

    # ── Diagnostic: LIDM standard-tier container ──
    try:
        lidm_result = subprocess.run(
            [docker_cmd, "ps", "-a", "--filter", "name=llm_service_standard",
             "--format", "{{.Names}} {{.Status}}"],
            capture_output=True, timeout=5,
        )
        lidm_out = lidm_result.stdout.decode().strip()
        if lidm_out:
            logging.info("  LIDM standard-tier: %s", lidm_out)
        else:
            logging.info("  LIDM standard-tier: not started (profile not active)")
    except Exception:
        pass

    # Check if orchestrator is reachable (assumes already running)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("localhost", 50054))
        sock.close()
        
        if result != 0:
            pytest.skip("orchestrator not reachable on port 50054. Please start services with 'make up' first.")
    except Exception as e:
        pytest.skip(f"Cannot check service health: {e}. Please ensure services are running.")
    
    logging.info("✓ Test environment validated (services appear to be running)")

    yield

    logging.info("✓ Test session complete")


@pytest.fixture(scope="session", autouse=True)
def llm_warmup(test_environment):
    """
    Send a lightweight warmup query to the LLM service so the model is loaded
    and ready before any test that depends on it. If the warmup fails after
    180 seconds the fixture still succeeds — individual tests will fail or
    skip on their own — but in the happy path this eliminates first-request
    DEADLINE_EXCEEDED errors.
    """
    import grpc

    try:
        # Import the generated stubs
        sys.path.insert(0, str(project_root))
        from shared.generated import llm_pb2, llm_pb2_grpc

        channel = grpc.insecure_channel("localhost:50051")
        stub = llm_pb2_grpc.LLMServiceStub(channel)

        logging.info("LLM warmup: sending probe request (timeout 180s)…")
        responses = stub.Generate(
            llm_pb2.GenerateRequest(
                prompt="Say OK.",
                max_tokens=8,
                temperature=0.1,
            ),
            timeout=180,
        )
        # Consume the stream
        for r in responses:
            if r.is_final:
                break
        logging.info("✓ LLM warmup complete — model is loaded")
        channel.close()
    except Exception as e:
        logging.warning(f"LLM warmup failed (tests may DEADLINE_EXCEED): {e}")

    yield
