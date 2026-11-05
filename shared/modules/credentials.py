"""
Credential Store — encrypted at-rest storage for module API keys.

Uses Fernet symmetric encryption so credentials are never stored in
plaintext on disk. Master key comes from MODULE_ENCRYPTION_KEY env var.

Credentials are injected into AdapterConfig.credentials at module load
time and NEVER exposed to the LLM context.
"""
import json
import logging
import os
import sqlite3
from base64 import urlsafe_b64encode
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid hard dependency if cryptography not installed
_fernet = None


def _get_fernet():
    """Get or create Fernet instance from environment key."""
    global _fernet
    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning(
            "cryptography package not installed. "
            "Credentials will be stored base64-encoded (NOT encrypted). "
            "Install cryptography for production use."
        )
        return None

    key = os.getenv("MODULE_ENCRYPTION_KEY", "")
    if not key:
        # Derive a deterministic key from a fallback (dev only)
        logger.warning("MODULE_ENCRYPTION_KEY not set — using derived dev key")
        raw = sha256(b"nexus-dev-key-not-for-production").digest()
        key = urlsafe_b64encode(raw)
    else:
        key = key.encode() if isinstance(key, str) else key

    _fernet = Fernet(key)
    return _fernet


class CredentialStore:
    """
    Encrypted credential storage for dynamically loaded modules.

    Stores credentials in SQLite with Fernet encryption at rest.
    Falls back to base64 encoding if cryptography is not available.
    """

    def __init__(self, db_path: str = "data/module_credentials.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"CredentialStore initialized: {self.db_path}")

    def _init_db(self) -> None:
        with self._connect() as conn:
            # Check if we need to migrate from old schema (module_id PK only)
            existing_cols = [
                row[1] for row in conn.execute("PRAGMA table_info(credentials)").fetchall()
            ]

            if not existing_cols:
                # Fresh install: create with composite key
                conn.execute("""
                    CREATE TABLE credentials (
                        module_id TEXT NOT NULL,
                        encrypted_data TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        org_id TEXT NOT NULL DEFAULT 'default',
                        PRIMARY KEY (module_id, org_id)
                    )
                """)
            elif "org_id" not in existing_cols:
                # Migration: old table with module_id-only PK -> composite PK
                conn.execute("""
                    CREATE TABLE credentials_new (
                        module_id TEXT NOT NULL,
                        encrypted_data TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        org_id TEXT NOT NULL DEFAULT 'default',
                        PRIMARY KEY (module_id, org_id)
                    )
                """)
                conn.execute("""
                    INSERT INTO credentials_new (module_id, encrypted_data, created_at, updated_at, org_id)
                    SELECT module_id, encrypted_data, created_at, updated_at, 'default'
                    FROM credentials
                """)
                conn.execute("DROP TABLE credentials")
                conn.execute("ALTER TABLE credentials_new RENAME TO credentials")

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def store(self, module_id: str, credentials: Dict[str, Any], org_id: str = "default") -> None:
        """
        Store credentials for a module (encrypted at rest).

        Args:
            module_id: "category/platform" identifier
            credentials: Dict of credential key-value pairs
                         (e.g., {"api_key": "abc123"})
            org_id: Organization identifier for multi-tenant isolation
        """
        plaintext = json.dumps(credentials).encode()
        fernet = _get_fernet()

        if fernet:
            encrypted = fernet.encrypt(plaintext).decode()
        else:
            encrypted = urlsafe_b64encode(plaintext).decode()

        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO credentials
                   (module_id, encrypted_data, created_at, updated_at, org_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (module_id, encrypted, now, now, org_id),
            )
        logger.info(f"Credentials stored for module: {module_id}")

    def retrieve(self, module_id: str, org_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve decrypted credentials for a module.

        Returns None if no credentials are stored.
        """
        with self._connect() as conn:
            if org_id is not None:
                row = conn.execute(
                    "SELECT encrypted_data FROM credentials WHERE module_id = ? AND org_id = ?",
                    (module_id, org_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT encrypted_data FROM credentials WHERE module_id = ?",
                    (module_id,),
                ).fetchone()

        if row is None:
            return None

        encrypted = row[0]
        fernet = _get_fernet()

        try:
            if fernet:
                plaintext = fernet.decrypt(encrypted.encode())
            else:
                from base64 import urlsafe_b64decode
                plaintext = urlsafe_b64decode(encrypted)
            return json.loads(plaintext)
        except Exception as e:
            logger.error(f"Failed to decrypt credentials for {module_id}: {e}")
            return None

    def delete(self, module_id: str, org_id: Optional[str] = None) -> bool:
        """Delete credentials for a module."""
        with self._connect() as conn:
            if org_id is not None:
                cursor = conn.execute(
                    "DELETE FROM credentials WHERE module_id = ? AND org_id = ?",
                    (module_id, org_id),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM credentials WHERE module_id = ?", (module_id,)
                )
            removed = cursor.rowcount > 0
        if removed:
            logger.info(f"Credentials deleted for module: {module_id}")
        return removed

    def has_credentials(self, module_id: str, org_id: Optional[str] = None) -> bool:
        """Check if credentials exist for a module."""
        with self._connect() as conn:
            if org_id is not None:
                row = conn.execute(
                    "SELECT 1 FROM credentials WHERE module_id = ? AND org_id = ?",
                    (module_id, org_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM credentials WHERE module_id = ?", (module_id,)
                ).fetchone()
        return row is not None

    def list_modules_with_credentials(self, org_id: Optional[str] = None) -> list:
        """List module IDs that have stored credentials."""
        with self._connect() as conn:
            if org_id is not None:
                rows = conn.execute(
                    "SELECT module_id FROM credentials WHERE org_id = ?",
                    (org_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT module_id FROM credentials").fetchall()
        return [r[0] for r in rows]
