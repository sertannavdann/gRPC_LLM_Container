# testing_tool/tests/test_e2e.py

import subprocess
import time
import pytest
import grpc
from agent_service import agent_pb2, agent_pb2_grpc
import shutil

def get_docker_compose_cmd():
    """Detect which docker compose command to use (V1 or V2)"""
    # Common docker locations
    docker_paths = [
        "docker",  # In PATH
        "/usr/local/bin/docker",  # Standard macOS Docker Desktop location
        "/Applications/Docker.app/Contents/Resources/bin/docker"  # Direct Docker.app path
    ]
    
    # Try docker compose (V2) first
    for docker_path in docker_paths:
        try:
            result = subprocess.run([docker_path, "compose", "version"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return [docker_path, "compose"]
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    
    # Fall back to docker-compose (V1)
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    
    # No docker compose found
    pytest.skip("Docker or docker-compose not available")

def test_full_system():
    docker_cmd = get_docker_compose_cmd()
    
    try:
        subprocess.run(docker_cmd + ["up", "-d"], check=True)
        time.sleep(20)  # increased wait time to ensure LLM is fully operational

        channel = grpc.insecure_channel("localhost:50054")
        stub = agent_pb2_grpc.AgentServiceStub(channel)

        response = stub.QueryAgent(
            agent_pb2.AgentRequest(user_query="Explain quantum computing")
        )
        final_answer = response.final_answer.strip()
        assert final_answer, "Final answer is empty."
        assert "LLM Service Error" not in final_answer, f"LLM returned an error: {final_answer}"
    finally:
        subprocess.run(docker_cmd + ["down"])
