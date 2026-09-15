"""
Unit tests for the canvas c_state export (dashboard_service/canvas_context.py).

Ports the canonical-ordering / format-stability claims from spike
005b-world-snapshot-miniplex (run.mjs) to the Python verbalizer: c_state text
must be byte-identical across churn for unchanged worlds regardless of
dict/list ordering, latency must render as a rounded int on both ports, and
no credential material may ever be emitted (T-09-04).
"""

import copy
import random

from fastapi.testclient import TestClient

from dashboard_service.canvas_context import (
    build_canvas_context,
    pipeline_state_to_views,
    to_compact_dsl,
)


def _fixture_state():
    return {
        "services": {
            "dashboard": {"name": "dashboard", "state": "running", "latency_ms": 0},
            "orchestrator_admin": {"name": "orchestrator_admin", "state": "running", "latency_ms": 12.4},
            "llm_service": {"name": "llm_service", "state": "unknown", "latency_ms": 0},
        },
        "modules": [
            {
                "id": "finance/cibc",
                "name": "CIBC",
                "state": "running",
                "status": "installed",
                "pending_approval": False,
                "build_stage": "installed",
            },
            {
                "id": "gaming/clashroyale",
                "name": "Clash Royale",
                "state": "disabled",
                "status": "validated",
                "pending_approval": True,
                "build_stage": "validating",
            },
            {
                "id": "weather/openweather",
                "name": "OpenWeather",
                "state": "running",
                "status": "installed",
                "pending_approval": False,
                "build_stage": "installed",
            },
        ],
        "adapters": [
            {
                "id": "finance/cibc",
                "name": "CIBC",
                "category": "finance",
                "platform": "cibc",
                "state": "running",
                "requires_auth": False,
                "has_credentials": True,
            },
            {
                "id": "calendar/google_calendar",
                "name": "Google Calendar",
                "category": "calendar",
                "platform": "google_calendar",
                "state": "error",
                "requires_auth": True,
                "has_credentials": False,
            },
        ],
        "tools": [
            {"name": "get_financial_summary", "stage": "finance", "connected_adapters": ["finance/cibc"]},
            {
                "name": "get_calendar_summary",
                "stage": "calendar",
                "connected_adapters": ["calendar/google_calendar", "calendar/outlook"],
            },
        ],
        "stage_tools": {"finance": ["get_financial_summary"], "calendar": ["get_calendar_summary"]},
        "timestamp": 1700000000.0,
    }


def test_header_present_and_grouped():
    state = _fixture_state()
    text = to_compact_dsl(pipeline_state_to_views(state))
    lines = text.split("\n")
    assert lines[0] == (
        '# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>]'
        "[ detail=<detail>][ latency=<ms>][ creds:<c1,c2>][ flags:<f1,f2>]"
    )
    group_headers = [l for l in lines if l.startswith("[") and l.endswith("]")]
    assert group_headers == ["[adapter]", "[module]", "[service]", "[stage]", "[tool]"]


def test_byte_stable_across_reordering():
    state = _fixture_state()
    baseline = to_compact_dsl(pipeline_state_to_views(state))

    shuffled = copy.deepcopy(state)
    random.Random(42).shuffle(shuffled["modules"])
    random.Random(7).shuffle(shuffled["adapters"])
    random.Random(3).shuffle(shuffled["tools"])
    shuffled["services"] = dict(reversed(list(state["services"].items())))

    shuffled_text = to_compact_dsl(pipeline_state_to_views(shuffled))
    assert shuffled_text == baseline


def test_latency_rendered_as_rounded_int():
    state = _fixture_state()
    text = to_compact_dsl(pipeline_state_to_views(state))
    assert "latency=12.4" not in text
    assert 'svc-orchestrator_admin "orchestrator_admin" running latency=12' in text


def test_no_credential_material_emitted():
    state = _fixture_state()
    text = to_compact_dsl(pipeline_state_to_views(state))
    import re

    assert not re.search(r"API_KEY|TOKEN|SECRET|PASSWORD", text)
    assert "flags:auth_required,no_credentials" in text


def test_degrades_on_malformed_state():
    result = pipeline_state_to_views({"modules": "not-a-list"})
    assert isinstance(result, list)


def test_route_registered_before_category():
    from dashboard_service.main import app

    routes = [r.path for r in app.router.routes if getattr(r, "path", None)]
    canvas_idx = routes.index("/context/canvas")
    category_idx = routes.index("/context/{category}")
    assert canvas_idx < category_idx

    client = TestClient(app)
    response = client.get("/context/canvas")
    assert response.status_code == 200
    body = response.json()
    assert body["c_state"].startswith("# pipeline_state")
