import types
import time
from types import SimpleNamespace

import grpc
import pytest

import chroma_pb2
import llm_pb2
import tool_pb2

from agent_service.agent_service import AgentMetrics, AgentOrchestrator
from chroma_service import chroma_service as chroma_module
from chroma_service.chroma_service import ChromaServiceServicer
from llm_service import llm_service as llm_module
from llm_service.llm_service import LLMServiceServicer
from shared.clients.cpp_llm_client import CppLLMClient
from shared.generated import cpp_llm_pb2
from tool_service.tool_service import ToolService


class _DummyGrpcContext:
    def abort(self, code, details):  # pragma: no cover - invoked in error path tests
        raise grpc.RpcError(details)


def test_cpp_llm_client_success():
    client = CppLLMClient.__new__(CppLLMClient)
    client._timeout = 1
    client._stub = SimpleNamespace(
        RunInference=lambda request, timeout=None: cpp_llm_pb2.InferenceResponse(
            output="[stubbed inference] HELLO",
            intent_payload="{\"intent\": \"schedule_event\"}"
        )
    )

    result = CppLLMClient.run_inference(client, "hello")
    assert result["output"].startswith("[stubbed inference]")
    assert "schedule_event" in result["intent_payload"]


def test_cpp_llm_client_error():
    class FakeRpcError(grpc.RpcError):
        def __init__(self, code, details):
            self._code = code
            self._details = details

        def code(self):
            return self._code

        def details(self):
            return self._details

    error = FakeRpcError(grpc.StatusCode.UNAVAILABLE, "service offline")

    client = CppLLMClient.__new__(CppLLMClient)
    client._timeout = 1
    client._stub = SimpleNamespace(RunInference=lambda request, timeout=None: (_ for _ in ()).throw(error))

    result = CppLLMClient.run_inference(client, "hello")
    assert result["output"].startswith("[cpp-llm-error]")
    assert result["intent_payload"] == ""


def test_agent_cpp_llm_tool():
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.cpp_llm = SimpleNamespace(
        run_inference=lambda prompt: {
            "output": "[stubbed inference] SCHEDULE",
            "intent_payload": "{\"intent\": \"schedule_event\"}"
        }
    )
    orchestrator.metrics = AgentMetrics(llm_calls=1, avg_response_time=0.0)

    result = AgentOrchestrator._cpp_llm_inference(orchestrator, "schedule a call", return_intent=True)
    assert "schedule_event" in result["intent_payload"]
    assert orchestrator.metrics.avg_response_time >= 0.0


def test_llm_service_generate_stream(monkeypatch):
    class DummyLLM:
        def __call__(self, prompt, **kwargs):
            yield {"choices": [{"text": "Hello"}]}
            yield {"choices": [{"text": "!"}]}

    llm_module.load_model.cache_clear()
    monkeypatch.setattr(llm_module, "load_model", lambda: DummyLLM())

    servicer = LLMServiceServicer()
    responses = list(servicer.Generate(
        llm_pb2.GenerateRequest(prompt="Hello", max_tokens=4, temperature=0.2),
        _DummyGrpcContext()
    ))
    assert responses[-1].is_final is True
    tokens = "".join(r.token for r in responses[:-1])
    assert tokens == "Hello!"


def test_chroma_service_add_document(monkeypatch):
    class DummyCollection:
        def __init__(self):
            self.add_calls = []

        def add(self, documents, ids, metadatas):
            self.add_calls.append((documents, ids, metadatas))

    class DummyLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    servicer = ChromaServiceServicer.__new__(ChromaServiceServicer)
    servicer.chroma = SimpleNamespace(
        lock=DummyLock(),
        collection=DummyCollection()
    )

    response = ChromaServiceServicer.AddDocument(servicer,
        chroma_pb2.AddDocumentRequest(
            document=chroma_pb2.Document(
                id="doc-1",
                text="example",
            )
        ),
        _DummyGrpcContext()
    )
    assert response.success is True
    assert servicer.chroma.collection.add_calls[0][0][0] == "example"


def test_tool_service_math_solver():
    service = ToolService.__new__(ToolService)
    service.headers = {}
    service.base_url = ""
    service.api_key = "dummy"
    result = ToolService._handle_math(service, {"expression": "1+2"})
    assert result.success is True
    assert "Math Result" in result.results[0].title
*** End Patch