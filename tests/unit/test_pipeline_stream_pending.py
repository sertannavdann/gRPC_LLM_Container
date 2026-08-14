"""
Unit tests for the pending-approval SSE contract (dashboard_service/pipeline_stream.py).

Covers manifest-scan status mapping, robustness (malformed manifest, missing
dir), and the dedup merge inside _build_pipeline_state (D-01/D-03/D-04).

Fixtures mirror the tmp_path/manifest approach used in
tests/unit/modules/test_installer_approval_guard.py. The shared
`_write_manifest` helper is reused by the stage-enrichment tests added in
Task 3 (test_pipeline_stream_pending.py grows in that task, not duplicated).
"""
import asyncio

import pytest

from dashboard_service import pipeline_stream
from dashboard_service.pipeline_stream import (
    _build_pending_approval_list,
    _build_pipeline_state,
)
from shared.modules.manifest import ModuleManifest


def _write_manifest(tmp_path, category: str, platform: str, status: str) -> None:
    """Write a manifest.json under tmp_path/{category}/{platform}/manifest.json."""
    manifest = ModuleManifest(
        name=platform,
        category=category,
        platform=platform,
        status=status,
        display_name=platform.title(),
    )
    manifest.save(tmp_path)


class TestBuildPendingApprovalList:
    def test_validated_manifest_yields_pending_approval_true(self, tmp_path):
        _write_manifest(tmp_path, "test", "validated_mod", "validated")

        entries = _build_pending_approval_list(tmp_path)

        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == "test/validated_mod"
        assert entry["status"] == "validated"
        assert entry["pending_approval"] is True
        assert entry["build_stage"] == "validated"
        assert entry["state"] == "disabled"

    def test_validating_status_maps_to_documented_values(self, tmp_path):
        _write_manifest(tmp_path, "test", "validating_mod", "validating")

        entries = _build_pending_approval_list(tmp_path)

        entry = entries[0]
        assert entry["pending_approval"] is False
        assert entry["build_stage"] == "validating"
        assert entry["state"] == "disabled"

    def test_approved_status_maps_to_documented_values(self, tmp_path):
        _write_manifest(tmp_path, "test", "approved_mod", "approved")

        entries = _build_pending_approval_list(tmp_path)

        entry = entries[0]
        assert entry["status"] == "approved"
        assert entry["pending_approval"] is False
        assert entry["state"] == "disabled"

    def test_failed_status_maps_to_documented_values(self, tmp_path):
        _write_manifest(tmp_path, "test", "failed_mod", "failed")

        entries = _build_pending_approval_list(tmp_path)

        entry = entries[0]
        assert entry["status"] == "failed"
        assert entry["pending_approval"] is False
        assert entry["state"] == "failed"

    def test_unparseable_manifest_is_skipped_not_raised(self, tmp_path):
        module_dir = tmp_path / "test" / "broken_mod"
        module_dir.mkdir(parents=True)
        (module_dir / "manifest.json").write_text("{not valid json")

        entries = _build_pending_approval_list(tmp_path)

        assert entries == []

    def test_nonexistent_modules_dir_returns_empty_list(self, tmp_path):
        missing = tmp_path / "does_not_exist"

        entries = _build_pending_approval_list(missing)

        assert entries == []


class _FakeLoader:
    """Minimal stand-in for the real ModuleLoader used by _build_pipeline_state."""

    def __init__(self, modules):
        self._modules = modules

    def list_modules(self):
        return self._modules


class _FakeAppState:
    def __init__(self, module_loader):
        self.module_loader = module_loader


class _FakeApp:
    def __init__(self, module_loader):
        self.state = _FakeAppState(module_loader)


async def _stub_check_service(client, name, url):
    return {"name": name, "state": "running", "latency_ms": 1, "status_code": 200}


class TestBuildPipelineStateDedup:
    def test_loaded_and_on_disk_module_appears_exactly_once(self, tmp_path, monkeypatch):
        _write_manifest(tmp_path, "test", "dup_mod", "installed")

        monkeypatch.setattr(pipeline_stream, "MODULES_DIR", tmp_path)
        monkeypatch.setattr(pipeline_stream, "_check_service", _stub_check_service)

        loader = _FakeLoader([
            {"category": "test", "platform": "dup_mod", "name": "Dup Mod", "is_loaded": True},
        ])
        app = _FakeApp(loader)

        state = asyncio.run(_build_pipeline_state(app))

        matches = [m for m in state["modules"] if m["id"] == "test/dup_mod"]
        assert len(matches) == 1
        assert matches[0]["status"] == "installed"
        assert matches[0]["pending_approval"] is False

    def test_manifest_only_module_appears_in_payload(self, tmp_path, monkeypatch):
        _write_manifest(tmp_path, "test", "manifest_only_mod", "validated")

        monkeypatch.setattr(pipeline_stream, "MODULES_DIR", tmp_path)
        monkeypatch.setattr(pipeline_stream, "_check_service", _stub_check_service)

        loader = _FakeLoader([])
        app = _FakeApp(loader)

        state = asyncio.run(_build_pipeline_state(app))

        matches = [m for m in state["modules"] if m["id"] == "test/manifest_only_mod"]
        assert len(matches) == 1
        assert matches[0]["pending_approval"] is True
        assert matches[0]["status"] == "validated"
