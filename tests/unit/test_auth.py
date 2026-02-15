"""
Unit tests for shared.auth — models, API key store, and RBAC.

Tests API key lifecycle (create, validate, rotate, revoke),
Pydantic model validation, and RBAC permission matrix.
"""

import os
import sqlite3
import tempfile

import pytest

from shared.auth.models import APIKeyRecord, Organization, Role, User
from shared.auth.api_keys import APIKeyStore
from shared.auth.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    has_permission,
    require_permission,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary SQLite DB path for APIKeyStore."""
    return str(tmp_path / "test_api_keys.db")


@pytest.fixture
def store(tmp_db):
    """Create a fresh APIKeyStore backed by a temp DB."""
    return APIKeyStore(db_path=tmp_db)


@pytest.fixture
def seeded_store(store):
    """APIKeyStore pre-seeded with an org and keys for each role."""
    store.create_organization("org-1", "Test Org")
    keys = {}
    for role in Role:
        plaintext, key_id = store.create_key("org-1", role.value)
        keys[role] = {"plaintext": plaintext, "key_id": key_id}
    store._keys = keys  # stash for test access
    return store


# ============================================================================
# Models
# ============================================================================


class TestModels:
    """Pydantic model validation."""

    def test_role_enum_values(self):
        assert Role.VIEWER == "viewer"
        assert Role.OPERATOR == "operator"
        assert Role.ADMIN == "admin"
        assert Role.OWNER == "owner"

    def test_user_create(self):
        user = User(user_id="u-1", org_id="org-1", role=Role.ADMIN)
        assert user.user_id == "u-1"
        assert user.role == Role.ADMIN
        assert user.email is None

    def test_user_with_email(self):
        user = User(
            user_id="u-2", org_id="org-1", role=Role.VIEWER, email="a@b.com"
        )
        assert user.email == "a@b.com"

    def test_organization_defaults(self):
        org = Organization(org_id="o-1", name="Acme", created_at="2026-01-01")
        assert org.plan == "free"

    def test_api_key_record_defaults(self):
        rec = APIKeyRecord(
            key_id="k-1",
            org_id="o-1",
            role=Role.VIEWER,
            created_at="2026-01-01",
        )
        assert rec.status == "active"
        assert rec.last_used is None

    def test_role_from_string(self):
        assert Role("admin") == Role.ADMIN
        with pytest.raises(ValueError):
            Role("superadmin")


# ============================================================================
# APIKeyStore — Core Lifecycle
# ============================================================================


class TestAPIKeyStore:
    """API key create / validate / rotate / revoke."""

    def test_init_creates_tables(self, tmp_db, store):
        conn = sqlite3.connect(tmp_db)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert {"api_keys", "organizations", "users"}.issubset(tables)

    def test_wal_mode(self, tmp_db, store):
        conn = sqlite3.connect(tmp_db)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_create_key_returns_plaintext_and_id(self, store):
        key, key_id = store.create_key("org-1", "viewer")
        assert isinstance(key, str) and len(key) > 20
        assert isinstance(key_id, str) and len(key_id) > 10

    def test_validate_returns_user(self, store):
        key, _ = store.create_key("org-1", "admin")
        user = store.validate_key(key)
        assert user is not None
        assert user.org_id == "org-1"
        assert user.role == Role.ADMIN

    def test_validate_invalid_key_returns_none(self, store):
        assert store.validate_key("totally-invalid-key") is None

    def test_key_stored_hashed(self, tmp_db, store):
        key, key_id = store.create_key("org-1", "viewer")
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT key_hash FROM api_keys WHERE key_id = ?", (key_id,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] != key  # stored value != plaintext
        assert len(row[0]) == 64  # SHA-256 hex digest

    def test_validate_updates_last_used(self, tmp_db, store):
        key, key_id = store.create_key("org-1", "viewer")
        store.validate_key(key)
        conn = sqlite3.connect(tmp_db)
        last = conn.execute(
            "SELECT last_used FROM api_keys WHERE key_id = ?", (key_id,)
        ).fetchone()[0]
        conn.close()
        assert last is not None

    def test_revoke_key(self, store):
        key, key_id = store.create_key("org-1", "viewer")
        assert store.revoke_key(key_id) is True
        assert store.validate_key(key) is None

    def test_revoke_nonexistent_key(self, store):
        assert store.revoke_key("no-such-key") is False

    def test_list_keys_excludes_revoked(self, store):
        _, kid1 = store.create_key("org-1", "viewer")
        _, kid2 = store.create_key("org-1", "admin")
        store.revoke_key(kid1)
        keys = store.list_keys("org-1")
        ids = [k.key_id for k in keys]
        assert kid2 in ids
        assert kid1 not in ids

    def test_list_keys_scoped_to_org(self, store):
        store.create_key("org-A", "viewer")
        store.create_key("org-B", "admin")
        assert len(store.list_keys("org-A")) == 1
        assert len(store.list_keys("org-B")) == 1

    # ── Rotation ──────────────────────────────────────────────────────

    def test_rotate_key_dual_overlap(self, store):
        key, kid = store.create_key("org-1", "admin")
        new_key, new_kid = store.rotate_key("org-1", kid)
        # Both keys valid during grace period
        assert store.validate_key(key) is not None
        assert store.validate_key(new_key) is not None

    def test_rotate_key_preserves_role(self, store):
        key, kid = store.create_key("org-1", "operator")
        new_key, _ = store.rotate_key("org-1", kid)
        user = store.validate_key(new_key)
        assert user.role == Role.OPERATOR

    def test_rotate_nonexistent_key_raises(self, store):
        with pytest.raises(ValueError):
            store.rotate_key("org-1", "no-such-key")

    # ── Organization & User CRUD ──────────────────────────────────────

    def test_create_organization(self, store):
        org = store.create_organization("org-x", "Org X", plan="pro")
        assert org.org_id == "org-x"
        assert org.plan == "pro"

    def test_get_organization(self, store):
        store.create_organization("org-y", "Org Y")
        org = store.get_organization("org-y")
        assert org is not None
        assert org.name == "Org Y"

    def test_get_nonexistent_org(self, store):
        assert store.get_organization("ghost") is None

    def test_create_user(self, store):
        store.create_organization("org-z", "Z Corp")
        user = store.create_user("u-1", "org-z", "admin", "a@z.com")
        assert user.role == Role.ADMIN
        assert user.email == "a@z.com"


# ============================================================================
# RBAC Permission Matrix
# ============================================================================


class TestRBAC:
    """Permission checks for each role tier."""

    # ── Viewer ────────────────────────────────────────────────────────

    def test_viewer_can_read_config(self):
        assert has_permission(Role.VIEWER, Permission.READ_CONFIG)

    def test_viewer_cannot_write_config(self):
        assert not has_permission(Role.VIEWER, Permission.WRITE_CONFIG)

    def test_viewer_cannot_manage_modules(self):
        assert not has_permission(Role.VIEWER, Permission.MANAGE_MODULES)

    def test_viewer_cannot_manage_credentials(self):
        assert not has_permission(Role.VIEWER, Permission.MANAGE_CREDENTIALS)

    # ── Operator ──────────────────────────────────────────────────────

    def test_operator_can_read(self):
        assert has_permission(Role.OPERATOR, Permission.READ_CONFIG)

    def test_operator_can_manage_modules(self):
        assert has_permission(Role.OPERATOR, Permission.MANAGE_MODULES)

    def test_operator_cannot_write_config(self):
        assert not has_permission(Role.OPERATOR, Permission.WRITE_CONFIG)

    def test_operator_cannot_manage_keys(self):
        assert not has_permission(Role.OPERATOR, Permission.MANAGE_KEYS)

    # ── Admin ─────────────────────────────────────────────────────────

    def test_admin_can_write_config(self):
        assert has_permission(Role.ADMIN, Permission.WRITE_CONFIG)

    def test_admin_can_manage_modules(self):
        assert has_permission(Role.ADMIN, Permission.MANAGE_MODULES)

    def test_admin_can_manage_keys(self):
        assert has_permission(Role.ADMIN, Permission.MANAGE_KEYS)

    def test_admin_cannot_manage_credentials(self):
        assert not has_permission(Role.ADMIN, Permission.MANAGE_CREDENTIALS)

    def test_admin_cannot_admin_all(self):
        assert not has_permission(Role.ADMIN, Permission.ADMIN_ALL)

    # ── Owner ─────────────────────────────────────────────────────────

    def test_owner_has_all_permissions(self):
        for perm in Permission:
            assert has_permission(Role.OWNER, perm), f"Owner missing {perm}"

    # ── Hierarchy ─────────────────────────────────────────────────────

    def test_permission_hierarchy(self):
        """Each higher role has a superset of the lower role's permissions."""
        hierarchy = [Role.VIEWER, Role.OPERATOR, Role.ADMIN, Role.OWNER]
        for i in range(len(hierarchy) - 1):
            lower = ROLE_PERMISSIONS[hierarchy[i]]
            upper = ROLE_PERMISSIONS[hierarchy[i + 1]]
            assert lower.issubset(upper), (
                f"{hierarchy[i+1]} should be a superset of {hierarchy[i]}"
            )
