"""
pytest configuration for cross-feature integration tests.

These tests verify Phase 03 components working together across boundaries.
All tests are in-process — no Docker services required.
"""
import importlib
import json
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.modules.manifest import ModuleManifest, ModuleStatus
from shared.modules.artifacts import ArtifactBundleBuilder
from shared.modules.audit import DevModeAuditLog


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "wiring_gap: Tests documenting known wiring gaps (will flip when wiring added)"
    )


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Override parent test_environment fixture."""
    yield


@pytest.fixture(scope="session", autouse=True)
def llm_warmup(test_environment):
    """Override parent llm_warmup fixture."""
    yield


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with all needed directories."""
    modules_dir = tmp_path / "modules"
    drafts_dir = tmp_path / "drafts"
    audit_dir = tmp_path / "audit"
    artifacts_dir = tmp_path / "artifacts"
    modules_dir.mkdir()
    drafts_dir.mkdir()
    audit_dir.mkdir()
    artifacts_dir.mkdir()
    return {
        "modules_dir": modules_dir,
        "drafts_dir": drafts_dir,
        "audit_dir": audit_dir,
        "artifacts_dir": artifacts_dir,
        "db_path": str(tmp_path / "module_versions.db"),
    }


@pytest.fixture
def valid_adapter_code():
    """Return syntactically valid adapter code that passes AdapterContractSpec."""
    return '''
from shared.adapters.base import BaseAdapter, register_adapter

@register_adapter
class WeatherAdapter(BaseAdapter):
    def fetch_raw(self):
        return {"temperature": 22, "unit": "celsius"}

    def transform(self, raw):
        return {"temp_f": raw["temperature"] * 9/5 + 32}

    def get_schema(self):
        return {"type": "object", "properties": {"temp_f": {"type": "number"}}}
'''


@pytest.fixture
def valid_test_code():
    """Return basic test code for an adapter."""
    return '''
def test_adapter_returns_data():
    assert True

def test_adapter_schema():
    assert True
'''


@pytest.fixture
def forbidden_import_adapter_code():
    """Return adapter code with a forbidden import."""
    return '''
import subprocess

from shared.adapters.base import BaseAdapter, register_adapter

@register_adapter
class BadAdapter(BaseAdapter):
    def fetch_raw(self):
        return subprocess.check_output(["ls"])

    def transform(self, raw):
        return raw

    def get_schema(self):
        return {"type": "object"}
'''


@pytest.fixture
def sample_manifest_dict():
    """Return a dict for manifest construction."""
    return {
        "name": "openweather",
        "category": "weather",
        "platform": "openweather",
        "auth_type": "api_key",
        "capabilities": {
            "pagination": True,
            "rate_limited": True,
        },
        "display_name": "OpenWeather",
        "status": ModuleStatus.VALIDATED.value,
    }


@pytest.fixture
def mock_loader():
    """Create mock module loader."""
    loader = MagicMock()
    handle = MagicMock()
    handle.is_loaded = True
    handle.error = None
    loader.load_module.return_value = handle
    return loader


@pytest.fixture
def mock_registry():
    """Create mock module registry."""
    return MagicMock()


def create_test_module(modules_dir, module_id, adapter_code, test_code, status):
    """
    Create a test module on disk.

    Returns:
        Tuple of (manifest, bundle_sha256)
    """
    category, platform = module_id.split("/")
    module_dir = modules_dir / category / platform
    module_dir.mkdir(parents=True, exist_ok=True)

    manifest = ModuleManifest(
        name=platform,
        category=category,
        platform=platform,
        status=status,
        display_name=platform.title(),
    )
    manifest.save(modules_dir)

    (module_dir / "adapter.py").write_text(adapter_code)
    (module_dir / "test_adapter.py").write_text(test_code)

    manifest_text = (module_dir / "manifest.json").read_text()

    bundle = ArtifactBundleBuilder.build_from_dict(
        files={
            f"{category}/{platform}/manifest.json": manifest_text,
            f"{category}/{platform}/adapter.py": adapter_code,
            f"{category}/{platform}/test_adapter.py": test_code,
        },
        job_id="test",
        attempt_id=1,
        module_id=module_id,
    )

    return manifest, bundle.bundle_sha256


@pytest.fixture
def setup_installer(mock_loader, mock_registry, temp_workspace):
    """Setup module_installer with temp dirs."""
    from tools.builtin import module_installer

    with patch.dict("os.environ", {
        "MODULES_DIR": str(temp_workspace["modules_dir"]),
        "AUDIT_DIR": str(temp_workspace["audit_dir"]),
    }):
        importlib.reload(module_installer)
        module_installer.set_installer_deps(
            loader=mock_loader,
            registry=mock_registry,
            credential_store=MagicMock(),
        )
        yield module_installer

        module_installer._module_loader = None
        module_installer._module_registry = None


@pytest.fixture
def setup_builder(temp_workspace):
    """Setup module_builder with temp dirs."""
    # Mock gRPC proto modules that aren't generated locally
    _mock_pb2 = MagicMock()
    _saved = {}
    for mod_name in ("llm_service", "llm_service.llm_pb2", "llm_service.llm_pb2_grpc"):
        _saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = _mock_pb2

    from tools.builtin import module_builder

    with patch.dict("os.environ", {
        "MODULES_DIR": str(temp_workspace["modules_dir"]),
        "AUDIT_DIR": str(temp_workspace["audit_dir"]),
    }):
        importlib.reload(module_builder)
        yield module_builder

    # Restore original sys.modules state
    for mod_name, original in _saved.items():
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original
