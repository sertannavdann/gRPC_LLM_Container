# testing_tool/tests/test_integration.py
import grpc
import pytest

from testing_tool.client import TestClient
from testing_tool.config import SERVICES

from agent_service import agent_pb2


def _skip_unless_service_ready(service_name: str, timeout: float = 0.5) -> None:
    config = SERVICES[service_name]
    channel = grpc.insecure_channel(f"{config['host']}:{config['port']}")
    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
    except grpc.FutureTimeoutError:
        pytest.skip(f"{service_name} service is not running on {config['host']}:{config['port']}")
    finally:
        channel.close()

@pytest.fixture(scope="module")
def agent_client():
    _skip_unless_service_ready("agent")
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
