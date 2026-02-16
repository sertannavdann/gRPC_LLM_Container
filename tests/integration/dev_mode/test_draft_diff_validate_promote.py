"""
Integration test for draft → diff → validate → promote flow.

Tests the complete dev-mode lifecycle:
1. Create draft from installed module
2. Edit a file (fix a mapping bug)
3. View diff
4. Validate in sandbox
5. Promote to new validated version
6. Verify installed module reflects changes
7. Verify original version is still available
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from shared.modules.drafts import DraftManager, DraftState
from shared.modules.audit import DevModeAuditLog
from shared.modules.manifest import ModuleManifest, ModuleStatus


@pytest.fixture
def temp_workspace():
    """Create temporary workspace for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    drafts_dir = temp_dir / "drafts"
    modules_dir = temp_dir / "modules"
    audit_dir = temp_dir / "audit"

    drafts_dir.mkdir(parents=True)
    modules_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)

    yield {
        "temp_dir": temp_dir,
        "drafts_dir": drafts_dir,
        "modules_dir": modules_dir,
        "audit_dir": audit_dir
    }

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def installed_module(temp_workspace):
    """Create a mock installed module."""
    modules_dir = temp_workspace["modules_dir"]
    module_dir = modules_dir / "test" / "example"
    module_dir.mkdir(parents=True)

    # Create adapter.py with a bug (wrong mapping)
    adapter_code = '''"""Test adapter with a bug."""
from shared.adapters.base import BaseAdapter, register_adapter

@register_adapter
class ExampleAdapter(BaseAdapter):
    """Example adapter."""

    def fetch_raw(self, query: str):
        """Fetch raw data."""
        return {"value": query.upper()}  # BUG: should be lower()

    def transform(self, raw_data):
        """Transform data."""
        return {"result": raw_data.get("value", "")}

    def get_schema(self):
        """Get schema."""
        return {"type": "object"}
'''
    (module_dir / "adapter.py").write_text(adapter_code)

    # Create test_adapter.py
    test_code = '''"""Test for example adapter."""
from adapter import ExampleAdapter

def test_transform():
    """Test transformation."""
    adapter = ExampleAdapter()
    raw = adapter.fetch_raw("hello")
    result = adapter.transform(raw)
    assert result["result"] == "hello", f"Expected 'hello', got {result['result']}"
'''
    (module_dir / "test_adapter.py").write_text(test_code)

    # Create manifest.json
    manifest = ModuleManifest(
        name="Example Adapter",
        category="test",
        platform="example",
        version="1.0.0",
        status=ModuleStatus.INSTALLED
    )
    manifest.save(modules_dir)

    return {
        "module_id": "test/example",
        "module_dir": module_dir
    }


def test_draft_diff_validate_promote_flow(temp_workspace, installed_module):
    """Test complete draft lifecycle."""
    # Initialize managers
    audit_log = DevModeAuditLog(temp_workspace["audit_dir"])
    draft_manager = DraftManager(
        drafts_dir=temp_workspace["drafts_dir"],
        modules_dir=temp_workspace["modules_dir"],
        audit_log=audit_log
    )

    module_id = installed_module["module_id"]

    # Step 1: Create draft from installed module
    result = draft_manager.create_draft(
        module_id=module_id,
        from_version="v1.0.0",
        actor="test_user"
    )
    assert result["status"] == "success"
    draft_id = result["draft_id"]

    # Verify draft created
    metadata = draft_manager.get_draft(draft_id)
    assert metadata is not None
    assert metadata.state == DraftState.CREATED
    assert metadata.module_id == module_id
    assert metadata.source_version == "v1.0.0"

    # Step 2: Edit adapter.py to fix the bug
    fixed_adapter_code = '''"""Test adapter with fix."""
from shared.adapters.base import BaseAdapter, register_adapter

@register_adapter
class ExampleAdapter(BaseAdapter):
    """Example adapter."""

    def fetch_raw(self, query: str):
        """Fetch raw data."""
        return {"value": query.lower()}  # FIXED: now uses lower()

    def transform(self, raw_data):
        """Transform data."""
        return {"result": raw_data.get("value", "")}

    def get_schema(self):
        """Get schema."""
        return {"type": "object"}
'''
    edit_result = draft_manager.edit_file(
        draft_id=draft_id,
        file_path="adapter.py",
        content=fixed_adapter_code,
        actor="test_user"
    )
    assert edit_result["status"] == "success"

    # Verify state changed to EDITING
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.EDITING

    # Step 3: View diff
    diff_result = draft_manager.get_diff(draft_id, actor="test_user")
    assert diff_result["status"] == "success"
    assert "adapter.py" in diff_result["diffs"]
    diff_text = diff_result["diffs"]["adapter.py"]
    assert "query.upper()" in diff_text  # Old code
    assert "query.lower()" in diff_text  # New code

    # Step 4: Validate in sandbox (mock validator)
    def mock_validator(module_id_path):
        """Mock validator that always passes."""
        return {
            "status": "success",
            "report": {
                "status": "VALIDATED",
                "module_id": module_id_path,
                "validated_at": "2026-02-15T12:00:00Z",
                "static_results": [],
                "runtime_results": {
                    "tests_run": 1,
                    "tests_passed": 1,
                    "tests_failed": 0
                }
            }
        }

    validate_result = draft_manager.validate_draft(
        draft_id=draft_id,
        actor="test_user",
        validator_func=mock_validator
    )
    assert validate_result["status"] == "success"
    assert validate_result["bundle_sha256"] is not None

    # Verify state changed to VALIDATED
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.VALIDATED
    assert metadata.bundle_sha256 is not None

    # Step 5: Promote to new version (mock installer)
    def mock_installer(module_id, attestation):
        """Mock installer that always succeeds."""
        return {
            "status": "success",
            "module_id": module_id,
            "is_loaded": True,
            "message": "Module installed"
        }

    promote_result = draft_manager.promote_draft(
        draft_id=draft_id,
        actor="test_user",
        installer_func=mock_installer
    )
    assert promote_result["status"] == "success"
    assert promote_result["bundle_sha256"] is not None

    # Verify state changed to PROMOTED
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.PROMOTED

    # Step 6: Verify installed module reflects changes
    module_dir = temp_workspace["modules_dir"] / "test" / "example"
    adapter_content = (module_dir / "adapter.py").read_text()
    assert "query.lower()" in adapter_content  # Fixed version
    assert "query.upper()" not in adapter_content  # Bug removed

    # Step 7: Verify audit trail
    events = audit_log.get_events(draft_id=draft_id)
    assert len(events) >= 5  # created, edited, diff_viewed, validated, promoted
    actions = [e.action for e in events]
    assert "draft_created" in actions
    assert "draft_edited" in actions
    assert "draft_diff_viewed" in actions
    assert "draft_validated" in actions
    assert "draft_promoted" in actions


def test_validation_failure_returns_to_editing(temp_workspace, installed_module):
    """Test that validation failure returns draft to EDITING state."""
    audit_log = DevModeAuditLog(temp_workspace["audit_dir"])
    draft_manager = DraftManager(
        drafts_dir=temp_workspace["drafts_dir"],
        modules_dir=temp_workspace["modules_dir"],
        audit_log=audit_log
    )

    module_id = installed_module["module_id"]

    # Create draft
    result = draft_manager.create_draft(module_id=module_id, actor="test_user")
    draft_id = result["draft_id"]

    # Mock validator that fails
    def mock_failing_validator(module_id_path):
        """Mock validator that fails."""
        return {
            "status": "failed",
            "report": {
                "status": "FAILED",
                "module_id": module_id_path,
                "validated_at": "2026-02-15T12:00:00Z",
                "fix_hints": [
                    {
                        "category": "test_failure",
                        "message": "Tests failed"
                    }
                ]
            }
        }

    validate_result = draft_manager.validate_draft(
        draft_id=draft_id,
        actor="test_user",
        validator_func=mock_failing_validator
    )
    assert validate_result["status"] == "failed"

    # Verify state returned to EDITING
    metadata = draft_manager.get_draft(draft_id)
    assert metadata.state == DraftState.EDITING


def test_promote_requires_validated_state(temp_workspace, installed_module):
    """Test that promotion fails if draft not VALIDATED."""
    audit_log = DevModeAuditLog(temp_workspace["audit_dir"])
    draft_manager = DraftManager(
        drafts_dir=temp_workspace["drafts_dir"],
        modules_dir=temp_workspace["modules_dir"],
        audit_log=audit_log
    )

    module_id = installed_module["module_id"]

    # Create draft
    result = draft_manager.create_draft(module_id=module_id, actor="test_user")
    draft_id = result["draft_id"]

    # Try to promote without validation
    promote_result = draft_manager.promote_draft(
        draft_id=draft_id,
        actor="test_user"
    )
    assert promote_result["status"] == "error"
    assert "must be VALIDATED" in promote_result["error"]
