"""
Unit tests for draft lifecycle: create, edit, diff, validate, promote.

Tests the full dev-mode flow without requiring Docker services.
Uses tmp_path fixtures and mock validators/installers.
"""
import json
import pytest
from pathlib import Path
from shared.modules.drafts import DraftManager, DraftState, DraftMetadata


@pytest.fixture
def setup_test_module(tmp_path):
    """Create a test module for draft creation."""
    modules_dir = tmp_path / "modules"
    finance_cibc = modules_dir / "finance" / "cibc"
    finance_cibc.mkdir(parents=True)

    # Create adapter.py
    adapter_code = '''
"""CIBC bank adapter."""
from shared.adapters.base import BaseAdapter

class CibcAdapter(BaseAdapter):
    def fetch_raw(self):
        return {"transactions": []}

    def transform(self, raw):
        return []
'''
    (finance_cibc / "adapter.py").write_text(adapter_code)

    # Create test_adapter.py
    test_code = '''
"""Tests for CIBC adapter."""
import pytest
from adapter import CibcAdapter

def test_fetch():
    adapter = CibcAdapter()
    result = adapter.fetch_raw()
    assert result is not None
'''
    (finance_cibc / "test_adapter.py").write_text(test_code)

    # Create manifest.json
    manifest = {
        "name": "cibc",
        "category": "finance",
        "platform": "cibc",
        "version": "1.0.0"
    }
    (finance_cibc / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return {
        "modules_dir": modules_dir,
        "module_id": "finance/cibc",
        "module_dir": finance_cibc
    }


@pytest.fixture
def draft_manager(tmp_path, setup_test_module):
    """Create DraftManager with test directories."""
    drafts_dir = tmp_path / "drafts"
    modules_dir = setup_test_module["modules_dir"]
    return DraftManager(
        drafts_dir=drafts_dir,
        modules_dir=modules_dir,
        audit_log=None  # No audit for unit tests
    )


def test_create_draft(draft_manager, setup_test_module):
    """Test creating a draft from installed module."""
    result = draft_manager.create_draft(
        module_id="finance/cibc",
        from_version="v1.0.0",
        actor="test_user"
    )

    assert result["status"] == "success"
    assert "draft_id" in result
    assert result["module_id"] == "finance/cibc"
    assert result["source_version"] == "v1.0.0"
    assert "adapter.py" in result["files"]
    assert "test_adapter.py" in result["files"]
    assert "manifest.json" in result["files"]

    # Verify draft metadata
    draft_id = result["draft_id"]
    metadata = draft_manager.get_draft(draft_id)
    assert metadata is not None
    assert metadata.module_id == "finance/cibc"
    assert metadata.source_version == "v1.0.0"
    assert metadata.state == DraftState.CREATED
    assert metadata.created_by == "test_user"


def test_create_draft_from_missing_module(draft_manager):
    """Test creating draft from non-existent module fails."""
    result = draft_manager.create_draft(
        module_id="missing/module",
        from_version="v1.0.0"
    )

    assert result["status"] == "error"
    assert "not found" in result["error"].lower()


def test_edit_draft_file(draft_manager):
    """Test editing a file in a draft."""
    # Create draft
    create_result = draft_manager.create_draft(
        module_id="finance/cibc",
        from_version="v1.0.0",
        actor="test_user"
    )
    draft_id = create_result["draft_id"]

    # Edit adapter.py
    new_code = '''
"""Updated CIBC adapter with fix."""
from shared.adapters.base import BaseAdapter

class CibcAdapter(BaseAdapter):
    def fetch_raw(self):
        return {"transactions": [], "account": "123"}  # Added account field

    def transform(self, raw):
        return raw.get("transactions", [])
'''
    edit_result = draft_manager.edit_file(
        draft_id=draft_id,
        file_path="adapter.py",
        content=new_code,
        actor="test_user"
    )

    assert edit_result["status"] == "success"
    assert edit_result["file"] == "adapter.py"
    assert "file_hash" in edit_result

    # Verify metadata updated
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.EDITING
    assert "adapter.py" in metadata.files


def test_edit_promoted_draft_fails(draft_manager):
    """Test that promoted drafts cannot be edited."""
    # Create draft
    create_result = draft_manager.create_draft(
        module_id="finance/cibc",
        from_version="v1.0.0"
    )
    draft_id = create_result["draft_id"]

    # Manually promote it
    draft_dir = draft_manager.drafts_dir / draft_id
    metadata_file = draft_dir / "metadata.json"
    metadata = DraftMetadata.from_dict(json.loads(metadata_file.read_text()))
    metadata.state = DraftState.PROMOTED
    metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

    # Try to edit
    result = draft_manager.edit_file(
        draft_id=draft_id,
        file_path="adapter.py",
        content="new code"
    )

    assert result["status"] == "error"
    assert "cannot edit" in result["error"].lower()


def test_get_diff(draft_manager):
    """Test generating diff between draft and source."""
    # Create draft
    create_result = draft_manager.create_draft(
        module_id="finance/cibc",
        from_version="v1.0.0"
    )
    draft_id = create_result["draft_id"]

    # Edit file
    new_code = '''
"""Updated adapter."""
from shared.adapters.base import BaseAdapter

class CibcAdapter(BaseAdapter):
    def fetch_raw(self):
        return {"transactions": [], "fixed": True}  # Added fix

    def transform(self, raw):
        return raw.get("transactions", [])
'''
    draft_manager.edit_file(draft_id, "adapter.py", new_code)

    # Get diff
    diff_result = draft_manager.get_diff(draft_id)

    assert diff_result["status"] == "success"
    assert "diffs" in diff_result
    assert "adapter.py" in diff_result["diffs"]

    # Verify diff contains changes
    adapter_diff = diff_result["diffs"]["adapter.py"]
    assert "---" in adapter_diff or "+++" in adapter_diff
    assert "fixed" in adapter_diff.lower() or "Updated adapter" in adapter_diff


def test_discard_draft(draft_manager):
    """Test discarding a draft."""
    # Create draft
    create_result = draft_manager.create_draft(
        module_id="finance/cibc",
        from_version="v1.0.0"
    )
    draft_id = create_result["draft_id"]

    # Discard
    discard_result = draft_manager.discard_draft(draft_id, actor="test_user")

    assert discard_result["status"] == "success"

    # Verify state changed
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.DISCARDED

    # Files should still exist (preserved for audit)
    draft_dir = draft_manager.drafts_dir / draft_id
    assert draft_dir.exists()
    files_dir = draft_dir / "files"
    assert (files_dir / "adapter.py").exists()


def test_list_drafts(draft_manager):
    """Test listing all drafts."""
    import time
    # Create multiple drafts
    draft1 = draft_manager.create_draft("finance/cibc", "v1.0.0")
    time.sleep(1.1)  # Ensure different timestamp for second draft
    draft2 = draft_manager.create_draft("finance/cibc", "v1.1.0")

    # List all drafts
    all_drafts = draft_manager.list_drafts()
    assert len(all_drafts) == 2

    # List filtered by module
    cibc_drafts = draft_manager.list_drafts(module_id="finance/cibc")
    assert len(cibc_drafts) == 2
    assert all(d.module_id == "finance/cibc" for d in cibc_drafts)


def test_validate_draft_success(draft_manager):
    """Test validating a draft with mock validator."""
    # Create and edit draft
    create_result = draft_manager.create_draft("finance/cibc", "v1.0.0")
    draft_id = create_result["draft_id"]

    # Mock validator that always passes
    def mock_validator(module_id):
        return {
            "status": "success",
            "report": {
                "static_results": [{"name": "syntax", "passed": True}],
                "runtime_results": {"exit_code": 0, "stdout": "All tests passed"},
                "validated_at": "2026-02-16T00:00:00Z"
            }
        }

    # Validate
    result = draft_manager.validate_draft(
        draft_id=draft_id,
        actor="test_user",
        validator_func=mock_validator
    )

    assert result["status"] == "success"
    assert "validation_report" in result
    assert "bundle_sha256" in result
    assert result["bundle_sha256"] is not None

    # Verify state changed
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.VALIDATED
    assert metadata.bundle_sha256 is not None


def test_validate_draft_failure(draft_manager):
    """Test validation failure keeps draft in editable state."""
    # Create draft
    create_result = draft_manager.create_draft("finance/cibc", "v1.0.0")
    draft_id = create_result["draft_id"]

    # Mock validator that fails
    def mock_validator(module_id):
        return {
            "status": "failed",
            "report": {
                "static_results": [{"name": "syntax", "passed": False, "error": "Syntax error"}],
                "fix_hints": [{"category": "syntax_error", "hint": "Fix syntax"}]
            }
        }

    # Validate
    result = draft_manager.validate_draft(
        draft_id=draft_id,
        validator_func=mock_validator
    )

    assert result["status"] == "failed"

    # Verify state is back to EDITING
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.EDITING


def test_promote_draft_success(draft_manager, setup_test_module):
    """Test promoting a validated draft."""
    # Create and validate draft
    create_result = draft_manager.create_draft("finance/cibc", "v1.0.0")
    draft_id = create_result["draft_id"]

    # Mock successful validation
    def mock_validator(module_id):
        return {
            "status": "success",
            "report": {"validated_at": "2026-02-16T00:00:00Z"}
        }

    draft_manager.validate_draft(draft_id, validator_func=mock_validator)

    # Mock installer
    def mock_installer(module_id, attestation):
        return {
            "status": "success",
            "module_id": module_id,
            "bundle_sha256": attestation["bundle_sha256"]
        }

    # Promote
    result = draft_manager.promote_draft(
        draft_id=draft_id,
        actor="test_user",
        installer_func=mock_installer
    )

    assert result["status"] == "success"
    assert result["module_id"] == "finance/cibc"
    assert "bundle_sha256" in result

    # Verify state changed
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.PROMOTED


def test_promote_unvalidated_draft_fails(draft_manager):
    """Test that unvalidated drafts cannot be promoted."""
    # Create draft without validation
    create_result = draft_manager.create_draft("finance/cibc", "v1.0.0")
    draft_id = create_result["draft_id"]

    # Try to promote
    result = draft_manager.promote_draft(draft_id)

    assert result["status"] == "error"
    assert "validated" in result["error"].lower()


def test_full_draft_lifecycle(draft_manager):
    """Test complete draft lifecycle: create -> edit -> diff -> validate -> promote."""
    # Step 1: Create draft
    create_result = draft_manager.create_draft(
        module_id="finance/cibc",
        from_version="v1.0.0",
        actor="developer"
    )
    assert create_result["status"] == "success"
    draft_id = create_result["draft_id"]

    # Step 2: Edit file (fix a bug)
    fixed_code = '''
"""Fixed CIBC adapter."""
from shared.adapters.base import BaseAdapter

class CibcAdapter(BaseAdapter):
    def fetch_raw(self):
        # Fixed: Added error handling
        try:
            return {"transactions": []}
        except Exception as e:
            return {"transactions": [], "error": str(e)}

    def transform(self, raw):
        return raw.get("transactions", [])
'''
    edit_result = draft_manager.edit_file(draft_id, "adapter.py", fixed_code, actor="developer")
    assert edit_result["status"] == "success"

    # Step 3: View diff
    diff_result = draft_manager.get_diff(draft_id, actor="developer")
    assert diff_result["status"] == "success"
    assert "adapter.py" in diff_result["diffs"]

    # Step 4: Validate in sandbox
    def mock_validator(module_id):
        return {
            "status": "success",
            "report": {
                "static_results": [{"name": "syntax", "passed": True}],
                "runtime_results": {"exit_code": 0},
                "validated_at": "2026-02-16T00:00:00Z"
            }
        }

    validate_result = draft_manager.validate_draft(draft_id, actor="developer", validator_func=mock_validator)
    assert validate_result["status"] == "success"
    assert validate_result["draft_state"] == "validated"

    # Step 5: Promote to new version
    def mock_installer(module_id, attestation):
        assert attestation["bundle_sha256"] is not None
        assert attestation["draft_id"] == draft_id
        return {"status": "success", "module_id": module_id}

    promote_result = draft_manager.promote_draft(draft_id, actor="developer", installer_func=mock_installer)
    assert promote_result["status"] == "success"
    assert promote_result["module_id"] == "finance/cibc"

    # Step 6: Verify final state
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.PROMOTED
    assert metadata.bundle_sha256 is not None
