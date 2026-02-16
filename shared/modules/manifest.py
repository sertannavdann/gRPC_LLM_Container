"""
Module Manifest - Metadata schema for dynamically loaded modules.

Each module directory contains a manifest.json describing the module's
identity, requirements, and validation state. The ModuleManifest is the
single source of truth for module metadata throughout the system.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
import json
from pathlib import Path


class ModuleStatus(str, Enum):
    """Lifecycle status of a module."""
    PENDING = "pending"          # Created but not yet validated
    VALIDATING = "validating"    # Currently running tests
    VALIDATED = "validated"      # Tests passed, awaiting approval
    APPROVED = "approved"        # User approved, ready to install
    INSTALLED = "installed"      # Loaded and active
    DISABLED = "disabled"        # Installed but not active
    FAILED = "failed"            # Validation or runtime failure
    UNINSTALLED = "uninstalled"  # Removed from active registry


@dataclass
class ValidationResults:
    """Results from module validation pipeline."""
    syntax_check: str = "pending"    # pass | fail | pending
    unit_tests: str = "pending"
    integration_test: str = "pending"
    test_coverage: float = 0.0
    error_details: Optional[str] = None
    validated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationResults":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ModuleManifest:
    """
    Complete metadata for a NEXUS module.

    Stored as manifest.json in each module directory:
        modules/{category}/{platform}/manifest.json
    """
    # Identity
    name: str                       # e.g., "clashroyale"
    version: str = "1.0.0"
    category: str = "unknown"       # e.g., "gaming", "finance", "health"
    platform: str = "unknown"       # e.g., "clashroyale", "cibc", "applewatch"
    display_name: str = ""
    description: str = ""
    icon: str = "🔌"

    # Module structure
    entry_point: str = "adapter.py"
    class_name: str = ""            # e.g., "ClashRoyaleAdapter"
    test_file: str = "test_adapter.py"

    # Requirements
    requires_api_key: bool = False
    api_key_instructions: str = ""
    python_dependencies: List[str] = field(default_factory=list)

    # Auth
    auth_type: str = "api_key"      # api_key | oauth2 | basic | none
    auth_url: Optional[str] = None

    # Lifecycle
    status: str = "pending"
    health_status: str = "unknown"  # healthy | degraded | unhealthy | unknown
    created_by: str = "user"        # user | executor_agent
    build_provider: str = ""        # e.g., "claude-sonnet-4-5", "local"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Validation
    validation_results: ValidationResults = field(default_factory=ValidationResults)

    # Runtime stats
    failure_count: int = 0
    success_count: int = 0
    last_used: Optional[str] = None

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name.replace("_", " ").title()
        if not self.class_name:
            self.class_name = f"{self.platform.title().replace('_', '')}Adapter"

    @property
    def module_id(self) -> str:
        """Unique identifier: category/platform."""
        return f"{self.category}/{self.platform}"

    @property
    def module_dir(self) -> str:
        """Relative directory path: modules/{category}/{platform}/"""
        return f"modules/{self.category}/{self.platform}"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["validation_results"] = self.validation_results.to_dict()
        return data

    def save(self, base_path: Path) -> Path:
        """Save manifest to manifest.json in the module directory."""
        module_path = base_path / self.category / self.platform
        module_path.mkdir(parents=True, exist_ok=True)
        manifest_file = module_path / "manifest.json"
        self.updated_at = datetime.now(timezone.utc).isoformat()
        manifest_file.write_text(json.dumps(self.to_dict(), indent=2))
        return manifest_file

    @classmethod
    def load(cls, manifest_path: Path) -> "ModuleManifest":
        """Load manifest from a manifest.json file."""
        data = json.loads(manifest_path.read_text())
        validation = data.pop("validation_results", {})
        manifest = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        manifest.validation_results = ValidationResults.from_dict(validation)
        return manifest

    @classmethod
    def discover(cls, modules_dir: Path) -> List["ModuleManifest"]:
        """Discover all manifests under a modules directory."""
        manifests = []
        if not modules_dir.exists():
            return manifests
        for manifest_file in modules_dir.rglob("manifest.json"):
            try:
                manifests.append(cls.load(manifest_file))
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Skipping invalid manifest {manifest_file}: {e}"
                )
        return manifests
