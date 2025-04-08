# testing_tool/tests/test_e2e.py

import subprocess
import time
import pytest
import grpc
import agent_pb2, agent_pb2_grpc

def test_full_system():
    try:
        subprocess.run(["docker-compose", "up", "-d"], check=True)
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
        subprocess.run(["docker-compose", "down"])
