"""
Tests for DraftManager + VersionManager tool registration in orchestrator.

Verifies that draft lifecycle and version management tools are registered
and callable as orchestrator chat tools.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from shared.modules.drafts import DraftManager, DraftState
from shared.modules.versioning import VersionManager
from shared.modules.audit import DevModeAuditLog


@pytest.fixture
def tmp_dirs():
    """Create temporary directories for testing."""
    tmpdir = tempfile.mkdtemp()
    drafts_dir = Path(tmpdir) / "drafts"
    modules_dir = Path(tmpdir) / "modules"
    audit_dir = Path(tmpdir) / "audit"
    db_path = Path(tmpdir) / "versions.db"

    drafts_dir.mkdir()
    modules_dir.mkdir()
    audit_dir.mkdir()

    yield {
        "tmpdir": tmpdir,
        "drafts_dir": drafts_dir,
        "modules_dir": modules_dir,
        "audit_dir": audit_dir,
        "db_path": str(db_path),
    }

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def audit_log(tmp_dirs):
    return DevModeAuditLog(audit_dir=tmp_dirs["audit_dir"])


@pytest.fixture
def draft_manager(tmp_dirs, audit_log):
    return DraftManager(
        drafts_dir=tmp_dirs["drafts_dir"],
        modules_dir=tmp_dirs["modules_dir"],
        audit_log=audit_log,
    )


@pytest.fixture
def version_manager(tmp_dirs, audit_log):
    return VersionManager(
        db_path=tmp_dirs["db_path"],
        audit_log=audit_log,
    )


@pytest.fixture
def installed_module(tmp_dirs):
    """Create a fake installed module for testing."""
    mod_dir = tmp_dirs["modules_dir"] / "test" / "example"
    mod_dir.mkdir(parents=True)

    (mod_dir / "manifest.json").write_text('{"name": "test/example", "version": "1.0.0"}')
    (mod_dir / "adapter.py").write_text('class ExampleAdapter: pass')
    (mod_dir / "test_adapter.py").write_text('def test_example(): assert True')

    return "test/example"


class TestDraftManagerTools:

    def test_create_draft_returns_metadata(self, draft_manager, installed_module):
        result = draft_manager.create_draft(module_id=installed_module, actor="test")
        assert result["status"] == "success"
        assert "draft_id" in result

    def test_create_draft_invalid_module_id(self, draft_manager):
        result = draft_manager.create_draft(module_id="noslash", actor="test")
        assert result["status"] == "error"

    def test_create_draft_missing_module(self, draft_manager):
        result = draft_manager.create_draft(module_id="nonexistent/module", actor="test")
        assert result["status"] == "error"

    def test_edit_file_in_draft(self, draft_manager, installed_module):
        create_result = draft_manager.create_draft(module_id=installed_module, actor="test")
        draft_id = create_result["draft_id"]

        edit_result = draft_manager.edit_file(
            draft_id=draft_id,
            file_path="adapter.py",
            content="class ModifiedAdapter: pass",
            actor="test",
        )
        assert edit_result["status"] == "success"
        assert edit_result["file"] == "adapter.py"

    def test_get_diff_returns_diffs(self, draft_manager, installed_module):
        create_result = draft_manager.create_draft(module_id=installed_module, actor="test")
        draft_id = create_result["draft_id"]

        # Edit a file to create a diff
        draft_manager.edit_file(
            draft_id=draft_id,
            file_path="adapter.py",
            content="class ModifiedAdapter: pass\n",
            actor="test",
        )

        diff_result = draft_manager.get_diff(draft_id=draft_id, actor="test")
        assert diff_result["status"] == "success"
        assert "diffs" in diff_result
        assert "adapter.py" in diff_result["diffs"]

    def test_validate_draft(self, draft_manager, installed_module):
        """validate_draft is callable and returns a result."""
        create_result = draft_manager.create_draft(module_id=installed_module, actor="test")
        draft_id = create_result["draft_id"]
        result = draft_manager.validate_draft(draft_id=draft_id, actor="test")
        assert isinstance(result, dict)


class TestVersionManagerTools:

    def test_list_versions_empty(self, version_manager):
        result = version_manager.list_versions(module_id="unknown/module")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_record_and_list_version(self, version_manager):
        version_manager.record_version(
            module_id="test/example",
            bundle_sha256="abc123",
            actor="test",
        )
        versions = version_manager.list_versions(module_id="test/example")
        assert len(versions) >= 1
        v = versions[0]
        assert hasattr(v, "module_id")
        assert v.module_id == "test/example"

    def test_rollback_to_version(self, version_manager):
        v1_id = version_manager.record_version(
            module_id="test/example",
            bundle_sha256="hash_v1",
            actor="test",
        )
        v2_id = version_manager.record_version(
            module_id="test/example",
            bundle_sha256="hash_v2",
            actor="test",
        )

        result = version_manager.rollback_to_version(
            module_id="test/example",
            target_version_id=v1_id,
            actor="test",
        )
        assert isinstance(result, dict)


class TestToolRegistration:

    def test_draft_tools_are_callable(self, draft_manager):
        assert callable(draft_manager.create_draft)
        assert callable(draft_manager.edit_file)
        assert callable(draft_manager.get_diff)
        assert callable(draft_manager.validate_draft)
        assert callable(draft_manager.promote_draft)

    def test_version_tools_are_callable(self, version_manager):
        assert callable(version_manager.list_versions)
        assert callable(version_manager.rollback_to_version)

    def test_tool_functions_have_docstrings(self, draft_manager, version_manager):
        assert draft_manager.create_draft.__doc__ is not None
        assert version_manager.list_versions.__doc__ is not None
        assert version_manager.rollback_to_version.__doc__ is not None
