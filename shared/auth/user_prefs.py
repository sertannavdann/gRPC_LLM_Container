"""
User Preferences Store

SQLite-backed user preference persistence with optimistic concurrency.
WAL-mode for concurrent read access.

Preferences stored per-user:
  - theme (light/dark/system)
  - provider_ordering (list of provider IDs)
  - module_favorites (list of module IDs)
  - monitoring_tab (overview/modules/alerts)
  - dashboard_layout (optional layout configuration)

Optimistic concurrency via version field:
  - set_prefs requires expected_version
  - Raises ConflictError if version mismatch (409)

Academic anchor: EDMO T6 (CQRS — user prefs as read-optimized model)
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic Models ──────────────────────────────────────────────────────────


class UserPreferences(BaseModel):
    """User preference data model."""

    theme: str = Field(default="system", pattern=r"^(light|dark|system)$")
    provider_ordering: list[str] = Field(default_factory=list)
    module_favorites: list[str] = Field(default_factory=list)
    monitoring_tab: str = Field(default="overview", pattern=r"^(overview|modules|alerts)$")
    dashboard_layout: Optional[dict] = None


class ConflictError(Exception):
    """Raised when optimistic concurrency version mismatch occurs."""

    def __init__(self, current_version: int, expected_version: int):
        self.current_version = current_version
        self.expected_version = expected_version
        super().__init__(
            f"Version conflict: expected {expected_version}, "
            f"current is {current_version}"
        )


# ── User Prefs Store ────────────────────────────────────────────────────────


class UserPrefsStore:
    """SQLite-backed user preference persistence with optimistic concurrency."""

    def __init__(self, db_path: str = "data/user_prefs.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection with WAL mode."""
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create user_prefs table if it does not exist."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_prefs (
                    user_id   TEXT PRIMARY KEY,
                    prefs_json TEXT NOT NULL DEFAULT '{}',
                    version   INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        logger.info(f"UserPrefsStore initialized at {self._db_path}")

    def get_prefs(self, user_id: str) -> tuple[UserPreferences, int]:
        """
        Get user preferences.

        Returns (preferences, version). Returns defaults if no record exists.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT prefs_json, version FROM user_prefs WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if row is None:
            return UserPreferences(), 0

        try:
            data = json.loads(row["prefs_json"])
            prefs = UserPreferences(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse prefs for {user_id}: {e}")
            prefs = UserPreferences()

        return prefs, row["version"]

    def set_prefs(
        self, user_id: str, prefs: UserPreferences, expected_version: int
    ) -> int:
        """
        Set user preferences with optimistic concurrency.

        Args:
            user_id: User identifier
            prefs: New preferences
            expected_version: Expected current version (0 for new record)

        Returns:
            New version number

        Raises:
            ConflictError: If version mismatch (HTTP 409)
        """
        now = datetime.now(timezone.utc).isoformat()
        prefs_json = prefs.model_dump_json()

        with self._connect() as conn:
            if expected_version == 0:
                # Insert new record
                try:
                    conn.execute(
                        """
                        INSERT INTO user_prefs (user_id, prefs_json, version, updated_at)
                        VALUES (?, ?, 1, ?)
                        """,
                        (user_id, prefs_json, now),
                    )
                    conn.commit()
                    return 1
                except sqlite3.IntegrityError:
                    # Record was created concurrently, check version
                    row = conn.execute(
                        "SELECT version FROM user_prefs WHERE user_id = ?",
                        (user_id,),
                    ).fetchone()
                    raise ConflictError(
                        current_version=row["version"] if row else 1,
                        expected_version=0,
                    )
            else:
                # Update with version check
                new_version = expected_version + 1
                result = conn.execute(
                    """
                    UPDATE user_prefs
                    SET prefs_json = ?, version = ?, updated_at = ?
                    WHERE user_id = ? AND version = ?
                    """,
                    (prefs_json, new_version, now, user_id, expected_version),
                )

                if result.rowcount == 0:
                    # Version mismatch
                    row = conn.execute(
                        "SELECT version FROM user_prefs WHERE user_id = ?",
                        (user_id,),
                    ).fetchone()

                    if row is None:
                        # Record deleted, treat as version 0
                        raise ConflictError(
                            current_version=0,
                            expected_version=expected_version,
                        )
                    raise ConflictError(
                        current_version=row["version"],
                        expected_version=expected_version,
                    )

                conn.commit()
                return new_version

    def delete_prefs(self, user_id: str) -> bool:
        """Delete user preferences. Returns True if record existed."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM user_prefs WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            return result.rowcount > 0
