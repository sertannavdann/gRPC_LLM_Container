"""
Core contract specifications for NEXUS module system.

Defines the contracts that all generated modules and the builder itself must follow:
- AdapterContractSpec: Requirements for adapter.py files
- GeneratorResponseContract: Schema for LLM generator outputs
"""
import ast
import re
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, ClassVar
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.modules.security_policy import FORBIDDEN_IMPORTS
from shared.modules.static_analysis import check_imports as static_check_imports


class ErrorCode(str, Enum):
    """Standard error codes for contract violations."""
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_FIELD_VALUE = "invalid_field_value"
    FORBIDDEN_IMPORT = "forbidden_import"
    MISSING_DECORATOR = "missing_decorator"
    MISSING_METHOD = "missing_method"
    MARKDOWN_FENCE_DETECTED = "markdown_fence_detected"
    PATH_NOT_ALLOWED = "path_not_allowed"
    SIZE_LIMIT_EXCEEDED = "size_limit_exceeded"
    UNKNOWN_FIELD = "unknown_field"


class AdapterContractSpec:
    """
    Contract specification for adapter.py files.

    Defines required structure, forbidden imports, and validation helpers.
    """

    # Required base class methods
    REQUIRED_METHODS = {
        "fetch_raw",
        "transform",
        "get_schema"
    }

    # Required decorator import
    REQUIRED_DECORATOR_IMPORT = "register_adapter"

    @staticmethod
    def check_forbidden_imports(source_code: str) -> List[str]:
        """
        Check for forbidden imports using AST parsing.

        Args:
            source_code: Python source code to check

        Returns:
            List of forbidden import names found
        """
        # Delegate to shared static analysis module
        violations = static_check_imports(source_code, FORBIDDEN_IMPORTS)

        # Extract just the forbidden import names from violation messages
        # Violations format: "Line N: Import 'name' ..."
        forbidden_found = []
        for violation in violations:
            # Parse import name from violation message
            if "Import '" in violation:
                import_name = violation.split("Import '")[1].split("'")[0]
                if import_name not in forbidden_found:
                    forbidden_found.append(import_name)
            elif "Dynamic __import__" in violation:
                if "__import__" not in forbidden_found:
                    forbidden_found.append("__import__")

        return forbidden_found

    @staticmethod
    def check_decorator_present(source_code: str, decorator_name: str = "register_adapter") -> bool:
        """
        Check if the required decorator is present on a class.

        Args:
            source_code: Python source code to check
            decorator_name: Name of decorator to look for

        Returns:
            True if decorator is present, False otherwise
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for decorator in node.decorator_list:
                    # Handle @register_adapter
                    if isinstance(decorator, ast.Name) and decorator.id == decorator_name:
                        return True
                    # Handle @register_adapter(...)
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name) and decorator.func.id == decorator_name:
                            return True

        return False

    @staticmethod
    def check_required_methods(source_code: str, required_methods: Set[str]) -> List[str]:
        """
        Check if all required methods are defined in the class.

        Args:
            source_code: Python source code to check
            required_methods: Set of method names that must be present

        Returns:
            List of missing method names
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return list(required_methods)

        defined_methods = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defined_methods.add(item.name)

        missing = required_methods - defined_methods
        return list(missing)

    @staticmethod
    def validate_adapter_file(source_code: str) -> Dict[str, Any]:
        """
        Run all adapter contract validations.

        Args:
            source_code: Python source code to validate

        Returns:
            Dictionary with validation results
        """
        results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        # Check forbidden imports
        forbidden = AdapterContractSpec.check_forbidden_imports(source_code)
        if forbidden:
            results["valid"] = False
            results["errors"].append({
                "code": ErrorCode.FORBIDDEN_IMPORT,
                "message": f"Forbidden imports detected: {', '.join(forbidden)}"
            })

        # Check decorator
        if not AdapterContractSpec.check_decorator_present(source_code):
            results["valid"] = False
            results["errors"].append({
                "code": ErrorCode.MISSING_DECORATOR,
                "message": f"Missing @{AdapterContractSpec.REQUIRED_DECORATOR_IMPORT} decorator"
            })

        # Check required methods
        missing = AdapterContractSpec.check_required_methods(
            source_code,
            AdapterContractSpec.REQUIRED_METHODS
        )
        if missing:
            results["valid"] = False
            results["errors"].append({
                "code": ErrorCode.MISSING_METHOD,
                "message": f"Missing required methods: {', '.join(missing)}"
            })

        return results


class FileChange(BaseModel):
    """A single file change in a generator response."""
    path: str
    content: str

    @field_validator("content")
    @classmethod
    def no_markdown_fences(cls, v: str) -> str:
        """Ensure content doesn't contain markdown code fences."""
        if "```" in v:
            raise ValueError("Content must not contain markdown fences (```)")
        return v


class GeneratorResponseContract(BaseModel):
    """
    Contract for LLM generator responses.

    Enforces strict schema for module generation outputs including:
    - Stage tracking
    - Changed/deleted files with path allowlist
    - Assumptions and rationale
    - Policy adherence
    - Validation reports
    - No markdown fences in file content
    """

    # Configuration (class variables)
    MAX_CHANGED_FILES: ClassVar[int] = 10
    MAX_PATCH_BYTES: ClassVar[int] = 100_000  # 100KB per file

    # Required fields
    stage: str = Field(..., description="Current generation stage (e.g., 'manifest', 'adapter', 'tests')")
    module: str = Field(..., description="Module identifier in format category/platform")
    changed_files: List[FileChange] = Field(..., description="List of files created or modified")
    deleted_files: List[str] = Field(default_factory=list, description="List of files to delete")
    assumptions: List[str] = Field(..., description="Assumptions made during generation")
    rationale: str = Field(..., description="Explanation of design decisions")
    policy: str = Field(..., description="Which policy/contract was followed")
    validation_report: Dict[str, Any] = Field(..., description="Self-validation results")

    @field_validator("module")
    @classmethod
    def validate_module_format(cls, v: str) -> str:
        """Ensure module ID matches category/platform format."""
        if not re.match(r"^[a-z0-9_]+/[a-z0-9_]+$", v):
            raise ValueError("Module must be in format 'category/platform'")
        return v

    @field_validator("changed_files")
    @classmethod
    def validate_changed_files(cls, v: List[FileChange]) -> List[FileChange]:
        """Validate changed files list."""
        if len(v) > cls.MAX_CHANGED_FILES:
            raise ValueError(f"Too many changed files (max {cls.MAX_CHANGED_FILES})")

        for file_change in v:
            if len(file_change.content.encode('utf-8')) > cls.MAX_PATCH_BYTES:
                raise ValueError(f"File {file_change.path} exceeds size limit")

        return v

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str) -> str:
        """Ensure stage is non-empty."""
        if not v or not v.strip():
            raise ValueError("Stage must be non-empty")
        return v

    def validate_path_allowlist(self, allowed_dirs: List[str]) -> List[str]:
        """
        Check that all changed/deleted files are within allowed directories.

        Args:
            allowed_dirs: List of allowed directory paths (e.g., ["modules/weather/openweather"])

        Returns:
            List of disallowed paths found
        """
        disallowed = []

        all_paths = [f.path for f in self.changed_files] + self.deleted_files

        for path in all_paths:
            path_obj = Path(path)
            allowed = False

            for allowed_dir in allowed_dirs:
                try:
                    # Check if path is relative to allowed directory
                    path_obj.relative_to(allowed_dir)
                    allowed = True
                    break
                except ValueError:
                    continue

            if not allowed:
                disallowed.append(path)

        return disallowed

    def validate_contract(self, allowed_dirs: List[str]) -> Dict[str, Any]:
        """
        Run full contract validation.

        Args:
            allowed_dirs: List of allowed directory paths

        Returns:
            Dictionary with validation results
        """
        results = {
            "valid": True,
            "errors": []
        }

        # Check path allowlist
        disallowed = self.validate_path_allowlist(allowed_dirs)
        if disallowed:
            results["valid"] = False
            results["errors"].append({
                "code": ErrorCode.PATH_NOT_ALLOWED,
                "message": f"Files outside allowed directories: {', '.join(disallowed)}"
            })

        # File count check (already validated by Pydantic, but explicit here)
        if len(self.changed_files) > self.MAX_CHANGED_FILES:
            results["valid"] = False
            results["errors"].append({
                "code": ErrorCode.SIZE_LIMIT_EXCEEDED,
                "message": f"Too many changed files: {len(self.changed_files)} > {self.MAX_CHANGED_FILES}"
            })

        return results


# Convenience function for external use
def validate_generator_response(
    response_data: Dict[str, Any],
    allowed_dirs: List[str]
) -> Dict[str, Any]:
    """
    Validate a generator response against the contract.

    Args:
        response_data: Raw response data from LLM generator
        allowed_dirs: List of allowed directory paths

    Returns:
        Dictionary with validation results including errors
    """
    try:
        contract = GeneratorResponseContract(**response_data)
        return contract.validate_contract(allowed_dirs)
    except Exception as e:
        return {
            "valid": False,
            "errors": [{
                "code": ErrorCode.INVALID_FIELD_VALUE,
                "message": str(e)
            }]
        }
