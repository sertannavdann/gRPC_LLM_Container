"""
Version pointer management for rollback operations.

Provides instant rollback to prior validated versions without rebuild:
- list_versions: show all validated versions with timestamps and hashes
- get_active_version: return currently installed version
- rollback_to_version: move active pointer to prior validated version

Rollback is pointer movement only — no code regeneration required.
All versions are preserved for future rollback.
"""
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModuleVersion:
    """
    Metadata for a single module version.

    Attributes:
        version_id: Unique version identifier
        module_id: Module identifier (category/platform)
        bundle_sha256: Content-addressed artifact hash
        status: Version status (VALIDATED, ACTIVE, ARCHIVED)
        created_at: ISO timestamp of version creation
        created_by: Actor who created the version
        validation_report: Validation report for this version
        source: Origin of version (generated, draft_promoted, etc.)
        metadata: Additional version-specific context
    """
    version_id: str
    module_id: str
    bundle_sha256: str
    status: str
    created_at: str
    created_by: str
    validation_report: Optional[Dict[str, Any]] = None
    source: str = "generated"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModuleVersion":
        """Create ModuleVersion from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class VersionManager:
    """
    Manages module version history and rollback operations.

    Uses SQLite for persistent version tracking:
        versions table: version_id, module_id, bundle_sha256, status, created_at, etc.
        active_versions table: module_id, version_id (pointer to active version)
    """

    def __init__(self, db_path: str = "data/module_versions.db", audit_log=None):
        """
        Initialize version manager.

        Args:
            db_path: Path to SQLite database
            audit_log: Audit log instance for recording rollback actions
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log = audit_log
        self._init_db()
        logger.info(f"VersionManager initialized: {self.db_path}")

    def _init_db(self) -> None:
        """Create version tracking tables if they don't exist."""
        with self._connect() as conn:
            # Versions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS versions (
                    version_id TEXT PRIMARY KEY,
                    module_id TEXT NOT NULL,
                    bundle_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'VALIDATED',
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    validation_report TEXT,
                    source TEXT DEFAULT 'generated',
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Active versions pointer table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS active_versions (
                    module_id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (version_id) REFERENCES versions(version_id)
                )
            """)

            # Index for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_versions_module_id
                ON versions(module_id)
            """)

            # Migration: add org_id column if not exists
            try:
                conn.execute(
                    "ALTER TABLE versions ADD COLUMN org_id TEXT DEFAULT 'default'"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                conn.execute(
                    "ALTER TABLE active_versions ADD COLUMN org_id TEXT DEFAULT 'default'"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

    def _connect(self):
        """Create database connection."""
        return sqlite3.connect(str(self.db_path))

    def record_version(
        self,
        module_id: str,
        bundle_sha256: str,
        actor: str = "system",
        validation_report: Optional[Dict[str, Any]] = None,
        source: str = "generated",
        metadata: Optional[Dict[str, Any]] = None,
        org_id: str = "default"
    ) -> str:
        """
        Record a new validated version.

        Args:
            module_id: Module identifier
            bundle_sha256: Artifact bundle hash
            actor: Identity of version creator
            validation_report: Validation report dict
            source: Origin (generated, draft_promoted, etc.)
            metadata: Additional version context
            org_id: Organization identifier

        Returns:
            version_id
        """
        # Generate version ID
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        version_id = f"{module_id.replace('/', '_')}_v_{timestamp}"

        now = datetime.utcnow().isoformat() + "Z"

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO versions
                    (version_id, module_id, bundle_sha256, status, created_at,
                     created_by, validation_report, source, metadata, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    module_id,
                    bundle_sha256,
                    "VALIDATED",
                    now,
                    actor,
                    json.dumps(validation_report) if validation_report else None,
                    source,
                    json.dumps(metadata or {}),
                    org_id
                )
            )

            # Set as active version if no active version exists
            cursor = conn.execute(
                "SELECT version_id FROM active_versions WHERE module_id = ? AND org_id = ?",
                (module_id, org_id)
            )
            if cursor.fetchone() is None:
                conn.execute(
                    "INSERT INTO active_versions (module_id, version_id, updated_at, org_id) VALUES (?, ?, ?, ?)",
                    (module_id, version_id, now, org_id)
                )
                logger.info(f"Version recorded and set as active: {version_id}")
            else:
                logger.info(f"Version recorded: {version_id}")

        return version_id

    def list_versions(
        self,
        module_id: str,
        org_id: Optional[str] = None
    ) -> List[ModuleVersion]:
        """
        List all validated versions for a module.

        Args:
            module_id: Module identifier
            org_id: Optional organization filter

        Returns:
            List of ModuleVersion sorted by creation time (newest first)
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if org_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM versions
                    WHERE module_id = ? AND org_id = ?
                    ORDER BY created_at DESC
                    """,
                    (module_id, org_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM versions
                    WHERE module_id = ?
                    ORDER BY created_at DESC
                    """,
                    (module_id,)
                ).fetchall()

        versions = []
        for row in rows:
            version_data = dict(row)
            # Parse JSON fields
            if version_data.get("validation_report"):
                version_data["validation_report"] = json.loads(version_data["validation_report"])
            if version_data.get("metadata"):
                version_data["metadata"] = json.loads(version_data["metadata"])
            versions.append(ModuleVersion.from_dict(version_data))

        return versions

    def get_active_version(
        self,
        module_id: str,
        org_id: Optional[str] = None
    ) -> Optional[ModuleVersion]:
        """
        Get the currently active version for a module.

        Args:
            module_id: Module identifier
            org_id: Optional organization filter

        Returns:
            ModuleVersion or None if no active version
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if org_id is not None:
                row = conn.execute(
                    """
                    SELECT v.* FROM versions v
                    JOIN active_versions a ON v.version_id = a.version_id
                    WHERE a.module_id = ? AND a.org_id = ?
                    """,
                    (module_id, org_id)
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT v.* FROM versions v
                    JOIN active_versions a ON v.version_id = a.version_id
                    WHERE a.module_id = ?
                    """,
                    (module_id,)
                ).fetchone()

        if row is None:
            return None

        version_data = dict(row)
        # Parse JSON fields
        if version_data.get("validation_report"):
            version_data["validation_report"] = json.loads(version_data["validation_report"])
        if version_data.get("metadata"):
            version_data["metadata"] = json.loads(version_data["metadata"])

        return ModuleVersion.from_dict(version_data)

    def rollback_to_version(
        self,
        module_id: str,
        target_version_id: str,
        actor: str = "system",
        reason: str = "",
        org_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Rollback to a prior validated version.

        This is instant pointer movement — no rebuild required.
        The target version must have status VALIDATED.

        Args:
            module_id: Module identifier
            target_version_id: Version ID to rollback to
            actor: Identity of user performing rollback
            reason: Reason for rollback
            org_id: Organization identifier

        Returns:
            Dict with rollback status and version info
        """
        with self._connect() as conn:
            # Verify target version exists and is VALIDATED
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM versions WHERE version_id = ? AND module_id = ? AND org_id = ?",
                (target_version_id, module_id, org_id)
            ).fetchone()

            if row is None:
                return {
                    "status": "error",
                    "error": f"Version {target_version_id} not found for module {module_id}"
                }

            version_data = dict(row)
            if version_data["status"] != "VALIDATED":
                return {
                    "status": "error",
                    "error": f"Cannot rollback to version with status: {version_data['status']}. Only VALIDATED versions allowed."
                }

            # Get current active version
            current = conn.execute(
                "SELECT version_id FROM active_versions WHERE module_id = ? AND org_id = ?",
                (module_id, org_id)
            ).fetchone()
            from_version = current[0] if current else None

            # Update active version pointer
            now = datetime.utcnow().isoformat() + "Z"
            if current:
                conn.execute(
                    "UPDATE active_versions SET version_id = ?, updated_at = ? WHERE module_id = ? AND org_id = ?",
                    (target_version_id, now, module_id, org_id)
                )
            else:
                conn.execute(
                    "INSERT INTO active_versions (module_id, version_id, updated_at, org_id) VALUES (?, ?, ?, ?)",
                    (module_id, target_version_id, now, org_id)
                )

        # Audit log
        if self.audit_log:
            self.audit_log.log_action(
                action="version_rollback",
                actor=actor,
                module_id=module_id,
                details={
                    "from_version": from_version,
                    "to_version": target_version_id,
                    "reason": reason,
                    "bundle_sha256": version_data["bundle_sha256"]
                }
            )

        logger.info(f"Rolled back {module_id} from {from_version} to {target_version_id}")

        return {
            "status": "success",
            "module_id": module_id,
            "from_version": from_version,
            "to_version": target_version_id,
            "bundle_sha256": version_data["bundle_sha256"],
            "message": f"Module {module_id} rolled back to version {target_version_id}"
        }

    def get_version(self, version_id: str, org_id: Optional[str] = None) -> Optional[ModuleVersion]:
        """
        Get a specific version by ID.

        Args:
            version_id: Version identifier
            org_id: Optional organization filter

        Returns:
            ModuleVersion or None if not found
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if org_id is not None:
                row = conn.execute(
                    "SELECT * FROM versions WHERE version_id = ? AND org_id = ?",
                    (version_id, org_id)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM versions WHERE version_id = ?",
                    (version_id,)
                ).fetchone()

        if row is None:
            return None

        version_data = dict(row)
        # Parse JSON fields
        if version_data.get("validation_report"):
            version_data["validation_report"] = json.loads(version_data["validation_report"])
        if version_data.get("metadata"):
            version_data["metadata"] = json.loads(version_data["metadata"])

        return ModuleVersion.from_dict(version_data)
