"""
Shared fixtures for Admin API integration tests.

Provides TestClient wired with auth middleware, isolated databases,
and API keys for all roles (viewer, operator, admin, owner).
"""
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Depends
from starlette.testclient import TestClient

# Import the components we need directly (avoiding orchestrator/__init__.py)
from orchestrator.config_manager import ConfigManager
from orchestrator.routing_config import RoutingConfig, CategoryRouting, TierConfig, PerformanceConstraints
from shared.auth.api_keys import APIKeyStore
from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.models import Role, User
from shared.auth.rbac import Permission, get_current_user, require_permission
from shared.billing import QuotaManager, UsageStore
from shared.modules.credentials import CredentialStore
from shared.modules.loader import ModuleLoader
from shared.modules.registry import ModuleRegistry

# We need to re-create the admin API app here to avoid importing orchestrator package
# This is a simplified version that includes only what we need for testing


def create_test_admin_app():
    """Create a minimal admin API app for testing."""
    app = FastAPI(title="Test Admin API")

    # Module-level state (will be injected by fixtures)
    app.state.config_manager = None
    app.state.module_loader = None
    app.state.module_registry = None
    app.state.credential_store = None
    app.state.api_key_store = None
    app.state.usage_store = None
    app.state.quota_manager = None

    # Health endpoint
    @app.get("/admin/health")
    def health():
        module_count = 0
        if app.state.module_loader:
            module_count = len(app.state.module_loader.list_modules())
        return {
            "status": "ok",
            "modules_loaded": module_count,
            "config_manager": app.state.config_manager is not None,
        }

    # Module list endpoint
    @app.get("/admin/modules")
    def list_modules(user: User = Depends(get_current_user)):
        if app.state.module_loader is None:
            return {"modules": [], "total": 0}

        modules = app.state.module_loader.list_modules()
        enriched = []
        for mod in modules:
            module_id = f"{mod.get('category', 'unknown')}/{mod.get('platform', 'unknown')}"
            entry = {**mod, "module_id": module_id}
            if app.state.module_registry:
                reg = app.state.module_registry.get_module(module_id)
                if reg:
                    entry["persistent_status"] = reg.get("status")
                    entry["failure_count"] = reg.get("failure_count", 0)
            entry["has_credentials"] = False  # Simplified for testing
            enriched.append(entry)

        return {"modules": enriched, "total": len(enriched), "loaded": sum(1 for m in enriched if m.get("is_loaded"))}

    # Get module details
    @app.get("/admin/modules/{category}/{platform}")
    def get_module(category: str, platform: str, user: User = Depends(get_current_user)):
        from fastapi import HTTPException
        module_id = f"{category}/{platform}"
        if app.state.module_loader is None:
            raise HTTPException(status_code=503, detail="Module loader not initialized")

        modules = app.state.module_loader.list_modules()
        mod = next((m for m in modules if m.get("category") == category and m.get("platform") == platform), None)
        if mod is None:
            raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

        result = {**mod, "module_id": module_id}
        if app.state.module_registry:
            reg = app.state.module_registry.get_module(module_id)
            if reg:
                result["registry"] = reg
        result["has_credentials"] = False
        return result

    # Enable module
    @app.post("/admin/modules/{category}/{platform}/enable")
    def enable_module(category: str, platform: str, user: User = Depends(require_permission(Permission.MANAGE_MODULES))):
        from fastapi import HTTPException
        from pydantic import BaseModel

        class ModuleActionResponse(BaseModel):
            success: bool
            module_id: str
            message: str

        module_id = f"{category}/{platform}"
        if app.state.module_loader is None:
            raise HTTPException(status_code=503, detail="Module loader not initialized")
        try:
            handle = app.state.module_loader.enable_module(module_id)
            if app.state.module_registry:
                app.state.module_registry.enable(module_id)
            return ModuleActionResponse(
                success=handle.is_loaded,
                module_id=module_id,
                message=f"Module {module_id} enabled" if handle.is_loaded else f"Failed: {handle.error}",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Disable module
    @app.post("/admin/modules/{category}/{platform}/disable")
    def disable_module(category: str, platform: str, user: User = Depends(require_permission(Permission.MANAGE_MODULES))):
        from fastapi import HTTPException
        from pydantic import BaseModel

        class ModuleActionResponse(BaseModel):
            success: bool
            module_id: str
            message: str

        module_id = f"{category}/{platform}"
        if app.state.module_loader is None:
            raise HTTPException(status_code=503, detail="Module loader not initialized")
        try:
            app.state.module_loader.disable_module(module_id)
            if app.state.module_registry:
                app.state.module_registry.disable(module_id)
            return ModuleActionResponse(success=True, module_id=module_id, message=f"Module {module_id} disabled")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Reload module
    @app.post("/admin/modules/{category}/{platform}/reload")
    def reload_module(category: str, platform: str, user: User = Depends(require_permission(Permission.MANAGE_MODULES))):
        from fastapi import HTTPException
        from pydantic import BaseModel

        class ModuleActionResponse(BaseModel):
            success: bool
            module_id: str
            message: str

        module_id = f"{category}/{platform}"
        if app.state.module_loader is None:
            raise HTTPException(status_code=503, detail="Module loader not initialized")
        try:
            handle = app.state.module_loader.reload_module(module_id)
            return ModuleActionResponse(
                success=handle.is_loaded,
                module_id=module_id,
                message=f"Module {module_id} reloaded" if handle.is_loaded else f"Reload failed: {handle.error}",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Uninstall module
    @app.delete("/admin/modules/{category}/{platform}")
    def uninstall_module(category: str, platform: str, user: User = Depends(require_permission(Permission.MANAGE_MODULES))):
        from fastapi import HTTPException
        from pydantic import BaseModel

        class ModuleActionResponse(BaseModel):
            success: bool
            module_id: str
            message: str

        module_id = f"{category}/{platform}"
        if app.state.module_loader is None:
            raise HTTPException(status_code=503, detail="Module loader not initialized")
        try:
            app.state.module_loader.unload_module(module_id)
            if app.state.module_registry:
                app.state.module_registry.uninstall(module_id)
            return ModuleActionResponse(success=True, module_id=module_id, message=f"Module {module_id} uninstalled")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Routing config endpoints
    @app.get("/admin/routing-config")
    def get_routing_config(user: User = Depends(get_current_user)):
        from fastapi import HTTPException
        if app.state.config_manager is None:
            raise HTTPException(status_code=503, detail="ConfigManager not initialized")
        return app.state.config_manager.get_config().model_dump()

    @app.put("/admin/routing-config")
    def put_routing_config(payload: RoutingConfig, user: User = Depends(require_permission(Permission.WRITE_CONFIG))):
        from fastapi import HTTPException
        if app.state.config_manager is None:
            raise HTTPException(status_code=503, detail="ConfigManager not initialized")
        app.state.config_manager.update_config(payload)
        return {"status": "updated", "version": payload.version}

    @app.patch("/admin/routing-config/category/{name}")
    def patch_category(name: str, payload: CategoryRouting, user: User = Depends(require_permission(Permission.WRITE_CONFIG))):
        from fastapi import HTTPException
        if app.state.config_manager is None:
            raise HTTPException(status_code=503, detail="ConfigManager not initialized")
        config = app.state.config_manager.get_config().model_copy(deep=True)
        config.categories[name] = payload
        app.state.config_manager.update_config(config)
        return {"status": "updated", "category": name, "tier": payload.tier}

    @app.delete("/admin/routing-config/category/{name}")
    def delete_category(name: str, user: User = Depends(require_permission(Permission.WRITE_CONFIG))):
        from fastapi import HTTPException
        if app.state.config_manager is None:
            raise HTTPException(status_code=503, detail="ConfigManager not initialized")
        config = app.state.config_manager.get_config().model_copy(deep=True)
        if name not in config.categories:
            raise HTTPException(status_code=404, detail=f"Category '{name}' not found")
        del config.categories[name]
        app.state.config_manager.update_config(config)
        return {"status": "deleted", "category": name}

    @app.post("/admin/routing-config/reload")
    def reload_config(user: User = Depends(require_permission(Permission.WRITE_CONFIG))):
        from fastapi import HTTPException
        if app.state.config_manager is None:
            raise HTTPException(status_code=503, detail="ConfigManager not initialized")
        config = app.state.config_manager.reload()
        return {"status": "reloaded", "categories": len(config.categories)}

    # Billing endpoints
    @app.get("/admin/billing/usage")
    def get_billing_usage(period: str = None, user: User = Depends(get_current_user)):
        from fastapi import HTTPException
        if app.state.usage_store is None:
            raise HTTPException(status_code=503, detail="Billing not initialized")
        return app.state.usage_store.get_usage_summary(user.org_id, period)

    @app.get("/admin/billing/usage/history")
    def get_billing_history(start_date: str = None, end_date: str = None, limit: int = 100, user: User = Depends(get_current_user)):
        from fastapi import HTTPException
        if app.state.usage_store is None:
            raise HTTPException(status_code=503, detail="Billing not initialized")
        records = app.state.usage_store.get_usage_history(
            user.org_id,
            start_date=start_date,
            end_date=end_date,
            limit=min(limit, 1000),
        )
        return {"records": records, "count": len(records)}

    @app.get("/admin/billing/quota")
    def get_billing_quota(user: User = Depends(get_current_user)):
        from fastapi import HTTPException
        if app.state.quota_manager is None:
            raise HTTPException(status_code=503, detail="Billing not initialized")
        result = app.state.quota_manager.check_quota(user.org_id)
        return result.model_dump()

    return app


@pytest.fixture
def tmp_databases(tmp_path):
    """Create isolated SQLite databases for testing."""
    return {
        "auth": str(tmp_path / "auth.db"),
        "billing": str(tmp_path / "billing.db"),
        "registry": str(tmp_path / "registry.db"),
        "credentials": str(tmp_path / "credentials.db"),
        "routing_config": str(tmp_path / "routing_config.json"),
    }


@pytest.fixture
def api_key_store(tmp_databases):
    """Create an isolated APIKeyStore for testing."""
    return APIKeyStore(db_path=tmp_databases["auth"])


@pytest.fixture
def usage_store(tmp_databases):
    """Create an isolated UsageStore for testing."""
    return UsageStore(db_path=tmp_databases["billing"])


@pytest.fixture
def quota_manager(usage_store, api_key_store):
    """Create a QuotaManager with test stores."""
    return QuotaManager(
        usage_store=usage_store,
        api_key_store=api_key_store,
    )


@pytest.fixture
def module_registry(tmp_databases):
    """Create an isolated ModuleRegistry for testing."""
    return ModuleRegistry(db_path=tmp_databases["registry"])


@pytest.fixture
def credential_store(tmp_databases, monkeypatch):
    """Create an isolated CredentialStore for testing."""
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key()
    # Set encryption key via environment
    monkeypatch.setenv("MODULE_ENCRYPTION_KEY", test_key.decode())
    return CredentialStore(db_path=tmp_databases["credentials"])


@pytest.fixture
def config_manager(tmp_databases):
    """Create a ConfigManager with temp routing config."""
    config_path = Path(tmp_databases["routing_config"])
    minimal_config = {
        "version": "1.0",
        "categories": {
            "general": {"tier": "standard", "priority": "medium"},
            "code": {"tier": "heavy", "priority": "high"},
        },
        "tiers": {
            "standard": {"endpoint": "llm_service:50051", "priority": 2, "enabled": True},
            "heavy": {"endpoint": "llm_service:50051", "priority": 1, "enabled": True},
        },
        "performance": {
            "max_tokens": 8192,
            "timeout_seconds": 120,
            "max_retries": 3,
        },
    }
    config_path.write_text(json.dumps(minimal_config, indent=2))
    return ConfigManager(config_path=str(config_path))


@pytest.fixture
def module_loader(tmp_path):
    """Create a ModuleLoader with isolated module directory."""
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir(exist_ok=True)
    return ModuleLoader(modules_dir=modules_dir)


@pytest.fixture
def admin_app(
    config_manager,
    module_loader,
    module_registry,
    credential_store,
    api_key_store,
    usage_store,
    quota_manager,
):
    """Configure the Admin API app with test dependencies."""
    app = create_test_admin_app()

    # Inject test dependencies
    app.state.config_manager = config_manager
    app.state.module_loader = module_loader
    app.state.module_registry = module_registry
    app.state.credential_store = credential_store
    app.state.api_key_store = api_key_store
    app.state.usage_store = usage_store
    app.state.quota_manager = quota_manager

    # Add auth middleware
    app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=api_key_store,
        public_paths=["/admin/health"],
    )

    return app


@pytest.fixture
def client(admin_app):
    """Create a TestClient for the Admin API."""
    return TestClient(admin_app)


@pytest.fixture
def test_org(api_key_store):
    """Create a test organization."""
    return api_key_store.create_organization("test-org", "Test Organization")


@pytest.fixture
def admin_headers(api_key_store, test_org):
    """Create admin API key and return headers."""
    plaintext_key, _ = api_key_store.create_key(test_org.org_id, "admin")
    return {"X-API-Key": plaintext_key}


@pytest.fixture
def operator_headers(api_key_store, test_org):
    """Create operator API key and return headers."""
    plaintext_key, _ = api_key_store.create_key(test_org.org_id, "operator")
    return {"X-API-Key": plaintext_key}


@pytest.fixture
def viewer_headers(api_key_store, test_org):
    """Create viewer API key and return headers."""
    plaintext_key, _ = api_key_store.create_key(test_org.org_id, "viewer")
    return {"X-API-Key": plaintext_key}


@pytest.fixture
def owner_headers(api_key_store, test_org):
    """Create owner API key and return headers."""
    plaintext_key, _ = api_key_store.create_key(test_org.org_id, "owner")
    return {"X-API-Key": plaintext_key}
