"""
Integration tests for auth middleware and Admin API RBAC enforcement.

Tests the full request lifecycle: middleware auth → RBAC dependency → response.
Requires httpx (TestClient) but NO running services or Docker.
"""

import os
import sqlite3
import tempfile

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from shared.auth.api_keys import APIKeyStore
from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.models import Role, User
from shared.auth.rbac import Permission, get_current_user, has_permission, require_permission

# Skip the session-scoped Docker check — these tests run in-process
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ============================================================================
# Fixtures — minimal FastAPI app wired with auth
# ============================================================================


@pytest.fixture
def auth_db(tmp_path):
    return str(tmp_path / "auth_test.db")


@pytest.fixture
def store(auth_db):
    return APIKeyStore(db_path=auth_db)


@pytest.fixture
def app_with_auth(store):
    """Build a minimal FastAPI app with auth middleware + RBAC endpoints."""
    app = FastAPI()

    # Public endpoint
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Authenticated read
    @app.get("/protected")
    def protected(user: User = Depends(get_current_user)):
        return {"org_id": user.org_id, "role": user.role.value}

    # RBAC: write config
    @app.put("/config")
    def write_config(
        user: User = Depends(require_permission(Permission.WRITE_CONFIG)),
    ):
        return {"updated": True}

    # RBAC: manage modules
    @app.post("/modules/enable")
    def enable_module(
        user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
    ):
        return {"enabled": True}

    # RBAC: manage credentials
    @app.post("/credentials")
    def manage_creds(
        user: User = Depends(require_permission(Permission.MANAGE_CREDENTIALS)),
    ):
        return {"stored": True}

    # RBAC: manage keys
    @app.post("/api-keys")
    def manage_keys(
        user: User = Depends(require_permission(Permission.MANAGE_KEYS)),
    ):
        return {"created": True}

    app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=store,
        public_paths=["/health"],
    )
    return app


@pytest.fixture
def client(app_with_auth):
    return TestClient(app_with_auth)


@pytest.fixture
def keys(store):
    """Create one key per role for org-1."""
    store.create_organization("org-1", "Test Org")
    out = {}
    for role in Role:
        plaintext, key_id = store.create_key("org-1", role.value)
        out[role] = plaintext
    return out


# ============================================================================
# Middleware — Authentication
# ============================================================================


class TestMiddlewareAuth:
    """X-API-Key validation at the middleware layer."""

    def test_public_path_no_auth(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_missing_key_returns_401(self, client):
        r = client.get("/protected")
        assert r.status_code == 401
        assert "Missing API key" in r.json()["detail"]

    def test_invalid_key_returns_401(self, client):
        r = client.get("/protected", headers={"X-API-Key": "bogus"})
        assert r.status_code == 401
        assert "Invalid API key" in r.json()["detail"]

    def test_valid_key_passes_through(self, client, keys):
        r = client.get(
            "/protected", headers={"X-API-Key": keys[Role.VIEWER]}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["org_id"] == "org-1"
        assert body["role"] == "viewer"

    def test_options_passthrough(self, client):
        """CORS preflight must not be blocked."""
        r = client.options("/protected")
        # Should not be a 401
        assert r.status_code != 401

    def test_revoked_key_rejected(self, client, store, keys):
        key = keys[Role.VIEWER]
        # Get key_id for viewer
        all_keys = store.list_keys("org-1")
        viewer_kid = [k.key_id for k in all_keys if k.role == Role.VIEWER][0]
        store.revoke_key(viewer_kid)
        r = client.get("/protected", headers={"X-API-Key": key})
        assert r.status_code == 401


# ============================================================================
# RBAC — Endpoint-Level Authorization
# ============================================================================


class TestRBACEnforcement:
    """Permission checks on protected endpoints."""

    # ── Viewer ────────────────────────────────────────────────────────

    def test_viewer_can_read(self, client, keys):
        r = client.get(
            "/protected", headers={"X-API-Key": keys[Role.VIEWER]}
        )
        assert r.status_code == 200

    def test_viewer_cannot_write_config(self, client, keys):
        r = client.put(
            "/config", headers={"X-API-Key": keys[Role.VIEWER]}
        )
        assert r.status_code == 403

    def test_viewer_cannot_manage_modules(self, client, keys):
        r = client.post(
            "/modules/enable", headers={"X-API-Key": keys[Role.VIEWER]}
        )
        assert r.status_code == 403

    def test_viewer_cannot_manage_credentials(self, client, keys):
        r = client.post(
            "/credentials", headers={"X-API-Key": keys[Role.VIEWER]}
        )
        assert r.status_code == 403

    # ── Operator ──────────────────────────────────────────────────────

    def test_operator_can_manage_modules(self, client, keys):
        r = client.post(
            "/modules/enable", headers={"X-API-Key": keys[Role.OPERATOR]}
        )
        assert r.status_code == 200

    def test_operator_cannot_write_config(self, client, keys):
        r = client.put(
            "/config", headers={"X-API-Key": keys[Role.OPERATOR]}
        )
        assert r.status_code == 403

    # ── Admin ─────────────────────────────────────────────────────────

    def test_admin_can_write_config(self, client, keys):
        r = client.put(
            "/config", headers={"X-API-Key": keys[Role.ADMIN]}
        )
        assert r.status_code == 200

    def test_admin_can_manage_modules(self, client, keys):
        r = client.post(
            "/modules/enable", headers={"X-API-Key": keys[Role.ADMIN]}
        )
        assert r.status_code == 200

    def test_admin_can_manage_keys(self, client, keys):
        r = client.post(
            "/api-keys", headers={"X-API-Key": keys[Role.ADMIN]}
        )
        assert r.status_code == 200

    def test_admin_cannot_manage_credentials(self, client, keys):
        r = client.post(
            "/credentials", headers={"X-API-Key": keys[Role.ADMIN]}
        )
        assert r.status_code == 403

    # ── Owner ─────────────────────────────────────────────────────────

    def test_owner_can_do_everything(self, client, keys):
        endpoints = [
            ("GET", "/protected"),
            ("PUT", "/config"),
            ("POST", "/modules/enable"),
            ("POST", "/credentials"),
            ("POST", "/api-keys"),
        ]
        for method, path in endpoints:
            r = client.request(
                method, path, headers={"X-API-Key": keys[Role.OWNER]}
            )
            assert r.status_code == 200, f"Owner blocked on {method} {path}"


# ============================================================================
# Multi-Tenant Isolation
# ============================================================================


class TestMultiTenantIsolation:
    """Verify org_id scoping across stores."""

    def test_key_returns_correct_org(self, store):
        store.create_organization("alpha", "Alpha")
        store.create_organization("beta", "Beta")
        key_a, _ = store.create_key("alpha", "admin")
        key_b, _ = store.create_key("beta", "viewer")
        user_a = store.validate_key(key_a)
        user_b = store.validate_key(key_b)
        assert user_a.org_id == "alpha"
        assert user_b.org_id == "beta"

    def test_list_keys_org_isolated(self, store):
        store.create_key("alpha", "admin")
        store.create_key("alpha", "viewer")
        store.create_key("beta", "owner")
        assert len(store.list_keys("alpha")) == 2
        assert len(store.list_keys("beta")) == 1

    def test_credential_store_org_isolation(self):
        from shared.modules.credentials import CredentialStore

        with tempfile.TemporaryDirectory() as td:
            cs = CredentialStore(db_path=os.path.join(td, "creds.db"))
            cs.store("mod/a", {"key": "val_x"}, org_id="org-X")
            cs.store("mod/a", {"key": "val_y"}, org_id="org-Y")
            assert cs.retrieve("mod/a", org_id="org-X")["key"] == "val_x"
            assert cs.retrieve("mod/a", org_id="org-Y")["key"] == "val_y"

    def test_registry_org_scoping(self):
        from shared.modules.registry import ModuleRegistry

        with tempfile.TemporaryDirectory() as td:
            reg = ModuleRegistry(db_path=os.path.join(td, "reg.db"))
            conn = sqlite3.connect(os.path.join(td, "reg.db"))
            cols = [
                r[1] for r in conn.execute("PRAGMA table_info(modules)").fetchall()
            ]
            conn.close()
            assert "org_id" in cols

    def test_agent_state_org_id(self):
        from core.state import create_initial_state

        s1 = create_initial_state("c-1", org_id="org-1")
        s2 = create_initial_state("c-2")
        assert s1["org_id"] == "org-1"
        assert s2.get("org_id") is None
