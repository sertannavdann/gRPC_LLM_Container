import pytest
from testing_tool.client import TestClient
from testing_tool.config import SERVICES
import agent_pb2

@pytest.fixture(scope="module")
def agent_client():
    return TestClient(SERVICES["agent"])

def test_full_workflow(agent_client):
    response = agent_client.call(
        "QueryAgent",
        agent_pb2.AgentRequest(user_query="What is AI?"),
        timeout=20
    )
    assert len(response.final_answer) > 50
    assert "AI" in response.final_answer