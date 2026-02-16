"""
Version pointer management for module rollback.

Enables safe rollback to prior validated versions without rebuild:
- Track all validated versions with timestamps and hashes
- Move active pointer to any validated version
- Preserve all versions (no deletion on rollback)
- Full audit trail via shared/modules/audit.py

Key features:
- Immutable version storage (data/versions/)
- Active version pointer in registry
- Instant rollback (pointer movement, not rebuild)
- Audit logging for all rollback operations
"""
import json
import logging
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class VersionRecord:
    """
    Record of a single module version.

    Attributes:
        version_id: Unique version identifier (e.g., "v1", "v2", "draft-abc123")
        bundle_sha256: Content hash of this version
        created_at: ISO timestamp of version creation
        created_by: Actor who created this version
        status: VALIDATED | ACTIVE | DEPRECATED
        source: How this version was created (generated | promoted_from_draft)
        metadata: Additional version info (draft_id, validation_report, etc.)
    """
    version_id: str
    bundle_sha256: str
    created_at: str
    created_by: str = "system"
    status: str = "VALIDATED"
    source: str = "generated"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VersionRecord":
        """Create VersionRecord from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class VersionManager:
    """
    Manages module version pointers for rollback.

    Version storage structure:
        data/versions/{module_id}/
            versions.json       - List of all versions with metadata
            v1/                 - Version 1 files
                adapter.py
                manifest.json
                test_adapter.py
            v2/                 - Version 2 files
                adapter.py
                manifest.json
                test_adapter.py
    """

    def __init__(
        self,
        versions_dir: Path = Path("data/versions"),
        modules_dir: Path = Path("modules"),
        audit_log=None
    ):
        """
        Initialize version manager.

        Args:
            versions_dir: Directory for version storage
            modules_dir: Directory for installed modules
            audit_log: Audit log instance for recording actions
        """
        self.versions_dir = Path(versions_dir)
        self.modules_dir = Path(modules_dir)
        self.audit_log = audit_log
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def list_versions(self, module_id: str) -> List[VersionRecord]:
        """
        List all validated versions for a module.

        Args:
            module_id: Module identifier (category/platform)

        Returns:
            List of VersionRecord sorted by creation time (newest first)
        """
        module_versions_dir = self.versions_dir / module_id.replace("/", "_")
        versions_file = module_versions_dir / "versions.json"

        if not versions_file.exists():
            return []

        data = json.loads(versions_file.read_text())
        versions = [VersionRecord.from_dict(v) for v in data.get("versions", [])]

        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def get_active_version(self, module_id: str) -> Optional[VersionRecord]:
        """
        Get currently active version.

        Args:
            module_id: Module identifier

        Returns:
            VersionRecord of active version or None
        """
        versions = self.list_versions(module_id)
        active = [v for v in versions if v.status == "ACTIVE"]

        return active[0] if active else None

    def register_version(
        self,
        module_id: str,
        bundle_sha256: str,
        actor: str = "system",
        source: str = "generated",
        metadata: Optional[Dict[str, Any]] = None
    ) -> VersionRecord:
        """
        Register a new validated version.

        Args:
            module_id: Module identifier
            bundle_sha256: Content hash of version
            actor: Actor creating the version
            source: How version was created (generated | promoted_from_draft)
            metadata: Additional version metadata

        Returns:
            VersionRecord for new version
        """
        module_versions_dir = self.versions_dir / module_id.replace("/", "_")
        module_versions_dir.mkdir(parents=True, exist_ok=True)

        versions_file = module_versions_dir / "versions.json"

        # Load existing versions
        if versions_file.exists():
            data = json.loads(versions_file.read_text())
            versions = [VersionRecord.from_dict(v) for v in data.get("versions", [])]
        else:
            versions = []

        # Generate version ID
        version_num = len(versions) + 1
        version_id = f"v{version_num}"

        # Create version record
        version = VersionRecord(
            version_id=version_id,
            bundle_sha256=bundle_sha256,
            created_at=datetime.utcnow().isoformat() + "Z",
            created_by=actor,
            status="VALIDATED",
            source=source,
            metadata=metadata or {}
        )

        # Copy module files to version directory
        parts = module_id.split("/")
        category, platform = parts
        source_module_dir = self.modules_dir / category / platform
        version_dir = module_versions_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        if source_module_dir.exists():
            for filename in ["adapter.py", "test_adapter.py", "manifest.json"]:
                src_file = source_module_dir / filename
                if src_file.exists():
                    shutil.copy2(src_file, version_dir / filename)

        # Save versions
        versions.append(version)
        versions_file.write_text(json.dumps({
            "module_id": module_id,
            "versions": [v.to_dict() for v in versions]
        }, indent=2))

        logger.info(f"Version registered: {module_id} {version_id} ({bundle_sha256[:12]})")

        return version

    def rollback_to_version(
        self,
        module_id: str,
        target_version_id: str,
        actor: str = "system",
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Rollback module to a prior validated version.

        This is a pointer movement operation, not a rebuild:
        1. Find target version in version storage
        2. Copy target version files to active module directory
        3. Update active pointer in versions.json
        4. Record rollback in audit log

        Args:
            module_id: Module identifier
            target_version_id: Version to rollback to (e.g., "v1")
            actor: Identity of user performing rollback
            reason: Optional reason for rollback

        Returns:
            Dict with rollback status and details
        """
        module_versions_dir = self.versions_dir / module_id.replace("/", "_")
        versions_file = module_versions_dir / "versions.json"

        if not versions_file.exists():
            return {
                "status": "error",
                "error": f"No version history found for {module_id}"
            }

        # Load versions
        data = json.loads(versions_file.read_text())
        versions = [VersionRecord.from_dict(v) for v in data.get("versions", [])]

        # Find target version
        target = next((v for v in versions if v.version_id == target_version_id), None)
        if not target:
            return {
                "status": "error",
                "error": f"Version {target_version_id} not found for {module_id}"
            }

        # Validate target is VALIDATED status
        if target.status not in ["VALIDATED", "ACTIVE"]:
            return {
                "status": "error",
                "error": f"Cannot rollback to version with status: {target.status}"
            }

        # Get current active version (for audit)
        current_active = next((v for v in versions if v.status == "ACTIVE"), None)
        from_version = current_active.version_id if current_active else "none"

        # Copy target version files to active module directory
        parts = module_id.split("/")
        category, platform = parts
        module_dir = self.modules_dir / category / platform
        module_dir.mkdir(parents=True, exist_ok=True)

        version_dir = module_versions_dir / target_version_id

        if not version_dir.exists():
            return {
                "status": "error",
                "error": f"Version storage directory not found: {version_dir}"
            }

        # Copy files
        for filename in ["adapter.py", "test_adapter.py", "manifest.json"]:
            src_file = version_dir / filename
            if src_file.exists():
                dest_file = module_dir / filename
                shutil.copy2(src_file, dest_file)

        # Update version statuses (only one ACTIVE at a time)
        for v in versions:
            if v.version_id == target_version_id:
                v.status = "ACTIVE"
            elif v.status == "ACTIVE":
                v.status = "VALIDATED"

        # Save updated versions
        versions_file.write_text(json.dumps({
            "module_id": module_id,
            "versions": [v.to_dict() for v in versions]
        }, indent=2))

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="module_rollback",
                actor=actor,
                module_id=module_id,
                details={
                    "from_version": from_version,
                    "to_version": target_version_id,
                    "reason": reason,
                    "bundle_sha256": target.bundle_sha256
                }
            )

        logger.info(
            f"Rollback complete: {module_id} from {from_version} to {target_version_id}"
        )

        return {
            "status": "success",
            "module_id": module_id,
            "from_version": from_version,
            "to_version": target_version_id,
            "bundle_sha256": target.bundle_sha256,
            "message": f"Rolled back {module_id} from {from_version} to {target_version_id}"
        }

    def get_version_files(
        self,
        module_id: str,
        version_id: str
    ) -> Optional[Dict[str, str]]:
        """
        Get file contents for a specific version.

        Args:
            module_id: Module identifier
            version_id: Version to retrieve

        Returns:
            Dict mapping filename to content, or None if version not found
        """
        module_versions_dir = self.versions_dir / module_id.replace("/", "_")
        version_dir = module_versions_dir / version_id

        if not version_dir.exists():
            return None

        files = {}
        for filename in ["adapter.py", "test_adapter.py", "manifest.json"]:
            file_path = version_dir / filename
            if file_path.exists():
                files[filename] = file_path.read_text()

        return files if files else None
