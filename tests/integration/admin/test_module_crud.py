"""
Module CRUD integration tests for Admin API.

Tests the following endpoints:
- GET /admin/modules — list all modules
- GET /admin/modules/{category}/{platform} — get module details
- POST /admin/modules/{category}/{platform}/enable — enable module
- POST /admin/modules/{category}/{platform}/disable — disable module
- POST /admin/modules/{category}/{platform}/reload — reload module
- DELETE /admin/modules/{category}/{platform} — uninstall module
- GET /admin/health — health check (no auth required)

All tests use FastAPI TestClient (in-process, no Docker).
"""
import json
from pathlib import Path

import pytest


class TestModuleCRUDEndpoints:
    """Test module CRUD operations via Admin API."""

    def test_list_modules_empty(self, client, admin_headers):
        """GET /admin/modules returns empty list when no modules installed."""
        response = client.get("/admin/modules", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert "modules" in body
        assert isinstance(body["modules"], list)
        assert body["total"] >= 0

    def test_list_modules_requires_auth(self, client):
        """GET /admin/modules without API key returns 401."""
        response = client.get("/admin/modules")
        assert response.status_code == 401
        assert "API key" in response.json()["detail"]

    def test_get_module_not_found(self, client, admin_headers):
        """GET /admin/modules/{cat}/{plat} returns 404 for nonexistent module."""
        response = client.get(
            "/admin/modules/nonexistent/platform", headers=admin_headers
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_enable_module_requires_permission(self, client, viewer_headers):
        """POST /admin/modules/{cat}/{plat}/enable forbidden for viewer role."""
        response = client.post(
            "/admin/modules/test/demo/enable", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_enable_module_not_found(self, client, admin_headers):
        """POST /admin/modules/{cat}/{plat}/enable returns 500 if module doesn't exist."""
        response = client.post(
            "/admin/modules/nonexistent/platform/enable", headers=admin_headers
        )
        # Module loader will throw exception → 500
        assert response.status_code == 500

    def test_disable_module_requires_permission(self, client, viewer_headers):
        """POST /admin/modules/{cat}/{plat}/disable forbidden for viewer role."""
        response = client.post(
            "/admin/modules/test/demo/disable", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_disable_module_not_found(self, client, admin_headers):
        """POST /admin/modules/{cat}/{plat}/disable returns 500 if module doesn't exist."""
        response = client.post(
            "/admin/modules/nonexistent/platform/disable", headers=admin_headers
        )
        # Module loader will throw exception → 500
        assert response.status_code == 500

    def test_health_endpoint_no_auth(self, client):
        """GET /admin/health does not require authentication."""
        response = client.get("/admin/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "modules_loaded" in body
        assert "config_manager" in body

    def test_health_endpoint_with_auth(self, client, admin_headers):
        """GET /admin/health works with authentication too."""
        response = client.get("/admin/health", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestModulePermissions:
    """Test RBAC enforcement on module management endpoints."""

    def test_viewer_can_list_modules(self, client, viewer_headers):
        """Viewer role can list modules (read permission)."""
        response = client.get("/admin/modules", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_cannot_enable_module(self, client, viewer_headers):
        """Viewer role cannot enable modules."""
        response = client.post(
            "/admin/modules/test/demo/enable", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_viewer_cannot_disable_module(self, client, viewer_headers):
        """Viewer role cannot disable modules."""
        response = client.post(
            "/admin/modules/test/demo/disable", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_operator_can_enable_module(self, client, operator_headers):
        """Operator role can enable modules (MANAGE_MODULES permission)."""
        # Will fail with 500 because module doesn't exist, but RBAC passes (not 403)
        response = client.post(
            "/admin/modules/test/demo/enable", headers=operator_headers
        )
        assert response.status_code != 403

    def test_operator_can_disable_module(self, client, operator_headers):
        """Operator role can disable modules."""
        response = client.post(
            "/admin/modules/test/demo/disable", headers=operator_headers
        )
        assert response.status_code != 403

    def test_admin_can_enable_module(self, client, admin_headers):
        """Admin role can enable modules."""
        response = client.post(
            "/admin/modules/test/demo/enable", headers=admin_headers
        )
        assert response.status_code != 403

    def test_admin_can_disable_module(self, client, admin_headers):
        """Admin role can disable modules."""
        response = client.post(
            "/admin/modules/test/demo/disable", headers=admin_headers
        )
        assert response.status_code != 403

    def test_owner_can_manage_modules(self, client, owner_headers):
        """Owner role has full module management permissions."""
        response = client.post(
            "/admin/modules/test/demo/enable", headers=owner_headers
        )
        assert response.status_code != 403


class TestModuleReloadAndUninstall:
    """Test reload and uninstall operations."""

    def test_reload_module_requires_permission(self, client, viewer_headers):
        """POST /admin/modules/{cat}/{plat}/reload forbidden for viewer."""
        response = client.post(
            "/admin/modules/test/demo/reload", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_reload_module_operator_allowed(self, client, operator_headers):
        """Operator can reload modules."""
        response = client.post(
            "/admin/modules/test/demo/reload", headers=operator_headers
        )
        # RBAC check passes (not 403), module doesn't exist → 500
        assert response.status_code != 403

    def test_uninstall_module_requires_permission(self, client, viewer_headers):
        """DELETE /admin/modules/{cat}/{plat} forbidden for viewer."""
        response = client.delete(
            "/admin/modules/test/demo", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_uninstall_module_operator_allowed(self, client, operator_headers):
        """Operator can uninstall modules."""
        response = client.delete(
            "/admin/modules/test/demo", headers=operator_headers
        )
        # RBAC check passes (not 403), module doesn't exist → 500
        assert response.status_code != 403


class TestModuleWithMockModule:
    """Test module operations with a fake installed module."""

    @pytest.fixture
    def installed_module(self, module_loader, tmp_path):
        """Create a minimal module for testing."""
        # Create module directory structure
        module_path = tmp_path / "modules" / "test" / "demo"
        module_path.mkdir(parents=True, exist_ok=True)

        # Create manifest.json
        manifest = {
            "version": "1.0.0",
            "category": "test",
            "platform": "demo",
            "name": "Demo Test Module",
            "description": "Test module for integration tests",
            "adapter_file": "adapter.py",
        }
        (module_path / "manifest.json").write_text(json.dumps(manifest, indent=2))

        # Create minimal adapter.py
        adapter_code = '''"""Test adapter."""
from shared.adapters.base import BaseAdapter, AdapterResult

class DemoAdapter(BaseAdapter):
    def fetch_raw(self):
        return {"status": "ok"}

    def transform(self, raw_data):
        return raw_data
'''
        (module_path / "adapter.py").write_text(adapter_code)

        return "test/demo"

    def test_list_modules_with_installed(self, client, admin_headers, installed_module, module_loader):
        """GET /admin/modules lists installed module."""
        # Load the module
        module_loader.load_module(installed_module)

        response = client.get("/admin/modules", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1

        # Find our test module
        test_mod = next(
            (m for m in body["modules"] if m.get("module_id") == installed_module),
            None
        )
        assert test_mod is not None
        assert test_mod["category"] == "test"
        assert test_mod["platform"] == "demo"

    def test_get_module_details(self, client, admin_headers, installed_module, module_loader):
        """GET /admin/modules/{cat}/{plat} returns module details."""
        module_loader.load_module(installed_module)

        response = client.get("/admin/modules/test/demo", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["module_id"] == "test/demo"
        assert body["category"] == "test"
        assert body["platform"] == "demo"
