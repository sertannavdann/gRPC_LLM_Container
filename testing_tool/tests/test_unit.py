import pytest
from testing_tool.client import TestClient
from testing_tool.config import SERVICES

from google.protobuf.struct_pb2 import Struct

import chroma_pb2
import llm_pb2
import tool_pb2

@pytest.fixture(scope="module")
def llm_client():
    return TestClient(SERVICES["llm"])

@pytest.fixture(scope="module")
def chroma_client():
    return TestClient(SERVICES["chroma"])

@pytest.fixture(scope="module")
def tool_client():
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
    params.update({"query": "test", "max_results": "1"})
    
    response = tool_client.call(
        "CallTool",
        tool_pb2.ToolRequest(
            tool_name="web_search",
            params=params
        )
    )
    assert response.success