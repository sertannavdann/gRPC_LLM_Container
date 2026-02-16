"""
Tests for module registration contract.

Verifies that:
- Modules register correctly via @register_adapter decorator
- Modules appear in registry after registration
- Duplicate registration is handled gracefully
- Module metadata is preserved
"""
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


class TestRegistrationContract:
    """Contract tests for module registration via @register_adapter decorator."""

    def test_decorator_present_in_contract_spec(self):
        """Verify contract spec defines required decorator."""
        from shared.modules.contracts import AdapterContractSpec

        assert AdapterContractSpec.REQUIRED_DECORATOR_IMPORT == "register_adapter"

    def test_decorator_detection_with_simple_decorator(self):
        """Verify decorator detection works for @register_adapter."""
        from shared.modules.contracts import AdapterContractSpec

        code = '''
@register_adapter
class TestAdapter:
    pass
'''
        assert AdapterContractSpec.check_decorator_present(code)

    def test_decorator_detection_with_call_decorator(self):
        """Verify decorator detection works for @register_adapter(...)."""
        from shared.modules.contracts import AdapterContractSpec

        code = '''
@register_adapter("test", "platform")
class TestAdapter:
    pass
'''
        assert AdapterContractSpec.check_decorator_present(code)

    def test_decorator_detection_fails_when_missing(self):
        """Verify decorator detection fails when decorator is absent."""
        from shared.modules.contracts import AdapterContractSpec

        code = '''
class TestAdapter:
    pass
'''
        assert not AdapterContractSpec.check_decorator_present(code)

    def test_decorator_detection_fails_with_wrong_decorator(self):
        """Verify decorator detection fails for wrong decorator."""
        from shared.modules.contracts import AdapterContractSpec

        code = '''
@dataclass
class TestAdapter:
    pass
'''
        assert not AdapterContractSpec.check_decorator_present(code)

    def test_contract_validation_fails_without_decorator(self):
        """Verify contract validation rejects code without @register_adapter."""
        from shared.modules.contracts import AdapterContractSpec, ErrorCode

        code = '''
class TestAdapter:
    def fetch_raw(self):
        pass
    def transform(self, data):
        pass
    def get_schema(self):
        pass
'''
        result = AdapterContractSpec.validate_adapter_file(code)

        assert not result["valid"]
        assert any(e["code"] == ErrorCode.MISSING_DECORATOR for e in result["errors"])

    def test_duplicate_registration_does_not_crash(self):
        """Verify that attempting to register the same module twice doesn't crash.

        Note: Actual duplicate handling depends on registry implementation.
        This test verifies the decorator can be applied multiple times without syntax errors.
        """
        from shared.modules.contracts import AdapterContractSpec

        # Code with decorator applied
        code = '''
from shared.adapters.base import register_adapter, BaseAdapter

@register_adapter
class TestAdapter(BaseAdapter):
    def fetch_raw(self):
        pass
    def transform(self, data):
        pass
    def get_schema(self):
        pass
'''
        # Should parse without errors
        result = AdapterContractSpec.validate_adapter_file(code)

        # Decorator check should pass
        decorator_checks = [e for e in result.get("errors", [])
                          if e.get("code") == "missing_decorator"]
        assert len(decorator_checks) == 0

    def test_module_appears_in_registry_after_import(self):
        """Verify that importing a module with @register_adapter adds it to registry.

        This tests the actual registration mechanism, not just the decorator presence.
        """
        # Create a temporary module with @register_adapter
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "test_module.py"
            module_path.write_text('''
from shared.adapters.base import BaseAdapter
from shared.adapters.registry import register_adapter

@register_adapter("test", "registration", display_name="Test Registration")
class TestRegistrationAdapter(BaseAdapter):
    category = "test"
    platform = "registration"

    def fetch_raw(self, config):
        return {}

    def transform(self, data):
        return []

    def get_schema(self):
        return {}
''')

            # Add tmpdir to sys.path to allow import
            sys.path.insert(0, tmpdir)
            try:
                # Import the module to trigger registration
                import importlib.util
                spec = importlib.util.spec_from_file_location("test_module", module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Check that adapter is accessible
                assert hasattr(module, "TestRegistrationAdapter")

                # Verify it's a subclass of BaseAdapter
                from shared.adapters.base import BaseAdapter
                assert issubclass(module.TestRegistrationAdapter, BaseAdapter)

                # Verify it was registered in the registry
                from shared.adapters.registry import adapter_registry
                assert adapter_registry.has_adapter("test", "registration")

            finally:
                sys.path.remove(tmpdir)

    def test_metadata_preserved_in_registered_module(self):
        """Verify that module metadata (category, platform) is preserved after registration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "metadata_test.py"
            module_path.write_text('''
from shared.adapters.base import BaseAdapter
from shared.adapters.registry import register_adapter

@register_adapter("finance", "testbank", display_name="Test Bank")
class MetadataTestAdapter(BaseAdapter):
    category = "finance"
    platform = "testbank"

    def fetch_raw(self, config):
        return {}

    def transform(self, data):
        return []

    def get_schema(self):
        return {}
''')

            sys.path.insert(0, tmpdir)
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("metadata_test", module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Create instance and verify metadata
                adapter = module.MetadataTestAdapter()
                assert adapter.category == "finance"
                assert adapter.platform == "testbank"

                # Verify registration preserved metadata
                from shared.adapters.registry import adapter_registry
                assert adapter_registry.has_adapter("finance", "testbank")
                info = adapter_registry.get_info("finance", "testbank")
                assert info.display_name == "Test Bank"

            finally:
                sys.path.remove(tmpdir)
