import pytest
import grpc

from testing_tool.client import TestClient
from testing_tool.config import SERVICES

from google.protobuf.struct_pb2 import Struct

from chroma_service import chroma_pb2
from llm_service import llm_pb2
from tool_service import tool_pb2


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
def llm_client():
    _skip_unless_service_ready("llm")
    return TestClient(SERVICES["llm"])

@pytest.fixture(scope="module")
def chroma_client():
    _skip_unless_service_ready("chroma")
    return TestClient(SERVICES["chroma"])

@pytest.fixture(scope="module")
def tool_client():
    _skip_unless_service_ready("tool")
    return TestClient(SERVICES["tool"])

def test_llm_basic_generation(llm_client):
    response = llm_client.call(
        "Generate",  # Updated method name
        llm_pb2.GenerateRequest(prompt="Hello", max_tokens=10)
    )

def test_chroma_basic_operations(chroma_client):
    metadata = Struct()
    metadata.update({"test": "true"})
    
    add_response = chroma_client.call(
        "AddDocument",
        chroma_pb2.AddDocumentRequest(
            document=chroma_pb2.Document(
                id="test_001",
                text="Test content",
                metadata=metadata
            )
        )
    )
    assert add_response.success

def test_tool_service_search(tool_client):
    params = Struct()
    fields = {}
    fields["query"] = {"stringValue": "grpcurl test"}
    fields["max_results"] = {"stringValue": "5"}
    params.update({"fields": fields})
    
    response = tool_client.call(
        "CallTool",
        tool_pb2.ToolRequest(
            tool_name="web_search",
            params=params
        )
    )
    assert response.success