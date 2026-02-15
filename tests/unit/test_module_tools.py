"""
Unit tests for module lifecycle tools (build, write, validate, install).

Tests the self-correction pipeline: build → write → validate → fix → install.
All filesystem operations use temp directories; sandbox is mocked.
"""

import json
import os
import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Dict, Any

from shared.modules.manifest import ModuleManifest, ModuleStatus, ValidationResults
from shared.modules.templates.adapter_template import generate_adapter_code
from shared.modules.templates.test_template import generate_test_code


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def modules_dir(tmp_path):
    """Provide a temp modules directory and patch MODULES_DIR everywhere."""
    with patch("tools.builtin.module_builder.MODULES_DIR", tmp_path), \
         patch("tools.builtin.module_validator.MODULES_DIR", tmp_path), \
         patch("tools.builtin.module_installer.MODULES_DIR", tmp_path):
        yield tmp_path


@pytest.fixture()
def _reset_installer():
    """Reset installer globals before each test."""
    import tools.builtin.module_installer as inst
    old = (inst._module_loader, inst._module_registry, inst._credential_store)
    inst._module_loader = None
    inst._module_registry = None
    inst._credential_store = None
    yield
    inst._module_loader, inst._module_registry, inst._credential_store = old


@pytest.fixture()
def mock_loader():
    """Mock ModuleLoader that pretends to load successfully."""
    loader = MagicMock()
    handle = MagicMock()
    handle.is_loaded = True
    handle.error = None
    loader.load_module.return_value = handle
    return loader


@pytest.fixture()
def mock_registry():
    return MagicMock()


@pytest.fixture()
def mock_cred_store():
    store = MagicMock()
    store.has_credentials.return_value = False
    return store


# ---------------------------------------------------------------------------
# build_module
# ---------------------------------------------------------------------------

class TestBuildModule:
    """Tests for build_module() tool."""

    def test_creates_files(self, modules_dir):
        from tools.builtin.module_builder import build_module

        result = build_module(
            name="weather",
            category="weather",
            platform="openmeteo",
            description="Open-Meteo weather API",
            api_base_url="https://api.open-meteo.com/v1",
            requires_api_key=False,
        )

        assert result["status"] == "success"
        assert result["module_id"] == "weather/openmeteo"
        mod_dir = modules_dir / "weather" / "openmeteo"
        assert (mod_dir / "manifest.json").exists()
        assert (mod_dir / "adapter.py").exists()
        assert (mod_dir / "test_adapter.py").exists()

    def test_returns_adapter_code(self, modules_dir):
        from tools.builtin.module_builder import build_module

        result = build_module(name="demo", category="test")

        assert "adapter_code" in result
        assert "class" in result["adapter_code"]
        assert "fetch_raw" in result["adapter_code"]
        assert "transform" in result["adapter_code"]

    def test_duplicate_module_rejected(self, modules_dir):
        from tools.builtin.module_builder import build_module

        build_module(name="dup", category="test")
        result = build_module(name="dup", category="test")

        assert result["status"] == "error"
        assert "already exists" in result["error"]

    def test_manifest_status_is_pending(self, modules_dir):
        from tools.builtin.module_builder import build_module

        build_module(name="pending_check", category="test")
        manifest = ModuleManifest.load(
            modules_dir / "test" / "pending_check" / "manifest.json"
        )
        assert manifest.status == ModuleStatus.PENDING.value


# ---------------------------------------------------------------------------
# write_module_code
# ---------------------------------------------------------------------------

class TestWriteModuleCode:
    """Tests for write_module_code() tool."""

    def test_writes_adapter(self, modules_dir):
        from tools.builtin.module_builder import build_module, write_module_code

        build_module(name="wrtest", category="test")
        new_code = (modules_dir / "test" / "wrtest" / "adapter.py").read_text()
        new_code += "\n# modified\n"

        result = write_module_code("test/wrtest", new_code)

        assert result["status"] == "success"
        assert "# modified" in (modules_dir / "test" / "wrtest" / "adapter.py").read_text()

    def test_rejects_syntax_error(self, modules_dir):
        from tools.builtin.module_builder import build_module, write_module_code

        build_module(name="syntest", category="test")
        result = write_module_code("test/syntest", "def broken(:\n  pass")

        assert result["status"] == "error"
        assert "Syntax error" in result["error"]

    def test_resets_status_to_pending(self, modules_dir):
        from tools.builtin.module_builder import build_module, write_module_code

        build_module(name="statusreset", category="test")
        code = (modules_dir / "test" / "statusreset" / "adapter.py").read_text()
        write_module_code("test/statusreset", code)

        manifest = ModuleManifest.load(
            modules_dir / "test" / "statusreset" / "manifest.json"
        )
        assert manifest.status == ModuleStatus.PENDING.value

    def test_invalid_module_id(self, modules_dir):
        from tools.builtin.module_builder import write_module_code

        result = write_module_code("bad-id", "pass")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# validate_module
# ---------------------------------------------------------------------------

class TestValidateModule:
    """Tests for validate_module() tool."""

    def test_valid_module_passes(self, modules_dir):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module

        build_module(
            name="valpass", category="test",
            api_base_url="https://example.com",
            requires_api_key=True,
        )
        result = validate_module("test/valpass")

        assert result["status"] == "success"
        assert result["validation"]["syntax_check"] == "pass"
        assert result["errors"] is None

    def test_missing_method_detected(self, modules_dir):
        from tools.builtin.module_builder import build_module, write_module_code
        from tools.builtin.module_validator import validate_module

        build_module(name="nomethod", category="test")

        # Write adapter that's missing fetch_raw and transform
        bad_code = '''\
from shared.adapters.base import BaseAdapter
from shared.adapters.registry import register_adapter

@register_adapter(category="test", platform="nomethod", display_name="No Method", icon="🔌")
class NomethodAdapter(BaseAdapter):
    pass
'''
        write_module_code("test/nomethod", bad_code)
        result = validate_module("test/nomethod")

        assert result["status"] == "failed"
        assert any("Missing required method: fetch_raw" in e for e in result["errors"])
        assert any("Missing required method: transform" in e for e in result["errors"])

    def test_missing_decorator_detected(self, modules_dir):
        from tools.builtin.module_builder import build_module, write_module_code
        from tools.builtin.module_validator import validate_module

        build_module(name="nodec", category="test")

        bad_code = '''\
from shared.adapters.base import BaseAdapter

class NodecAdapter(BaseAdapter):
    async def fetch_raw(self, config):
        return {}
    def transform(self, raw_data):
        return []
'''
        write_module_code("test/nodec", bad_code)
        result = validate_module("test/nodec")

        assert result["status"] == "failed"
        assert any("Missing @register_adapter" in e for e in result["errors"])

    def test_syntax_error_detected(self, modules_dir):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module

        build_module(name="synval", category="test")
        # Force a syntax error by writing directly
        (modules_dir / "test" / "synval" / "adapter.py").write_text("def broken(:\n  pass")

        result = validate_module("test/synval")

        assert result["status"] == "failed"
        assert any("Syntax error" in e for e in result["errors"])

    def test_fix_hints_present_on_failure(self, modules_dir):
        from tools.builtin.module_builder import build_module, write_module_code
        from tools.builtin.module_validator import validate_module

        build_module(name="hints", category="test")
        bad_code = '''\
from shared.adapters.base import BaseAdapter
from shared.adapters.registry import register_adapter

@register_adapter(category="test", platform="hints", display_name="Hints", icon="🔌")
class HintsAdapter(BaseAdapter):
    pass
'''
        write_module_code("test/hints", bad_code)
        result = validate_module("test/hints")

        assert result["status"] == "failed"
        assert result["fix_hints"] is not None
        assert len(result["fix_hints"]) > 0
        # Check that at least one hint has a type and suggestion
        types = {h["type"] for h in result["fix_hints"]}
        assert "missing_method" in types

    def test_fix_hints_none_on_success(self, modules_dir):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module

        build_module(name="hintsok", category="test")
        result = validate_module("test/hintsok")

        assert result["status"] == "success"
        assert result["fix_hints"] is None

    def test_manifest_updated_to_validated(self, modules_dir):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module

        build_module(name="mstatus", category="test")
        validate_module("test/mstatus")

        manifest = ModuleManifest.load(
            modules_dir / "test" / "mstatus" / "manifest.json"
        )
        assert manifest.status == ModuleStatus.VALIDATED.value

    def test_manifest_updated_to_failed(self, modules_dir):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module

        build_module(name="mfail", category="test")
        (modules_dir / "test" / "mfail" / "adapter.py").write_text("def bad(:\n  pass")
        validate_module("test/mfail")

        manifest = ModuleManifest.load(
            modules_dir / "test" / "mfail" / "manifest.json"
        )
        assert manifest.status == ModuleStatus.FAILED.value


# ---------------------------------------------------------------------------
# install_module
# ---------------------------------------------------------------------------

class TestInstallModule:
    """Tests for install_module() tool."""

    def test_install_validated_module(
        self, modules_dir, _reset_installer, mock_loader, mock_registry, mock_cred_store,
    ):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module
        from tools.builtin.module_installer import install_module, set_installer_deps

        set_installer_deps(mock_loader, mock_registry, mock_cred_store)
        build_module(name="inst", category="test", requires_api_key=False)
        validate_module("test/inst")

        result = install_module("test/inst")

        assert result["status"] == "success"
        assert result["is_loaded"] is True
        mock_loader.load_module.assert_called_once()
        mock_registry.install.assert_called_once()

    def test_rejects_failed_module(
        self, modules_dir, _reset_installer, mock_loader,
    ):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module
        from tools.builtin.module_installer import install_module, set_installer_deps

        set_installer_deps(mock_loader, MagicMock(), MagicMock())
        build_module(name="fail_inst", category="test")
        # Force failure
        (modules_dir / "test" / "fail_inst" / "adapter.py").write_text("def bad(:\n  pass")
        validate_module("test/fail_inst")

        result = install_module("test/fail_inst")

        assert result["status"] == "error"
        assert "failed validation" in result["error"]
        mock_loader.load_module.assert_not_called()

    def test_rejects_pending_module(
        self, modules_dir, _reset_installer, mock_loader,
    ):
        """Verify the new VALIDATED guard rejects PENDING modules."""
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_installer import install_module, set_installer_deps

        set_installer_deps(mock_loader, MagicMock(), MagicMock())
        build_module(name="pend_inst", category="test")
        # Don't validate — status is PENDING

        result = install_module("test/pend_inst")

        assert result["status"] == "error"
        assert "not been validated" in result["error"]
        mock_loader.load_module.assert_not_called()

    def test_install_without_loader(self, modules_dir, _reset_installer):
        from tools.builtin.module_builder import build_module
        from tools.builtin.module_validator import validate_module
        from tools.builtin.module_installer import install_module

        build_module(name="noloader", category="test")
        validate_module("test/noloader")

        result = install_module("test/noloader")

        assert result["status"] == "error"
        assert "loader not available" in result["error"]


# ---------------------------------------------------------------------------
# Self-correction pipeline (end-to-end unit-level)
# ---------------------------------------------------------------------------

class TestSelfCorrectionPipeline:
    """Test the build → write → validate → fix → validate → install cycle."""

    def test_build_fix_install_cycle(
        self, modules_dir, _reset_installer, mock_loader, mock_registry, mock_cred_store,
    ):
        from tools.builtin.module_builder import build_module, write_module_code
        from tools.builtin.module_validator import validate_module
        from tools.builtin.module_installer import install_module, set_installer_deps

        set_installer_deps(mock_loader, mock_registry, mock_cred_store)

        # Step 1: build
        r = build_module(
            name="selfcorr", category="test",
            api_base_url="https://api.example.com",
            requires_api_key=True,
        )
        assert r["status"] == "success"
        module_id = r["module_id"]

        # Step 2: write deliberately broken code
        broken = '''\
from shared.adapters.base import BaseAdapter
from shared.adapters.registry import register_adapter

@register_adapter(category="test", platform="selfcorr", display_name="Self Corr", icon="🔌")
class SelfcorrAdapter(BaseAdapter):
    pass
'''
        wr = write_module_code(module_id, broken)
        assert wr["status"] == "success"

        # Step 3: validate — should fail (missing methods)
        v1 = validate_module(module_id)
        assert v1["status"] == "failed"
        assert v1["fix_hints"] is not None
        assert any(h["type"] == "missing_method" for h in v1["fix_hints"])

        # Step 4: fix — use the skeleton from build (which has correct methods)
        fixed_code = r["adapter_code"]
        wr2 = write_module_code(module_id, fixed_code)
        assert wr2["status"] == "success"

        # Step 5: re-validate — should pass now
        v2 = validate_module(module_id)
        assert v2["status"] == "success"
        assert v2["fix_hints"] is None

        # Step 6: install
        inst = install_module(module_id)
        assert inst["status"] == "success"
        assert inst["is_loaded"] is True


# ---------------------------------------------------------------------------
# Graph integration — system prompt + iteration budget
# ---------------------------------------------------------------------------

class TestGraphModuleBuildSupport:
    """Tests for module-build awareness in the AgentWorkflow graph."""

    def test_is_module_build_intent(self):
        from core.graph import AgentWorkflow

        assert AgentWorkflow._is_module_build_intent("Build me a weather module")
        assert AgentWorkflow._is_module_build_intent("Create a module for Clash Royale")
        assert AgentWorkflow._is_module_build_intent("add integration for spotify")
        assert not AgentWorkflow._is_module_build_intent("What is the weather?")
        assert not AgentWorkflow._is_module_build_intent("Hello!")

    def test_effective_max_iterations_default(self):
        from core.graph import AgentWorkflow
        from core.state import WorkflowConfig

        config = WorkflowConfig()
        wf = AgentWorkflow(
            tool_registry=MagicMock(),
            llm_engine=MagicMock(),
            config=config,
        )
        state = {"tool_results": [], "retry_count": 0}
        assert wf._get_effective_max_iterations(state) == 5

    def test_effective_max_iterations_module_build(self):
        from core.graph import AgentWorkflow
        from core.state import WorkflowConfig

        config = WorkflowConfig()
        wf = AgentWorkflow(
            tool_registry=MagicMock(),
            llm_engine=MagicMock(),
            config=config,
        )
        state = {
            "tool_results": [{"tool_name": "build_module"}],
            "retry_count": 0,
        }
        assert wf._get_effective_max_iterations(state) == 10

    def test_module_build_max_iterations_config(self):
        from core.state import WorkflowConfig

        config = WorkflowConfig(module_build_max_iterations=15)
        assert config.module_build_max_iterations == 15
        assert config.max_iterations == 5  # default unchanged
