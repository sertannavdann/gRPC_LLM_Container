"""Unit tests for contracts.py - adapter and generator contract validation."""
import pytest
from pydantic import ValidationError
from shared.modules.contracts import (
    AdapterContractSpec,
    GeneratorResponseContract,
    FileChange,
    ErrorCode,
    validate_generator_response
)


class TestAdapterContractSpec:
    """Tests for AdapterContractSpec validation."""

    def test_forbidden_imports_detected(self):
        """Test that forbidden imports are detected."""
        code = """
import subprocess
from os import system

def run_command():
    subprocess.call(['ls'])
"""
        forbidden = AdapterContractSpec.check_forbidden_imports(code)
        assert "subprocess" in forbidden
        assert "os.system" in forbidden

    def test_eval_exec_detected(self):
        """Test that eval/exec calls are detected."""
        code = """
def bad_function():
    eval("1 + 1")
    exec("print('hello')")
"""
        forbidden = AdapterContractSpec.check_forbidden_imports(code)
        assert "eval" in forbidden
        assert "exec" in forbidden

    def test_no_forbidden_imports(self):
        """Test that safe code passes."""
        code = """
import json
from typing import Dict

def safe_function():
    return json.dumps({})
"""
        forbidden = AdapterContractSpec.check_forbidden_imports(code)
        assert len(forbidden) == 0

    def test_decorator_present_simple(self):
        """Test detection of simple decorator."""
        code = """
@register_adapter
class MyAdapter:
    pass
"""
        assert AdapterContractSpec.check_decorator_present(code) is True

    def test_decorator_present_with_args(self):
        """Test detection of decorator with arguments."""
        code = """
@register_adapter(category="weather")
class MyAdapter:
    pass
"""
        assert AdapterContractSpec.check_decorator_present(code) is True

    def test_decorator_missing(self):
        """Test that missing decorator is detected."""
        code = """
class MyAdapter:
    pass
"""
        assert AdapterContractSpec.check_decorator_present(code) is False

    def test_required_methods_present(self):
        """Test that all required methods are found."""
        code = """
class MyAdapter:
    def fetch_raw(self):
        pass

    def transform(self, data):
        pass

    def get_schema(self):
        pass
"""
        missing = AdapterContractSpec.check_required_methods(
            code,
            {"fetch_raw", "transform", "get_schema"}
        )
        assert len(missing) == 0

    def test_required_methods_missing(self):
        """Test that missing methods are detected."""
        code = """
class MyAdapter:
    def fetch_raw(self):
        pass
"""
        missing = AdapterContractSpec.check_required_methods(
            code,
            {"fetch_raw", "transform", "get_schema"}
        )
        assert "transform" in missing
        assert "get_schema" in missing

    def test_validate_adapter_file_valid(self):
        """Test that a valid adapter file passes all checks."""
        code = """
from shared.modules.registry import register_adapter

@register_adapter
class WeatherAdapter:
    def fetch_raw(self):
        return {}

    def transform(self, data):
        return data

    def get_schema(self):
        return {}
"""
        result = AdapterContractSpec.validate_adapter_file(code)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_adapter_file_forbidden_import(self):
        """Test that forbidden imports cause validation failure."""
        code = """
import subprocess
from shared.modules.registry import register_adapter

@register_adapter
class BadAdapter:
    def fetch_raw(self):
        subprocess.call(['ls'])

    def transform(self, data):
        return data

    def get_schema(self):
        return {}
"""
        result = AdapterContractSpec.validate_adapter_file(code)
        assert result["valid"] is False
        assert any(e["code"] == ErrorCode.FORBIDDEN_IMPORT for e in result["errors"])

    def test_validate_adapter_file_missing_decorator(self):
        """Test that missing decorator causes validation failure."""
        code = """
class AdapterWithoutDecorator:
    def fetch_raw(self):
        return {}

    def transform(self, data):
        return data

    def get_schema(self):
        return {}
"""
        result = AdapterContractSpec.validate_adapter_file(code)
        assert result["valid"] is False
        assert any(e["code"] == ErrorCode.MISSING_DECORATOR for e in result["errors"])

    def test_validate_adapter_file_missing_methods(self):
        """Test that missing methods cause validation failure."""
        code = """
from shared.modules.registry import register_adapter

@register_adapter
class IncompleteAdapter:
    def fetch_raw(self):
        return {}
"""
        result = AdapterContractSpec.validate_adapter_file(code)
        assert result["valid"] is False
        assert any(e["code"] == ErrorCode.MISSING_METHOD for e in result["errors"])


class TestFileChange:
    """Tests for FileChange model."""

    def test_valid_file_change(self):
        """Test that valid file change is accepted."""
        change = FileChange(path="modules/weather/openweather/adapter.py", content="# code here")
        assert change.path == "modules/weather/openweather/adapter.py"
        assert change.content == "# code here"

    def test_markdown_fence_rejected(self):
        """Test that markdown fences in content are rejected."""
        with pytest.raises(ValidationError, match="must not contain markdown fences"):
            FileChange(
                path="modules/weather/adapter.py",
                content="```python\nprint('hello')\n```"
            )

    def test_content_without_fences_accepted(self):
        """Test that content without fences is accepted."""
        change = FileChange(
            path="modules/weather/adapter.py",
            content="print('hello')\n# This is code"
        )
        assert "print" in change.content


class TestGeneratorResponseContract:
    """Tests for GeneratorResponseContract validation."""

    @pytest.fixture
    def valid_response(self):
        """A valid generator response."""
        return {
            "stage": "adapter",
            "module": "weather/openweather",
            "changed_files": [
                {
                    "path": "modules/weather/openweather/adapter.py",
                    "content": "# adapter code"
                }
            ],
            "deleted_files": [],
            "assumptions": ["API key is provided"],
            "rationale": "Using requests library for HTTP calls",
            "policy": "adapter_contract_v1",
            "validation_report": {"syntax_check": "passed"}
        }

    def test_valid_response_accepted(self, valid_response):
        """Test that a valid response is accepted."""
        contract = GeneratorResponseContract(**valid_response)
        assert contract.stage == "adapter"
        assert contract.module == "weather/openweather"

    def test_missing_required_field(self, valid_response):
        """Test that missing required fields are rejected."""
        del valid_response["stage"]
        with pytest.raises(ValidationError):
            GeneratorResponseContract(**valid_response)

    def test_invalid_module_format(self, valid_response):
        """Test that invalid module format is rejected."""
        valid_response["module"] = "weather"  # Missing platform
        with pytest.raises(ValidationError, match="must be in format"):
            GeneratorResponseContract(**valid_response)

    def test_module_with_uppercase_rejected(self, valid_response):
        """Test that uppercase in module ID is rejected."""
        valid_response["module"] = "Weather/OpenWeather"
        with pytest.raises(ValidationError):
            GeneratorResponseContract(**valid_response)

    def test_empty_stage_rejected(self, valid_response):
        """Test that empty stage is rejected."""
        valid_response["stage"] = ""
        with pytest.raises(ValidationError, match="must be non-empty"):
            GeneratorResponseContract(**valid_response)

    def test_markdown_fence_in_changed_files_rejected(self, valid_response):
        """Test that markdown fences in changed files are rejected."""
        valid_response["changed_files"][0]["content"] = "```python\ncode\n```"
        with pytest.raises(ValidationError, match="must not contain markdown fences"):
            GeneratorResponseContract(**valid_response)

    def test_too_many_changed_files(self, valid_response):
        """Test that exceeding max changed files is rejected."""
        valid_response["changed_files"] = [
            {"path": f"file{i}.py", "content": "code"}
            for i in range(15)  # Exceeds max_changed_files = 10
        ]
        with pytest.raises(ValidationError, match="Too many changed files"):
            GeneratorResponseContract(**valid_response)

    def test_file_size_limit_exceeded(self, valid_response):
        """Test that files exceeding size limit are rejected."""
        valid_response["changed_files"][0]["content"] = "x" * 200_000  # 200KB > 100KB limit
        with pytest.raises(ValidationError, match="exceeds size limit"):
            GeneratorResponseContract(**valid_response)

    def test_path_allowlist_enforcement(self, valid_response):
        """Test that path allowlist is enforced."""
        contract = GeneratorResponseContract(**valid_response)
        allowed_dirs = ["modules/weather/openweather"]

        # Valid path
        disallowed = contract.validate_path_allowlist(allowed_dirs)
        assert len(disallowed) == 0

        # Add disallowed path
        contract.changed_files.append(
            FileChange(path="shared/config.py", content="# config")
        )
        disallowed = contract.validate_path_allowlist(allowed_dirs)
        assert "shared/config.py" in disallowed

    def test_validate_contract_all_valid(self, valid_response):
        """Test that valid contract passes all checks."""
        contract = GeneratorResponseContract(**valid_response)
        result = contract.validate_contract(["modules/weather/openweather"])
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_contract_path_violation(self, valid_response):
        """Test that path violations are caught."""
        valid_response["changed_files"].append({
            "path": "orchestrator/core.py",  # Outside allowed dir
            "content": "# bad"
        })
        contract = GeneratorResponseContract(**valid_response)
        result = contract.validate_contract(["modules/weather/openweather"])
        assert result["valid"] is False
        assert any(e["code"] == ErrorCode.PATH_NOT_ALLOWED for e in result["errors"])


class TestValidateGeneratorResponse:
    """Tests for validate_generator_response convenience function."""

    def test_valid_response_via_function(self):
        """Test that valid response passes through function."""
        response_data = {
            "stage": "tests",
            "module": "calendar/google",
            "changed_files": [
                {
                    "path": "modules/calendar/google/test_adapter.py",
                    "content": "# test code"
                }
            ],
            "deleted_files": [],
            "assumptions": ["OAuth2 configured"],
            "rationale": "Standard pytest structure",
            "policy": "test_contract_v1",
            "validation_report": {"tests_count": 5}
        }
        result = validate_generator_response(
            response_data,
            ["modules/calendar/google"]
        )
        assert result["valid"] is True

    def test_invalid_response_via_function(self):
        """Test that invalid response is rejected through function."""
        response_data = {
            "stage": "adapter",
            "module": "INVALID",  # Invalid format
            "changed_files": [],
            "assumptions": [],
            "rationale": "",
            "policy": "",
            "validation_report": {}
        }
        result = validate_generator_response(
            response_data,
            ["modules/weather/openweather"]
        )
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_malformed_data_via_function(self):
        """Test that malformed data is caught."""
        response_data = {
            "stage": "adapter"
            # Missing all other required fields
        }
        result = validate_generator_response(
            response_data,
            ["modules/weather/openweather"]
        )
        assert result["valid"] is False
        assert any(e["code"] == ErrorCode.INVALID_FIELD_VALUE for e in result["errors"])


class TestContractInvariants:
    """Test contract invariants across different scenarios."""

    def test_valid_payloads_always_pass(self):
        """Test that valid payloads consistently pass validation."""
        valid_responses = [
            {
                "stage": "manifest",
                "module": "weather/darksky",
                "changed_files": [{"path": "modules/weather/darksky/manifest.json", "content": "{}"}],
                "deleted_files": [],
                "assumptions": ["none"],
                "rationale": "initial",
                "policy": "v1",
                "validation_report": {}
            },
            {
                "stage": "adapter",
                "module": "finance/plaid",
                "changed_files": [{"path": "modules/finance/plaid/adapter.py", "content": "class X: pass"}],
                "deleted_files": [],
                "assumptions": ["API v2"],
                "rationale": "modern API",
                "policy": "adapter_v1",
                "validation_report": {"status": "ok"}
            }
        ]

        for response_data in valid_responses:
            contract = GeneratorResponseContract(**response_data)
            module_parts = response_data["module"].split("/")
            allowed_dir = f"modules/{module_parts[0]}/{module_parts[1]}"
            result = contract.validate_contract([allowed_dir])
            assert result["valid"] is True

    def test_invalid_payloads_always_fail_with_codes(self):
        """Test that invalid payloads fail with specific error codes."""
        # Missing required field
        with pytest.raises(ValidationError):
            GeneratorResponseContract(
                stage="test",
                # module missing
                changed_files=[],
                assumptions=[],
                rationale="",
                policy="",
                validation_report={}
            )

        # Markdown fence
        with pytest.raises(ValidationError):
            GeneratorResponseContract(
                stage="test",
                module="test/module",
                changed_files=[{"path": "test.py", "content": "```\ncode\n```"}],
                assumptions=[],
                rationale="",
                policy="",
                validation_report={}
            )

        # Invalid module format
        with pytest.raises(ValidationError):
            GeneratorResponseContract(
                stage="test",
                module="invalid-format",
                changed_files=[],
                assumptions=[],
                rationale="",
                policy="",
                validation_report={}
            )
