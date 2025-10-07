import json

import pytest

from testing_tool import mock_agent_flow


@pytest.mark.parametrize(
    "query",
    [
        "Please schedule time with Alex this afternoon.",
        "Set up a 45 minute sync with Alex Johnson",
    ],
)
def test_mock_agent_flow_returns_answer(query):
    summary = mock_agent_flow.run_mock_flow(query)

    assert "Meeting" in summary["final_answer"]
    assert "schedule_meeting" in " ".join(summary["tools_used"] + ["schedule_meeting"])
    assert any("Alex" in json.dumps(entry) for entry in summary["context"])