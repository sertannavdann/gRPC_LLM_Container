"""
Persistent Module Registry — SQLite-backed module lifecycle storage.

Tracks installed modules, their status, health, and usage across
service restarts. Follows the checkpointing.py pattern for SQLite usage.

Schema:
    modules: name, category, platform, status, health, manifest_json,
             installed_at, updated_at, failure_count, success_count
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .manifest import ModuleManifest, ModuleStatus

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    SQLite-backed persistent registry for installed modules.

    Survives service restarts. Used alongside the in-memory
    ModuleLoader and AdapterRegistry for durable state.
    """

    def __init__(self, db_path: str = "data/module_registry.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"ModuleRegistry initialized: {self.db_path}")

    def _init_db(self) -> None:
        """Create the modules table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS modules (
                    module_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    health_status TEXT NOT NULL DEFAULT 'unknown',
                    manifest_json TEXT NOT NULL,
                    installed_at TEXT,
                    updated_at TEXT,
                    failure_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    last_used TEXT
                )
            """)

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def install(self, manifest: ModuleManifest) -> None:
        """Record a module installation."""
        now = datetime.utcnow().isoformat()
        manifest.status = ModuleStatus.INSTALLED
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO modules
                    (module_id, name, category, platform, status, health_status,
                     manifest_json, installed_at, updated_at, failure_count,
                     success_count, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.module_id, manifest.name, manifest.category,
                    manifest.platform, manifest.status, manifest.health_status,
                    json.dumps(manifest.to_dict()), now, now,
                    manifest.failure_count, manifest.success_count,
                    manifest.last_used,
                ),
            )
        logger.info(f"Module installed in registry: {manifest.module_id}")

    def uninstall(self, module_id: str) -> bool:
        """Remove a module from the registry."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM modules WHERE module_id = ?", (module_id,)
            )
            removed = cursor.rowcount > 0
        if removed:
            logger.info(f"Module uninstalled from registry: {module_id}")
        return removed

    def enable(self, module_id: str) -> bool:
        """Mark a module as installed (enabled)."""
        return self._update_status(module_id, ModuleStatus.INSTALLED)

    def disable(self, module_id: str) -> bool:
        """Mark a module as disabled."""
        return self._update_status(module_id, ModuleStatus.DISABLED)

    def update_health(self, module_id: str, health: str, increment_failure: bool = False) -> None:
        """Update module health status and optionally increment failure count."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            if increment_failure:
                conn.execute(
                    """UPDATE modules SET health_status = ?, failure_count = failure_count + 1,
                       updated_at = ? WHERE module_id = ?""",
                    (health, now, module_id),
                )
            else:
                conn.execute(
                    """UPDATE modules SET health_status = ?, updated_at = ?
                       WHERE module_id = ?""",
                    (health, now, module_id),
                )

    def record_usage(self, module_id: str) -> None:
        """Record a successful usage of a module."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE modules SET success_count = success_count + 1,
                   last_used = ?, updated_at = ? WHERE module_id = ?""",
                (now, now, module_id),
            )

    def get_module(self, module_id: str) -> Optional[Dict[str, Any]]:
        """Get a module's registry entry."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM modules WHERE module_id = ?", (module_id,)
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_modules(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all modules, optionally filtered by status."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM modules WHERE status = ? ORDER BY category, name",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM modules ORDER BY category, name"
                ).fetchall()
        return [dict(r) for r in rows]

    def list_installed(self) -> List[Dict[str, Any]]:
        """List all installed (enabled) modules."""
        return self.list_modules(status=ModuleStatus.INSTALLED)

    def get_unhealthy(self, failure_threshold: int = 5) -> List[Dict[str, Any]]:
        """Get modules exceeding the failure threshold."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM modules WHERE failure_count >= ? AND status = ?",
                (failure_threshold, ModuleStatus.INSTALLED),
            ).fetchall()
        return [dict(r) for r in rows]

    def _update_status(self, module_id: str, status: str) -> bool:
        """Update a module's status."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE modules SET status = ?, updated_at = ? WHERE module_id = ?",
                (status, now, module_id),
            )
            return cursor.rowcount > 0
