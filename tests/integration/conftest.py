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
    
    # Check if agent_service is reachable (assumes already running)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("localhost", 50054))
        sock.close()
        
        if result != 0:
            pytest.skip("agent_service not reachable on port 50054. Please start services with 'make up' first.")
    except Exception as e:
        pytest.skip(f"Cannot check service health: {e}. Please ensure services are running.")
    
    logging.info("✓ Test environment validated (services appear to be running)")
    
    yield
    
    logging.info("✓ Test session complete")
