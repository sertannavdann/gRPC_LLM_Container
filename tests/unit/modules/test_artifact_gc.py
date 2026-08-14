"""
Unit tests for the artifact-GC sweep (D-10, D-12, T-08-14/15/16).

Covers `sweep_gc_pending()` / `purge_module_artifacts()` in
`shared/modules/gc.py`: reference-safe deletion of terminally rejected
module artifacts, audit-record preservation, and unconditional purge for
modules with no version history (RESEARCH Pitfall 5).

Uses tmp_path fixtures for filesystem isolation, mirroring the tmp_path
fixture style used in test_installer_approval_guard.py. A stub version
manager (exposing list_versions/get_active_version) is used for most cases;
one test exercises a real VersionManager to prove the signatures match.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared.modules.gc import (
    GC_MARKER_FILENAME,
    purge_module_artifacts,
    queue_for_gc,
    sweep_gc_pending,
)
from shared.modules.versioning import VersionManager


class StubVersionManager:
    """Minimal stub exposing the two methods gc.py relies on."""

    def __init__(self, versions_by_module=None, active_by_module=None):
        self._versions = versions_by_module or {}
        self._active = active_by_module or {}

    def list_versions(self, module_id, org_id=None):
        return self._versions.get(module_id, [])

    def get_active_version(self, module_id, org_id=None):
        return self._active.get(module_id)


@pytest.fixture
def modules_dir(tmp_path):
    d = tmp_path / "modules"
    d.mkdir()
    return d


@pytest.fixture
def artifacts_dir(tmp_path):
    d = tmp_path / "artifacts"
    d.mkdir()
    return d


def _make_module(modules_dir: Path, category: str, platform: str, with_jsonl: bool = False):
    module_dir = modules_dir / category / platform
    module_dir.mkdir(parents=True)
    (module_dir / "adapter.py").write_text("# adapter code\n")
    (module_dir / "manifest.json").write_text(json.dumps({"category": category, "platform": platform}))
    if with_jsonl:
        (module_dir / "build_audit.jsonl").write_text('{"event": "scaffold"}\n')
    return module_dir


def _make_artifacts(artifacts_dir: Path, category: str, platform: str):
    d = artifacts_dir / category / platform
    d.mkdir(parents=True)
    (d / "bundle.txt").write_text("bundle-content")
    return d


def _write_marker(module_dir: Path, module_id: str, rejected_at: str = None, actor: str = "tester"):
    marker = {
        "module_id": module_id,
        "rejected_at": rejected_at or datetime.now(timezone.utc).isoformat(),
        "actor": actor,
    }
    (module_dir / GC_MARKER_FILENAME).write_text(json.dumps(marker))


# ── purge_module_artifacts: reference safety (D-12) ────────────────────


def test_active_version_referenced_module_is_protected(modules_dir, artifacts_dir):
    module_dir = _make_module(modules_dir, "weather", "openweather")
    _make_artifacts(artifacts_dir, "weather", "openweather")
    vm = StubVersionManager(
        versions_by_module={"weather/openweather": [object()]},
        active_by_module={"weather/openweather": object()},
    )

    result = purge_module_artifacts("weather/openweather", modules_dir, artifacts_dir, version_manager=vm)

    assert result == {"purged": False, "reason": "active_version_reference"}
    assert module_dir.exists()


def test_versions_but_no_active_pointer_is_purged(modules_dir, artifacts_dir):
    _make_module(modules_dir, "weather", "openweather")
    vm = StubVersionManager(
        versions_by_module={"weather/openweather": [object()]},
        active_by_module={},  # no active pointer
    )

    result = purge_module_artifacts("weather/openweather", modules_dir, artifacts_dir, version_manager=vm)

    assert result["purged"] is True
    assert not (modules_dir / "weather" / "openweather").exists()


def test_no_version_rows_purged_unconditionally(modules_dir, artifacts_dir):
    _make_module(modules_dir, "test", "hello")
    vm = StubVersionManager(versions_by_module={}, active_by_module={})

    result = purge_module_artifacts("test/hello", modules_dir, artifacts_dir, version_manager=vm)

    assert result["purged"] is True
    assert not (modules_dir / "test" / "hello").exists()


def test_purge_with_no_version_manager_purges_unconditionally(modules_dir, artifacts_dir):
    _make_module(modules_dir, "test", "hello")

    result = purge_module_artifacts("test/hello", modules_dir, artifacts_dir, version_manager=None)

    assert result["purged"] is True
    assert not (modules_dir / "test" / "hello").exists()


# ── purge_module_artifacts: audit-record preservation ──────────────────


def test_jsonl_files_survive_purge(modules_dir, artifacts_dir):
    module_dir = _make_module(modules_dir, "test", "hello", with_jsonl=True)
    assert (module_dir / "build_audit.jsonl").exists()

    result = purge_module_artifacts("test/hello", modules_dir, artifacts_dir, version_manager=None)

    assert result["purged"] is True
    assert not module_dir.exists()  # module dir itself is gone
    preserved_paths = [Path(p) for p in result["preserved"]]
    assert len(preserved_paths) == 1
    assert preserved_paths[0].exists()
    assert preserved_paths[0].name == "build_audit.jsonl"
    assert preserved_paths[0].read_text() == '{"event": "scaffold"}\n'


def test_artifact_bundle_directory_is_removed_for_purged_module(modules_dir, artifacts_dir):
    _make_module(modules_dir, "test", "hello")
    artifact_dir = _make_artifacts(artifacts_dir, "test", "hello")
    assert artifact_dir.exists()

    result = purge_module_artifacts("test/hello", modules_dir, artifacts_dir, version_manager=None)

    assert result["purged"] is True
    assert not artifact_dir.exists()


def test_protected_module_artifacts_untouched(modules_dir, artifacts_dir):
    _make_module(modules_dir, "weather", "openweather")
    artifact_dir = _make_artifacts(artifacts_dir, "weather", "openweather")
    vm = StubVersionManager(
        versions_by_module={"weather/openweather": [object()]},
        active_by_module={"weather/openweather": object()},
    )

    purge_module_artifacts("weather/openweather", modules_dir, artifacts_dir, version_manager=vm)

    assert artifact_dir.exists()


def test_unsafe_module_id_rejected(modules_dir, artifacts_dir):
    with pytest.raises(ValueError):
        purge_module_artifacts("../etc/passwd", modules_dir, artifacts_dir, version_manager=None)


# ── sweep_gc_pending ─────────────────────────────────────────────────


def test_sweep_purges_and_protects_correctly(modules_dir, artifacts_dir):
    protected_dir = _make_module(modules_dir, "weather", "openweather")
    _write_marker(protected_dir, "weather/openweather")

    purge_dir = _make_module(modules_dir, "test", "hello")
    _write_marker(purge_dir, "test/hello")

    vm = StubVersionManager(
        versions_by_module={"weather/openweather": [object()]},
        active_by_module={"weather/openweather": object()},
    )

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=vm)

    assert summary["scanned"] == 2
    assert summary["purged"] == ["test/hello"]
    assert summary["protected"] == ["weather/openweather"]
    assert summary["errors"] == []
    assert protected_dir.exists()
    assert not purge_dir.exists()


def test_sweep_handles_unparseable_rejected_at_without_aborting(modules_dir, artifacts_dir):
    module_dir = _make_module(modules_dir, "test", "hello")
    _write_marker(module_dir, "test/hello", rejected_at="not-a-timestamp")

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=None)

    assert summary["scanned"] == 1
    assert summary["purged"] == ["test/hello"]
    assert len(summary["errors"]) == 1
    assert "unparseable rejected_at" in summary["errors"][0]["error"]
    assert not module_dir.exists()


def test_sweep_bad_marker_does_not_abort_others(modules_dir, artifacts_dir):
    bad_dir = _make_module(modules_dir, "bad", "marker")
    (bad_dir / GC_MARKER_FILENAME).write_text("not valid json{")

    good_dir = _make_module(modules_dir, "test", "hello")
    _write_marker(good_dir, "test/hello")

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=None)

    assert summary["scanned"] == 2
    assert summary["purged"] == ["test/hello"]
    assert len(summary["errors"]) == 1
    assert not good_dir.exists()


def test_sweep_no_markers_returns_empty_summary(modules_dir, artifacts_dir):
    _make_module(modules_dir, "test", "hello")  # no marker written

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=None)

    assert summary == {"scanned": 0, "purged": [], "protected": [], "errors": []}


def test_sweep_missing_modules_dir_returns_empty_summary(tmp_path, artifacts_dir):
    missing = tmp_path / "does_not_exist"

    summary = sweep_gc_pending(missing, artifacts_dir, version_manager=None)

    assert summary == {"scanned": 0, "purged": [], "protected": [], "errors": []}


def test_sweep_grace_seconds_skips_recent_markers(modules_dir, artifacts_dir):
    module_dir = _make_module(modules_dir, "test", "hello")
    recent = datetime.now(timezone.utc).isoformat()
    _write_marker(module_dir, "test/hello", rejected_at=recent)

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=None, grace_seconds=3600)

    assert summary["scanned"] == 1
    assert summary["purged"] == []
    assert summary["protected"] == []
    assert module_dir.exists()


def test_sweep_grace_seconds_purges_old_markers(modules_dir, artifacts_dir):
    module_dir = _make_module(modules_dir, "test", "hello")
    old = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _write_marker(module_dir, "test/hello", rejected_at=old)

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=None, grace_seconds=3600)

    assert summary["purged"] == ["test/hello"]
    assert not module_dir.exists()


# ── real VersionManager signature check ─────────────────────────────


def test_sweep_with_real_version_manager(tmp_path, modules_dir, artifacts_dir):
    vm = VersionManager(db_path=str(tmp_path / "v.db"))

    # Module with a recorded, active version — protected.
    protected_dir = _make_module(modules_dir, "weather", "openweather")
    _write_marker(protected_dir, "weather/openweather")
    vm.record_version(
        module_id="weather/openweather",
        bundle_sha256="abc123",
        actor="builder",
    )

    # Module with no version rows — purged unconditionally.
    purge_dir = _make_module(modules_dir, "test", "hello")
    _write_marker(purge_dir, "test/hello")

    summary = sweep_gc_pending(modules_dir, artifacts_dir, version_manager=vm)

    assert summary["protected"] == ["weather/openweather"]
    assert summary["purged"] == ["test/hello"]
    assert protected_dir.exists()
    assert not purge_dir.exists()


def test_queue_for_gc_still_works_unchanged(modules_dir):
    module_dir = modules_dir / "test" / "hello"
    module_dir.mkdir(parents=True)

    marker_path = queue_for_gc("test/hello", modules_dir, actor="reviewer")

    assert marker_path is not None
    assert marker_path.exists()
    data = json.loads(marker_path.read_text())
    assert data["module_id"] == "test/hello"
    assert data["actor"] == "reviewer"
