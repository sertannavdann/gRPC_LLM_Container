"""
Config hot-reload integration tests for Admin API.

Tests the following endpoints:
- GET /admin/routing-config — get current routing configuration
- PUT /admin/routing-config — update entire configuration
- PATCH /admin/routing-config/category/{name} — update single category
- DELETE /admin/routing-config/category/{name} — delete category
- POST /admin/routing-config/reload — reload config from disk

All tests use FastAPI TestClient (in-process, no Docker).
"""
import pytest


class TestConfigHotReload:
    """Test routing config CRUD operations."""

    def test_get_routing_config(self, client, admin_headers):
        """GET /admin/routing-config returns valid config structure."""
        response = client.get("/admin/routing-config", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert "version" in body
        assert "categories" in body
        assert "tiers" in body
        assert "performance" in body

    def test_get_routing_config_requires_auth(self, client):
        """GET /admin/routing-config requires authentication."""
        response = client.get("/admin/routing-config")
        assert response.status_code == 401

    def test_put_routing_config(self, client, admin_headers, config_manager):
        """PUT /admin/routing-config updates entire configuration."""
        # Get current config
        current = config_manager.get_config()

        # Modify it
        new_config = current.model_copy(deep=True)
        new_config.version = "1.1"

        # Send update
        response = client.put(
            "/admin/routing-config",
            headers=admin_headers,
            json=new_config.model_dump(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "updated"
        assert response.json()["version"] == "1.1"

        # Verify it persisted
        updated = config_manager.get_config()
        assert updated.version == "1.1"

    def test_put_routing_config_viewer_forbidden(self, client, viewer_headers, config_manager):
        """PUT /admin/routing-config forbidden for viewer role (no WRITE_CONFIG)."""
        current = config_manager.get_config()
        response = client.put(
            "/admin/routing-config",
            headers=viewer_headers,
            json=current.model_dump(),
        )
        assert response.status_code == 403

    def test_patch_category(self, client, admin_headers, config_manager):
        """PATCH /admin/routing-config/category/{name} updates single category."""
        from orchestrator.routing_config import CategoryRouting

        new_category = CategoryRouting(tier="heavy", priority="high")
        response = client.patch(
            "/admin/routing-config/category/general",
            headers=admin_headers,
            json=new_category.model_dump(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "updated"
        assert response.json()["tier"] == "heavy"

        # Verify it persisted
        updated = config_manager.get_config()
        assert updated.categories["general"].tier == "heavy"
        assert updated.categories["general"].priority == "high"

    def test_patch_category_viewer_forbidden(self, client, viewer_headers):
        """PATCH /admin/routing-config/category/{name} forbidden for viewer."""
        from orchestrator.routing_config import CategoryRouting

        new_category = CategoryRouting(tier="heavy", priority="high")
        response = client.patch(
            "/admin/routing-config/category/general",
            headers=viewer_headers,
            json=new_category.model_dump(),
        )
        assert response.status_code == 403

    def test_delete_category(self, client, admin_headers, config_manager):
        """DELETE /admin/routing-config/category/{name} removes category."""
        # First verify it exists
        config = config_manager.get_config()
        assert "general" in config.categories

        # Delete it
        response = client.delete(
            "/admin/routing-config/category/general",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

        # Verify it's gone
        updated = config_manager.get_config()
        assert "general" not in updated.categories

    def test_delete_category_not_found(self, client, admin_headers):
        """DELETE /admin/routing-config/category/{name} returns 404 for nonexistent category."""
        response = client.delete(
            "/admin/routing-config/category/nonexistent",
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_category_viewer_forbidden(self, client, viewer_headers):
        """DELETE /admin/routing-config/category/{name} forbidden for viewer."""
        response = client.delete(
            "/admin/routing-config/category/general",
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_reload_config(self, client, admin_headers, config_manager, tmp_databases):
        """POST /admin/routing-config/reload reloads config from disk."""
        from pathlib import Path
        import json

        # Manually edit the config file on disk
        config_path = Path(tmp_databases["routing_config"])
        data = json.loads(config_path.read_text())
        data["version"] = "2.0"
        config_path.write_text(json.dumps(data, indent=2))

        # Reload via endpoint
        response = client.post("/admin/routing-config/reload", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "reloaded"

        # Verify the reload worked
        updated = config_manager.get_config()
        assert updated.version == "2.0"

    def test_reload_config_viewer_forbidden(self, client, viewer_headers):
        """POST /admin/routing-config/reload forbidden for viewer."""
        response = client.post("/admin/routing-config/reload", headers=viewer_headers)
        assert response.status_code == 403


class TestConfigPermissions:
    """Test RBAC enforcement on config endpoints."""

    def test_viewer_can_read_config(self, client, viewer_headers):
        """Viewer role can read config (get_current_user permission)."""
        response = client.get("/admin/routing-config", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_cannot_write_config(self, client, viewer_headers, config_manager):
        """Viewer role cannot write config (no WRITE_CONFIG permission)."""
        current = config_manager.get_config()
        response = client.put(
            "/admin/routing-config",
            headers=viewer_headers,
            json=current.model_dump(),
        )
        assert response.status_code == 403

    def test_operator_cannot_write_config(self, client, operator_headers, config_manager):
        """Operator role cannot write config (no WRITE_CONFIG permission)."""
        current = config_manager.get_config()
        response = client.put(
            "/admin/routing-config",
            headers=operator_headers,
            json=current.model_dump(),
        )
        assert response.status_code == 403

    def test_admin_can_write_config(self, client, admin_headers, config_manager):
        """Admin role can write config (has WRITE_CONFIG permission)."""
        current = config_manager.get_config()
        new_config = current.model_copy(deep=True)
        new_config.version = "1.2"
        response = client.put(
            "/admin/routing-config",
            headers=admin_headers,
            json=new_config.model_dump(),
        )
        assert response.status_code == 200

    def test_owner_can_write_config(self, client, owner_headers, config_manager):
        """Owner role can write config."""
        current = config_manager.get_config()
        new_config = current.model_copy(deep=True)
        new_config.version = "1.3"
        response = client.put(
            "/admin/routing-config",
            headers=owner_headers,
            json=new_config.model_dump(),
        )
        assert response.status_code == 200
