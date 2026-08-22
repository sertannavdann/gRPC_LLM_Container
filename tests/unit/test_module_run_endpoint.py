"""
Tests for GET /modules/{category}/{platform}/run (Phase 8 Plan 12, D-07).

Mounts the real `run_module` handler defined in dashboard_service.main onto a
minimal FastAPI test app (per PLAN.md's own suggestion) — this avoids
bootstrapping the full auth middleware stack / OpenTelemetry / bank service
side effects that importing the production `app` object triggers, while
still exercising the exact handler function that ships in main.py.

Covers:
- Success fetch -> AdapterRunResult round-trips through AdapterRunResult.from_dict()
- Failed fetch -> HTTP 200, status=ERROR, errors[] populated, still round-trips
- Unregistered adapter -> 404
- Manifest present but not INSTALLED -> 404 (approval-gate bypass guard, T-08-49)
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from shared.adapters.base import AdapterConfig, AdapterResult, BaseAdapter
from shared.adapters.registry import adapter_registry
from shared.auth.models import Role, User
from shared.modules.manifest import ModuleManifest
from shared.modules.output_contract import AdapterRunResult

import dashboard_service.main as dashboard_main


# ─── Fixtures: fake adapters registered into the process-wide registry ────


class _FakeSuccessAdapter(BaseAdapter):
    category = "showroom_test"
    platform = "run_success"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:  # pragma: no cover
        return {"items": []}

    def transform(self, raw_data: Dict[str, Any]) -> List[Any]:  # pragma: no cover
        return []

    async def fetch(self, config: Optional[AdapterConfig] = None) -> AdapterResult:
        return AdapterResult(
            success=True,
            category=self.category,
            platform=self.platform,
            data=[{"temp_f": 72, "condition": "sunny"}, {"temp_f": 68, "condition": "cloudy"}],
            raw_count=2,
            transformed_count=2,
        )


class _FakeFailureAdapter(BaseAdapter):
    category = "showroom_test"
    platform = "run_failure"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:  # pragma: no cover
        return {}

    def transform(self, raw_data: Dict[str, Any]) -> List[Any]:  # pragma: no cover
        return []

    async def fetch(self, config: Optional[AdapterConfig] = None) -> AdapterResult:
        return AdapterResult(
            success=False,
            category=self.category,
            platform=self.platform,
            data=[],
            error="upstream API returned 503",
        )


@pytest.fixture(scope="module", autouse=True)
def _register_fake_adapters():
    adapter_registry.register(
        "showroom_test", "run_success", _FakeSuccessAdapter, display_name="Run Success"
    )
    adapter_registry.register(
        "showroom_test", "run_failure", _FakeFailureAdapter, display_name="Run Failure"
    )
    yield
    adapter_registry.unregister("showroom_test", "run_success")
    adapter_registry.unregister("showroom_test", "run_failure")


@pytest.fixture()
def client():
    """Minimal test app mounting the real handler, auth dependency overridden."""
    test_app = FastAPI()
    test_app.get("/modules/{category}/{platform}/run")(dashboard_main.run_module)

    fake_user = User(user_id="u1", org_id="test-org", role=Role.ADMIN)
    test_app.dependency_overrides[dashboard_main.get_current_user] = lambda: fake_user

    return TestClient(test_app)


# ─── Success case ───────────────────────────────────────────────────────


class TestRunModuleSuccess:
    def test_returns_200_with_valid_envelope(self, client):
        resp = client.get("/modules/showroom_test/run_success/run")
        assert resp.status_code == 200

        body = resp.json()
        # Round-trips through the canonical contract model.
        run_result = AdapterRunResult.from_dict(body)
        assert run_result.is_success()

    def test_run_module_id_and_capability(self, client):
        resp = client.get("/modules/showroom_test/run_success/run")
        body = resp.json()
        assert body["run"]["module_id"] == "showroom_test/run_success"
        assert body["run"]["capability"] == "fetch"

    def test_duration_ms_populated(self, client):
        resp = client.get("/modules/showroom_test/run_success/run")
        body = resp.json()
        assert body["metering"]["duration_ms"] >= 0

    def test_data_points_mapped_from_adapter_result(self, client):
        resp = client.get("/modules/showroom_test/run_success/run")
        body = resp.json()
        assert len(body["data_points"]) == 2
        assert body["data_points"][0]["data"]["temp_f"] == 72
        assert body["errors"] == []


# ─── Failure case ───────────────────────────────────────────────────────


class TestRunModuleFailure:
    def test_returns_200_with_error_status(self, client):
        resp = client.get("/modules/showroom_test/run_failure/run")
        assert resp.status_code == 200

        body = resp.json()
        run_result = AdapterRunResult.from_dict(body)
        assert run_result.is_error()
        assert not run_result.is_success()

    def test_error_message_carried_from_adapter(self, client):
        resp = client.get("/modules/showroom_test/run_failure/run")
        body = resp.json()
        assert len(body["errors"]) == 1
        assert "upstream API returned 503" in body["errors"][0]["message"]
        assert body["data_points"] == []


# ─── Not-found cases ────────────────────────────────────────────────────


class TestRunModuleNotFound:
    def test_unregistered_adapter_returns_404(self, client):
        resp = client.get("/modules/nonexistent_category/nonexistent_platform/run")
        assert resp.status_code == 404

    def test_manifest_not_installed_returns_404(self, client, tmp_path, monkeypatch):
        # A module registered in adapter_registry (so has_adapter() passes)
        # but whose on-disk manifest says VALIDATED, not INSTALLED, must
        # still 404 — the approval gate is not bypassable via the run path
        # (T-08-49).
        modules_dir = tmp_path / "modules"
        manifest_dir = modules_dir / "showroom_test" / "run_success"
        manifest_dir.mkdir(parents=True)

        manifest = ModuleManifest(
            name="run_success",
            category="showroom_test",
            platform="run_success",
            status="validated",
        )
        manifest.save(modules_dir)

        monkeypatch.setenv("MODULES_DIR", str(modules_dir))

        resp = client.get("/modules/showroom_test/run_success/run")
        assert resp.status_code == 404
