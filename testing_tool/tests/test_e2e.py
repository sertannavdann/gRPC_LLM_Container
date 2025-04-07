import subprocess
import time
import pytest
import grpc
import agent_pb2, agent_pb2_grpc

def test_full_system():
    try:
        subprocess.run(["docker-compose", "up", "-d"])
        time.sleep(15)
        
        channel = grpc.insecure_channel("localhost:50054")
        stub = agent_pb2_grpc.AgentServiceStub(channel)
        
        response = stub.QueryAgent(
            agent_pb2.AgentRequest(user_query="Explain quantum computing")
        )
        assert len(response.final_answer) > 50
        
    finally:
        subprocess.run(["docker-compose", "down"])