# testing_tool/tests/test_integration.py
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
    final_answer = response.final_answer.strip()
    assert final_answer, "Final answer is empty."
    assert "LLM Service Error" not in final_answer, f"LLM returned an error: {final_answer}"
