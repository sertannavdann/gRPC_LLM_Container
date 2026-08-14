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
import os

import pytest

from dashboard_service import pipeline_stream
from dashboard_service.pipeline_stream import (
    _build_pending_approval_list,
    _build_pipeline_state,
    _build_stage_index,
)
from shared.modules.audit import AttemptRecord, AttemptStatus, BuildAuditLog
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


def _write_audit_log(audit_dir, job_id: str, module_id: str, stage: str, mtime: float = None):
    """Build a real BuildAuditLog with one attempt at `stage` and save it."""
    log = BuildAuditLog(job_id=job_id, module_id=module_id)
    log.add_attempt(AttemptRecord(
        attempt_number=1,
        bundle_sha256="x" * 8,
        stage=stage,
        status=AttemptStatus.FAILED,
    ))
    audit_file = log.save(audit_dir)
    if mtime is not None:
        os.utime(audit_file, (mtime, mtime))
    return audit_file


@pytest.fixture(autouse=True)
def _reset_stage_index_cache():
    """Prevent cached stage-index state from leaking between tests."""
    pipeline_stream._STAGE_INDEX_CACHE["key"] = None
    pipeline_stream._STAGE_INDEX_CACHE["value"] = {}
    yield
    pipeline_stream._STAGE_INDEX_CACHE["key"] = None
    pipeline_stream._STAGE_INDEX_CACHE["value"] = {}


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


class TestBuildStageIndex:
    def test_missing_audit_dir_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "no_audit"

        assert _build_stage_index(missing) == {}

    def test_malformed_audit_file_is_skipped(self, tmp_path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        (audit_dir / "broken_audit.json").write_text("{not valid json")

        assert _build_stage_index(audit_dir) == {}

    def test_two_files_same_module_newest_mtime_wins(self, tmp_path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        _write_audit_log(audit_dir, "test_repair_a1", "test/repair_mod", "implement", mtime=1000.0)
        _write_audit_log(audit_dir, "test_repair_a2", "test/repair_mod", "repair", mtime=2000.0)

        index = _build_stage_index(audit_dir)

        assert index["test/repair_mod"] == "repair"


class TestLiveBuildStageEnrichment:
    def test_validating_with_repair_stage_yields_repair(self, tmp_path):
        modules_dir = tmp_path / "modules"
        audit_dir = tmp_path / "audit"
        modules_dir.mkdir()
        audit_dir.mkdir()
        _write_manifest(modules_dir, "test", "repair_mod", "validating")
        _write_audit_log(audit_dir, "test_repair_mod_a1", "test/repair_mod", "repair")

        entries = _build_pending_approval_list(modules_dir, audit_dir=audit_dir)

        entry = next(e for e in entries if e["id"] == "test/repair_mod")
        assert entry["build_stage"] == "repair"
        assert entry["pending_approval"] is False

    @pytest.mark.parametrize("stage", ["scaffold", "implement", "tests", "repair"])
    def test_validating_with_each_stage(self, tmp_path, stage):
        modules_dir = tmp_path / "modules"
        audit_dir = tmp_path / "audit"
        modules_dir.mkdir()
        audit_dir.mkdir()
        _write_manifest(modules_dir, "test", "stage_mod", "validating")
        _write_audit_log(audit_dir, "test_stage_mod_a1", "test/stage_mod", stage)

        entries = _build_pending_approval_list(modules_dir, audit_dir=audit_dir)

        entry = next(e for e in entries if e["id"] == "test/stage_mod")
        assert entry["build_stage"] == stage

    def test_pending_with_no_audit_file_falls_back_to_status(self, tmp_path):
        modules_dir = tmp_path / "modules"
        audit_dir = tmp_path / "audit"
        modules_dir.mkdir()
        audit_dir.mkdir()
        _write_manifest(modules_dir, "test", "no_audit_mod", "pending")

        entries = _build_pending_approval_list(modules_dir, audit_dir=audit_dir)

        entry = next(e for e in entries if e["id"] == "test/no_audit_mod")
        assert entry["build_stage"] == "pending"

    def test_validated_module_keeps_validated_stage_even_with_audit_file(self, tmp_path):
        modules_dir = tmp_path / "modules"
        audit_dir = tmp_path / "audit"
        modules_dir.mkdir()
        audit_dir.mkdir()
        _write_manifest(modules_dir, "test", "validated_stale_mod", "validated")
        _write_audit_log(audit_dir, "test_validated_stale_mod_a1", "test/validated_stale_mod", "repair")

        entries = _build_pending_approval_list(modules_dir, audit_dir=audit_dir)

        entry = next(e for e in entries if e["id"] == "test/validated_stale_mod")
        assert entry["build_stage"] == "validated"
        assert entry["pending_approval"] is True

    def test_no_in_flight_modules_skips_audit_scan_entirely(self, tmp_path, monkeypatch):
        modules_dir = tmp_path / "modules"
        audit_dir = tmp_path / "audit"
        modules_dir.mkdir()
        audit_dir.mkdir()
        _write_manifest(modules_dir, "test", "installed_mod", "installed")

        called = {"count": 0}
        original = pipeline_stream._build_stage_index

        def _tracking_stage_index(*args, **kwargs):
            called["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(pipeline_stream, "_build_stage_index", _tracking_stage_index)

        _build_pending_approval_list(modules_dir, audit_dir=audit_dir)

        assert called["count"] == 0
