"""Lightweight harness to exercise the agent orchestration with mock services.

Run this module directly to see an end-to-end flow without starting the gRPC stack:

    conda run -n llm python -m testing_tool.mock_agent_flow

The script stubs the LLM, vector search, tool service, and the native C++ bridge so
we can validate control flow decisions and tool selection.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable

from langchain_core.messages import AIMessage, FunctionMessage, HumanMessage

from agent_service.agent_service import AgentOrchestrator, AgentState


class _MockLLMClient:
    """Return deterministic responses emulating the llm_service."""

    def __init__(self) -> None:
        self._call_count = 0

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:  # noqa: D401
        self._call_count += 1

        if self._call_count == 1:
            return json.dumps(
                {
                    "function_call": {
                        "name": "schedule_meeting",
                        "arguments": {
                            "person": "Alex Johnson",
                            "start_time_iso8601": "2025-10-06T15:00:00Z",
                            "duration_minutes": 45,
                        },
                    }
                }
            )

        return json.dumps(
            {
                "content": "Meeting scheduled with Alex Johnson at 2025-10-06T15:00:00Z."
            }
        )


class _MockCppLLMClient:
    def run_inference(self, prompt: str) -> Dict[str, str]:
        return {
            "output": f"[mock cpp llm output] {prompt}",
            "intent_payload": json.dumps({"intent": "schedule_event"}),
        }

    def trigger_schedule_meeting(
        self,
        *,
        person: str,
        start_time_iso8601: str,
        duration_minutes: int,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "message": f"Meeting scheduled for {person}",
            "event_identifier": "evt-mock-001",
        }


class _MockChromaClient:
    def query(self, query_text: str, top_k: int = 3) -> Iterable[Dict[str, Any]]:
        return [
            {
                "text": "Alex prefers meetings in the afternoon.",
                "metadata": {"source": "calendar_notes"},
                "score": 0.9,
            }
        ]


class _MockToolClient:
    def web_search(self, query: str, max_results: int = 5):
        return [
            {
                "title": "Mock Search Result",
                "snippet": f"Answering question about: {query}",
                "url": "https://example.com/mock",
            }
        ]

    def math_solver(self, expression: str):
        return {"result": 42, "expression": expression}


def build_mock_orchestrator() -> AgentOrchestrator:
    orchestrator = AgentOrchestrator()
    orchestrator.llm = _MockLLMClient()
    orchestrator.cpp_llm = _MockCppLLMClient()
    orchestrator.chroma = _MockChromaClient()
    orchestrator.tool_client = _MockToolClient()
    orchestrator.llm_orchestrator.llm = orchestrator.llm
    orchestrator.workflow = orchestrator._init_workflow()
    return orchestrator


def run_mock_flow(user_query: str) -> Dict[str, Any]:
    orchestrator = build_mock_orchestrator()

    state = AgentState(
        messages=[HumanMessage(content=user_query)],
        context=[],
        tools_used=[],
        errors=[],
        start_time=time.time(),
    )

    config = {"configurable": {"thread_id": "mock"}}
    final_state = None
    tools_used: list[str] = []
    context_entries: list[Dict[str, Any]] = []

    for step in orchestrator.workflow.stream(state, config=config):
        node, data = next(iter(step.items()))
        final_state = data

        if node == "tool":
            for message in data.get("messages", []):
                if isinstance(message, FunctionMessage):
                    tools_used.append(message.name)
                    try:
                        payload = json.loads(message.content)
                        context_entries.append(payload)
                    except json.JSONDecodeError:
                        context_entries.append({"raw": message.content})

    assert final_state is not None, "Workflow did not yield a final state"

    messages = final_state.get("messages", [])
    final_answer = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.additional_kwargs.get("function_call"):
            final_answer = message.content
            break

    return {
        "final_answer": final_answer,
        "context": context_entries,
        "tools_used": tools_used,
    }


def main() -> None:
    summary = run_mock_flow("Please schedule time with Alex this afternoon.")
    print("Final answer:\n", summary["final_answer"])
    print("\nTools used:", summary["tools_used"])
    print("\nContext entries:")
    for item in summary["context"]:
        print(" -", json.dumps(item, indent=2))


if __name__ == "__main__":
    main()
