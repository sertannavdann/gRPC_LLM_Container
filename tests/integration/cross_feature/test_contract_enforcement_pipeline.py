"""
Cross-feature integration test: Contract enforcement across boundaries.

Verifies that GeneratorResponseContract validation at the gateway layer is
consistent with AdapterContractSpec validation at the validator layer.

Components integrated:
- shared/modules/contracts.py
- sandbox_service/runner.py (StaticImportChecker)
- sandbox_service/policy.py (ImportPolicy)
"""
import pytest
from pathlib import Path
from pydantic import ValidationError

from shared.modules.contracts import (
    AdapterContractSpec,
    GeneratorResponseContract,
    FileChange,
    ErrorCode,
)
from sandbox_service.runner import StaticImportChecker
from sandbox_service.policy import ImportPolicy, ExecutionPolicy


class TestContractEnforcementPipeline:

    def test_gateway_validated_code_passes_validator_static_checks(
        self, valid_adapter_code
    ):
        """Code valid per GeneratorResponseContract also passes AdapterContractSpec."""
        contract = GeneratorResponseContract(
            stage="adapter",
            module="weather/openweather",
            changed_files=[
                FileChange(
                    path="weather/openweather/adapter.py",
                    content=valid_adapter_code,
                )
            ],
            assumptions=["API returns JSON"],
            rationale="Standard REST adapter",
            policy="adapter_contract_v1",
            validation_report={"self_check": "passed"},
        )

        # Contract validates
        result = contract.validate_contract(
            allowed_dirs=["weather/openweather"]
        )
        assert result["valid"] is True

        # Adapter code also passes AdapterContractSpec
        adapter_result = AdapterContractSpec.validate_adapter_file(valid_adapter_code)
        assert adapter_result["valid"] is True

    def test_forbidden_imports_caught_at_both_boundaries(
        self, forbidden_import_adapter_code
    ):
        """Forbidden imports rejected by both AdapterContractSpec and StaticImportChecker."""
        # AdapterContractSpec catches it
        forbidden = AdapterContractSpec.check_forbidden_imports(
            forbidden_import_adapter_code
        )
        assert "subprocess" in forbidden

        # StaticImportChecker also catches it
        policy = ImportPolicy.module_validation()
        violations = StaticImportChecker.check_imports(
            forbidden_import_adapter_code, policy
        )
        subprocess_violations = [
            v for v in violations if "subprocess" in v.module_name
        ]
        assert len(subprocess_violations) > 0

    def test_markdown_fences_rejected_by_contract(self):
        """GeneratorResponseContract rejects content with markdown fences."""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorResponseContract(
                stage="adapter",
                module="weather/test",
                changed_files=[
                    FileChange(
                        path="weather/test/adapter.py",
                        content="```python\nclass A: pass\n```",
                    )
                ],
                assumptions=["test"],
                rationale="test",
                policy="v1",
                validation_report={},
            )

        assert "markdown fences" in str(exc_info.value).lower()

    def test_path_allowlist_enforced(self):
        """Files outside allowed_dirs rejected by validate_contract."""
        contract = GeneratorResponseContract(
            stage="adapter",
            module="weather/openweather",
            changed_files=[
                FileChange(
                    path="weather/openweather/adapter.py",
                    content="class A: pass",
                )
            ],
            assumptions=["test"],
            rationale="test",
            policy="v1",
            validation_report={},
        )

        # Within allowed dir — passes
        result = contract.validate_contract(
            allowed_dirs=["weather/openweather"]
        )
        assert result["valid"] is True

        # Outside allowed dir — fails
        result = contract.validate_contract(
            allowed_dirs=["finance/cibc"]
        )
        assert result["valid"] is False

        errors = result["errors"]
        assert any(
            e["code"] == ErrorCode.PATH_NOT_ALLOWED for e in errors
        )

    def test_build_and_repair_tools_registered_in_orchestrator_source(self):
        """build_module and repair_module are explicitly registered in orchestrator."""
        repo_root = Path(__file__).resolve().parents[3]
        orchestrator_source = (repo_root / "orchestrator" / "orchestrator_service.py").read_text()

        assert "self.tool_registry.register(build_module)" in orchestrator_source
        assert "self.tool_registry.register(repair_module)" in orchestrator_source
