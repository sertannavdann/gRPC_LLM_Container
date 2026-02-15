"""
API Key Store — SQLite-backed API key lifecycle management.

Handles generation, hashing, validation, rotation, and revocation
of API keys. Keys are stored SHA-256 hashed, never plaintext.
Follows the SQLite pattern from shared/modules/registry.py.
"""
import hashlib
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import APIKeyRecord, Organization, Role, User

logger = logging.getLogger(__name__)


class APIKeyStore:
    """
    SQLite-backed API key store with SHA-256 hashing.

    Supports full key lifecycle: create, validate, rotate, revoke.
    Keys are stored hashed — plaintext is only returned at creation time.
    """

    def __init__(self, db_path: str = "data/api_keys.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"APIKeyStore initialized: {self.db_path}")

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS organizations (
                    org_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    plan TEXT DEFAULT 'free'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    email TEXT,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(org_id) REFERENCES organizations(org_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    user_id TEXT,
                    created_at TEXT NOT NULL,
                    last_used TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    rotation_grace_until TEXT,
                    rate_limit INTEGER DEFAULT 1000
                )
            """)

    def generate_key(self) -> str:
        return secrets.token_urlsafe(32)

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def create_key(
        self,
        org_id: str,
        role: str = "viewer",
        user_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Create a new API key for an organization.

        Returns (plaintext_key, key_id). The plaintext key is only
        available at creation time — it is stored hashed.
        """
        plaintext_key = self.generate_key()
        key_hash = self._hash_key(plaintext_key)
        key_id = secrets.token_urlsafe(16)
        now = datetime.utcnow().isoformat()

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO api_keys
                   (key_id, org_id, key_hash, role, user_id, created_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'active')""",
                (key_id, org_id, key_hash, role, user_id, now),
            )

        logger.info(f"API key created: key_id={key_id}, org_id={org_id}, role={role}")
        return plaintext_key, key_id

    def validate_key(self, key_plaintext: str) -> Optional[User]:
        """
        Validate an API key and return the associated User.

        Accepts both 'active' and 'rotation_pending' keys.
        Returns None for invalid or revoked keys.
        Always hashes input to prevent timing attacks.
        """
        key_hash = self._hash_key(key_plaintext)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM api_keys
                   WHERE key_hash = ? AND status IN ('active', 'rotation_pending')""",
                (key_hash,),
            ).fetchone()

        if row is None:
            return None

        # Update last_used timestamp
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE api_keys SET last_used = ? WHERE key_id = ?",
                (now, row["key_id"]),
            )

        return User(
            user_id=row["user_id"] or row["key_id"],
            org_id=row["org_id"],
            role=Role(row["role"]),
        )

    def rotate_key(
        self,
        org_id: str,
        key_id: str,
        grace_days: int = 7,
    ) -> tuple[str, str]:
        """
        Rotate an API key using dual-key overlap.

        Creates a new key, marks the old one as 'rotation_pending'
        with a grace period. Both keys remain valid until the grace
        period expires.

        Returns (new_plaintext_key, new_key_id).
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            old_key = conn.execute(
                "SELECT role, user_id FROM api_keys WHERE key_id = ? AND org_id = ?",
                (key_id, org_id),
            ).fetchone()

        if old_key is None:
            raise ValueError(f"Key {key_id} not found for org {org_id}")

        new_plaintext, new_key_id = self.create_key(
            org_id=org_id,
            role=old_key["role"],
            user_id=old_key["user_id"],
        )

        grace_until = (datetime.utcnow() + timedelta(days=grace_days)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE api_keys
                   SET status = 'rotation_pending', rotation_grace_until = ?
                   WHERE key_id = ? AND org_id = ?""",
                (grace_until, key_id, org_id),
            )

        logger.info(
            f"API key rotated: old={key_id}, new={new_key_id}, "
            f"grace_until={grace_until}"
        )
        return new_plaintext, new_key_id

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key. Returns True if the key was found and revoked."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE api_keys SET status = 'revoked' WHERE key_id = ?",
                (key_id,),
            )
            revoked = cursor.rowcount > 0

        if revoked:
            logger.info(f"API key revoked: key_id={key_id}")
        return revoked

    def list_keys(self, org_id: str) -> list[APIKeyRecord]:
        """List all non-revoked API keys for an organization."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT key_id, org_id, role, created_at, last_used, status
                   FROM api_keys
                   WHERE org_id = ? AND status != 'revoked'
                   ORDER BY created_at DESC""",
                (org_id,),
            ).fetchall()

        return [
            APIKeyRecord(
                key_id=row["key_id"],
                org_id=row["org_id"],
                role=Role(row["role"]),
                created_at=row["created_at"],
                last_used=row["last_used"],
                status=row["status"],
            )
            for row in rows
        ]

    def create_organization(
        self,
        org_id: str,
        name: str,
        plan: str = "free",
    ) -> Organization:
        """Create a new organization."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO organizations (org_id, name, created_at, plan)
                   VALUES (?, ?, ?, ?)""",
                (org_id, name, now, plan),
            )
        logger.info(f"Organization created: org_id={org_id}, name={name}")
        return Organization(org_id=org_id, name=name, created_at=now, plan=plan)

    def get_organization(self, org_id: str) -> Optional[Organization]:
        """Get an organization by ID."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM organizations WHERE org_id = ?",
                (org_id,),
            ).fetchone()

        if row is None:
            return None
        return Organization(
            org_id=row["org_id"],
            name=row["name"],
            created_at=row["created_at"],
            plan=row["plan"],
        )

    def create_user(
        self,
        user_id: str,
        org_id: str,
        role: str = "viewer",
        email: Optional[str] = None,
    ) -> User:
        """Create a new user within an organization."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO users (user_id, org_id, email, role, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, org_id, email, role, now),
            )
        logger.info(f"User created: user_id={user_id}, org_id={org_id}, role={role}")
        return User(
            user_id=user_id,
            org_id=org_id,
            role=Role(role),
            email=email,
            created_at=now,
        )
