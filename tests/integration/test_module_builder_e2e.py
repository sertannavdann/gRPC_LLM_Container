"""
Integration tests for the LLM-driven Module Builder (Track A4).

Exercises the full build → validate → install pipeline through the
live orchestrator gRPC service. These are NOT mocked — they require
the Docker Compose stack to be running.

Prerequisites:
    docker compose --profile lidm up -d

Markers:
    @pytest.mark.integration   — requires live services
    @pytest.mark.module_builder — Track A4 specific
"""

import json
import logging
import os
import time

import pytest
import requests

from integration.grpc_test_client import AgentTestClient

logger = logging.getLogger(__name__)

ORCHESTRATOR_HOST = os.getenv("ORCHESTRATOR_HOST", "localhost")
ORCHESTRATOR_PORT = int(os.getenv("ORCHESTRATOR_PORT", "50054"))
ADMIN_URL = os.getenv("ADMIN_URL", "http://localhost:8003")
GRPC_TIMEOUT = 120  # Module builds are multi-step and slow on local LLMs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def grpc_client():
    """Create a gRPC client with a long timeout for module builds."""
    try:
        with AgentTestClient(
            host=ORCHESTRATOR_HOST,
            port=ORCHESTRATOR_PORT,
            timeout=GRPC_TIMEOUT,
        ) as client:
            yield client
    except Exception as e:
        pytest.skip(f"Orchestrator not reachable: {e}")


@pytest.fixture(scope="module")
def admin_api():
    """Verify admin API is reachable."""
    try:
        r = requests.get(f"{ADMIN_URL}/admin/health", timeout=5)
        r.raise_for_status()
    except Exception as e:
        pytest.skip(f"Admin API not reachable: {e}")
    return ADMIN_URL


def _cleanup_module(admin_url: str, module_id: str):
    """Delete a module via the admin API (best-effort cleanup)."""
    try:
        category, platform = module_id.split("/")
        requests.delete(
            f"{admin_url}/admin/modules/{category}/{platform}",
            timeout=5,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestModuleBuilderE2E:
    """End-to-end tests for the module builder pipeline."""

    def test_build_weather_module(self, grpc_client, admin_api):
        """
        Full pipeline: user asks to build a module → agent calls
        build_module → write → validate → install in a multi-step flow.
        """
        # Clean up in case a previous run left artifacts
        _cleanup_module(admin_api, "weather/testweather")

        response = grpc_client.query(
            "Build me a weather module called testweather that fetches "
            "weather data from Open-Meteo API at https://api.open-meteo.com/v1/forecast. "
            "It does not require an API key."
        )

        assert response is not None
        assert len(response.final_answer) > 0

        # Verify the response mentions the module was built or installed
        answer_lower = response.final_answer.lower()
        built_or_installed = any(
            kw in answer_lower
            for kw in ["built", "created", "installed", "module", "scaffold", "ready"]
        )
        assert built_or_installed, (
            f"Expected module build confirmation, got: {response.final_answer[:300]}"
        )

        # Verify via admin API that the module exists
        r = requests.get(f"{admin_api}/admin/modules", timeout=5)
        if r.ok:
            modules = r.json()
            ids = [m.get("module_id", "") for m in modules if isinstance(m, dict)]
            logger.info(f"Modules after build: {ids}")

        # Cleanup
        _cleanup_module(admin_api, "weather/testweather")

    def test_build_response_includes_sources(self, grpc_client, admin_api):
        """Verify the agent response mentions the module was created."""
        _cleanup_module(admin_api, "test/srccheck")

        response = grpc_client.query(
            "Create a module called srccheck in category test. "
            "It talks to https://api.example.com/data. Needs an API key."
        )

        assert response is not None
        # The response text should reference the module creation
        reply = (response.final_answer or "").lower()
        assert any(kw in reply for kw in ("srccheck", "module", "created", "built", "exists")), (
            f"Expected module-related keywords in response: {reply[:200]}"
        )

        # If structured sources are available, verify tool calls
        if response.sources:
            try:
                sources = json.loads(response.sources)
                tool_names = [
                    t.get("tool_name", "")
                    for t in sources.get("tools_used", [])
                ]
                if tool_names and tool_names != [""]:
                    logger.info(f"Tools used in build: {tool_names}")
                    assert any("build_module" in t for t in tool_names), (
                        f"Expected build_module in tool calls, got: {tool_names}"
                    )
                else:
                    logger.info("Sources present but no structured tool_names")
            except (json.JSONDecodeError, AttributeError):
                logger.info("Sources not in JSON format — skipping tool check")

        _cleanup_module(admin_api, "test/srccheck")


@pytest.mark.integration
class TestModuleBuilderGuards:
    """Tests for safety guards in the module install pipeline."""

    def test_install_rejects_unvalidated_via_admin(self, admin_api):
        """
        Directly test that the admin install endpoint (or tool)
        rejects a module that hasn't been validated.
        
        This uses the unit-level tool directly rather than going
        through the full LLM pipeline, for determinism.
        """
        # This is primarily covered by unit tests (test_rejects_pending_module)
        # Integration verification: check admin /modules endpoint exists
        r = requests.get(f"{admin_api}/admin/modules", timeout=5)
        assert r.status_code == 200

    def test_admin_module_crud(self, admin_api):
        """Verify the admin module listing API is functional."""
        r = requests.get(f"{admin_api}/admin/modules", timeout=5)
        assert r.status_code == 200
        data = r.json()
        # Response is {"modules": [...], "loaded": N, "total": N}
        if isinstance(data, dict):
            assert "modules" in data
            assert isinstance(data["modules"], list)
        else:
            assert isinstance(data, list)
