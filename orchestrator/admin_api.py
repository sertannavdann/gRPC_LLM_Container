"""
Admin HTTP API for dynamic routing configuration and module management.

Runs as a FastAPI server in a daemon thread on port 8003.
Provides CRUD endpoints for hot-reloading routing config
and managing NEXUS dynamic modules without container restarts.
"""

import logging
import os
import threading

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from typing import Optional, Dict, Any, List

from shared.auth.api_keys import APIKeyStore
from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.models import User
from shared.auth.rbac import Permission, get_current_user, require_permission

from .config_manager import ConfigManager
from .routing_config import CategoryRouting, RoutingConfig

logger = logging.getLogger(__name__)

_app = FastAPI(title="Orchestrator Admin API", version="2.0")
_config_manager: Optional[ConfigManager] = None

# Module system references (set by start_admin_server)
_module_loader = None
_module_registry = None
_credential_store = None

# Auth (set by start_admin_server)
_api_key_store: Optional[APIKeyStore] = None

# CORS for UI access
_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_mgr() -> ConfigManager:
    if _config_manager is None:
        raise HTTPException(status_code=503, detail="ConfigManager not initialized")
    return _config_manager


def _check_module_credentials(module_id: str) -> bool:
    """Check if a module has credentials stored in the dashboard credential store."""
    import requests as http_req
    dashboard_url = __import__("os").getenv("DASHBOARD_URL", "http://dashboard:8001")
    try:
        parts = module_id.split("/", 1)
        if len(parts) != 2:
            return False
        resp = http_req.get(
            f"{dashboard_url}/admin/module-credentials/{parts[0]}/{parts[1]}/status",
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("has_credentials", False)
    except Exception:
        pass
    # Fallback: check local credential store if dashboard unreachable
    if _credential_store:
        return _credential_store.has_credentials(module_id)
    return False


# =============================================================================
# ROUTING CONFIG ENDPOINTS
# =============================================================================


@_app.get("/admin/health")
def health():
    module_count = 0
    if _module_loader:
        module_count = len(_module_loader.list_modules())
    return {
        "status": "ok",
        "modules_loaded": module_count,
        "config_manager": _config_manager is not None,
    }


@_app.get("/admin/routing-config")
def get_routing_config(user: User = Depends(get_current_user)):
    mgr = _get_mgr()
    return mgr.get_config().model_dump()


@_app.put("/admin/routing-config")
def put_routing_config(
    payload: RoutingConfig,
    user: User = Depends(require_permission(Permission.WRITE_CONFIG)),
):
    mgr = _get_mgr()
    mgr.update_config(payload)
    return {"status": "updated", "version": payload.version}


@_app.patch("/admin/routing-config/category/{name}")
def patch_category(
    name: str,
    payload: CategoryRouting,
    user: User = Depends(require_permission(Permission.WRITE_CONFIG)),
):
    mgr = _get_mgr()
    config = mgr.get_config().model_copy(deep=True)
    config.categories[name] = payload
    mgr.update_config(config)
    return {"status": "updated", "category": name, "tier": payload.tier}


@_app.delete("/admin/routing-config/category/{name}")
def delete_category(
    name: str,
    user: User = Depends(require_permission(Permission.WRITE_CONFIG)),
):
    mgr = _get_mgr()
    config = mgr.get_config().model_copy(deep=True)
    if name not in config.categories:
        raise HTTPException(status_code=404, detail=f"Category '{name}' not found")
    del config.categories[name]
    mgr.update_config(config)
    return {"status": "deleted", "category": name}


@_app.post("/admin/routing-config/reload")
def reload_config(user: User = Depends(require_permission(Permission.WRITE_CONFIG))):
    mgr = _get_mgr()
    config = mgr.reload()
    return {"status": "reloaded", "categories": len(config.categories)}


# =============================================================================
# MODULE MANAGEMENT ENDPOINTS
# =============================================================================


class ModuleCredentialRequest(BaseModel):
    """Request to store module credentials."""
    credentials: Dict[str, str]


class ModuleActionResponse(BaseModel):
    """Response from module actions."""
    success: bool
    module_id: str
    message: str


@_app.get("/admin/modules")
def list_modules(user: User = Depends(get_current_user)):
    """List all modules with status, health, and credential info."""
    if _module_loader is None:
        return {"modules": [], "total": 0}

    modules = _module_loader.list_modules()

    # Enrich with persistent registry and credential data
    enriched = []
    for mod in modules:
        module_id = f"{mod.get('category', 'unknown')}/{mod.get('platform', 'unknown')}"
        entry = {**mod, "module_id": module_id}

        # Add registry data if available
        if _module_registry:
            reg = _module_registry.get_module(module_id)
            if reg:
                entry["persistent_status"] = reg.get("status")
                entry["failure_count"] = reg.get("failure_count", 0)
                entry["success_count"] = reg.get("success_count", 0)
                entry["last_used"] = reg.get("last_used")

        # Add credential status (proxy to dashboard)
        entry["has_credentials"] = _check_module_credentials(module_id)

        enriched.append(entry)

    return {
        "modules": enriched,
        "total": len(enriched),
        "loaded": sum(1 for m in enriched if m.get("is_loaded")),
    }


@_app.get("/admin/modules/{category}/{platform}")
def get_module(category: str, platform: str, user: User = Depends(get_current_user)):
    """Get detailed information about a specific module."""
    module_id = f"{category}/{platform}"

    if _module_loader is None:
        raise HTTPException(status_code=503, detail="Module loader not initialized")

    # Check loader
    modules = _module_loader.list_modules()
    mod = next((m for m in modules if m.get("category") == category and m.get("platform") == platform), None)

    if mod is None:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

    result = {**mod, "module_id": module_id}

    # Registry data
    if _module_registry:
        reg = _module_registry.get_module(module_id)
        if reg:
            result["registry"] = reg

    # Credential status (proxy to dashboard)
    result["has_credentials"] = _check_module_credentials(module_id)

    return result


@_app.post("/admin/modules/{category}/{platform}/enable")
def enable_module(
    category: str,
    platform: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Enable a disabled module."""
    module_id = f"{category}/{platform}"

    if _module_loader is None:
        raise HTTPException(status_code=503, detail="Module loader not initialized")

    try:
        handle = _module_loader.enable_module(module_id)
        if _module_registry:
            _module_registry.enable(module_id)
        return ModuleActionResponse(
            success=handle.is_loaded,
            module_id=module_id,
            message=f"Module {module_id} enabled" if handle.is_loaded else f"Failed: {handle.error}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_app.post("/admin/modules/{category}/{platform}/disable")
def disable_module(
    category: str,
    platform: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Disable an active module."""
    module_id = f"{category}/{platform}"

    if _module_loader is None:
        raise HTTPException(status_code=503, detail="Module loader not initialized")

    try:
        _module_loader.disable_module(module_id)
        if _module_registry:
            _module_registry.disable(module_id)
        return ModuleActionResponse(
            success=True,
            module_id=module_id,
            message=f"Module {module_id} disabled",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_app.post("/admin/modules/{category}/{platform}/reload")
def reload_module(
    category: str,
    platform: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Reload a module (unload + load)."""
    module_id = f"{category}/{platform}"

    if _module_loader is None:
        raise HTTPException(status_code=503, detail="Module loader not initialized")

    try:
        handle = _module_loader.reload_module(module_id)
        return ModuleActionResponse(
            success=handle.is_loaded,
            module_id=module_id,
            message=f"Module {module_id} reloaded" if handle.is_loaded else f"Reload failed: {handle.error}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_app.delete("/admin/modules/{category}/{platform}")
def uninstall_module(
    category: str,
    platform: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Uninstall a module (unload + remove from registry)."""
    module_id = f"{category}/{platform}"

    if _module_loader is None:
        raise HTTPException(status_code=503, detail="Module loader not initialized")

    try:
        _module_loader.unload_module(module_id)
        if _module_registry:
            _module_registry.uninstall(module_id)
        # Delete credentials via dashboard proxy
        import requests as http_req
        dashboard_url = __import__("os").getenv("DASHBOARD_URL", "http://dashboard:8001")
        try:
            http_req.delete(
                f"{dashboard_url}/admin/module-credentials/{category}/{platform}",
                timeout=5,
            )
        except Exception:
            pass  # Best-effort cleanup
        return ModuleActionResponse(
            success=True,
            module_id=module_id,
            message=f"Module {module_id} uninstalled",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_app.post("/admin/modules/{category}/{platform}/credentials")
def store_credentials(
    category: str,
    platform: str,
    request: ModuleCredentialRequest,
    user: User = Depends(require_permission(Permission.MANAGE_CREDENTIALS)),
):
    """Store API credentials for a module — proxies to dashboard credential store."""
    import requests as http_req
    dashboard_url = __import__("os").getenv("DASHBOARD_URL", "http://dashboard:8001")

    try:
        resp = http_req.post(
            f"{dashboard_url}/admin/module-credentials/{category}/{platform}",
            json={"credentials": request.credentials},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()

        # Reload module to pick up credentials
        if _module_loader:
            try:
                _module_loader.reload_module(f"{category}/{platform}")
            except Exception:
                pass

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@_app.delete("/admin/modules/{category}/{platform}/credentials")
def delete_credentials(
    category: str,
    platform: str,
    user: User = Depends(require_permission(Permission.MANAGE_CREDENTIALS)),
):
    """Remove stored credentials for a module — proxies to dashboard credential store."""
    import requests as http_req
    dashboard_url = __import__("os").getenv("DASHBOARD_URL", "http://dashboard:8001")

    try:
        resp = http_req.delete(
            f"{dashboard_url}/admin/module-credentials/{category}/{platform}",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SYSTEM INFO ENDPOINT (for UI settings page)
# =============================================================================


@_app.get("/admin/system-info")
def system_info(user: User = Depends(get_current_user)):
    """Return system configuration for the settings UI."""
    mgr = _get_mgr()
    config = mgr.get_config()

    return {
        "routing": {
            "categories": {name: cat.model_dump() for name, cat in config.categories.items()},
            "tiers": {name: tier.model_dump() for name, tier in config.tiers.items()},
            "performance": config.performance.model_dump(),
        },
        "modules": {
            "total": len(_module_loader.list_modules()) if _module_loader else 0,
            "loaded": sum(1 for m in (_module_loader.list_modules() if _module_loader else []) if m.get("is_loaded")),
        },
        "adapters": {
            "count": len(list(_module_loader.list_modules())) if _module_loader else 0,
        },
    }


# =============================================================================
# PROVIDER & RELOAD ENDPOINTS
# =============================================================================


@_app.get("/admin/providers")
def get_providers(user: User = Depends(get_current_user)):
    """Return provider/model lists and LIDM tier models from routing config."""
    mgr = _get_mgr()
    config = mgr.get_config()
    # Read the raw JSON file for providers/lidm_tier_models (not in Pydantic model)
    import json
    providers = {}
    lidm_tier_models = {}
    try:
        raw_data = json.loads(mgr._config_path.read_text())
        providers = raw_data.get("providers", {})
        lidm_tier_models = raw_data.get("lidm_tier_models", {})
    except Exception:
        pass

    # Also build tier→model mapping from config.tiers
    tiers = {}
    for name, tier in config.tiers.items():
        tiers[name] = {
            "endpoint": tier.endpoint,
            "models": lidm_tier_models.get(name, []),
            "enabled": tier.enabled,
        }

    return {
        "providers": providers,
        "lidm_tier_models": lidm_tier_models,
        "tiers": tiers,
    }


@_app.post("/admin/reload")
def reload_system(user: User = Depends(require_permission(Permission.WRITE_CONFIG))):
    """Reload routing config and signal LLM clients to reconnect."""
    mgr = _get_mgr()
    config = mgr.reload()

    # Notify all observers (LLMClientPool, DelegationManager, etc.)
    # The reload() already triggers observer callbacks via ConfigManager

    return {
        "status": "reloaded",
        "categories": len(config.categories),
        "tiers": len(config.tiers),
        "message": "Config reloaded. LLM clients will reconnect on next request.",
    }


# ── Server launcher ──────────────────────────────────────────────────────────


# =============================================================================
# AUTH BOOTSTRAP & API KEY MANAGEMENT
# =============================================================================


class CreateKeyRequest(BaseModel):
    """Request to create a new API key."""
    org_id: str
    role: str = "viewer"


@_app.post("/admin/bootstrap")
def bootstrap_admin_key():
    """Create initial admin key. Only works when no keys exist."""
    if _api_key_store is None:
        raise HTTPException(503, "Auth not initialized")
    with _api_key_store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    if count > 0:
        raise HTTPException(
            403,
            "Bootstrap already complete. Use existing admin key to create new keys.",
        )
    org = _api_key_store.create_organization("default", "Default Organization")
    key, key_id = _api_key_store.create_key("default", "owner")
    return {
        "api_key": key,
        "key_id": key_id,
        "org_id": "default",
        "role": "owner",
        "warning": "Store this key securely. It will not be shown again.",
    }


@_app.post("/admin/api-keys")
def create_api_key(
    request: CreateKeyRequest,
    user: User = Depends(require_permission(Permission.MANAGE_KEYS)),
):
    """Create a new API key for an organization."""
    if _api_key_store is None:
        raise HTTPException(503, "Auth not initialized")
    key, key_id = _api_key_store.create_key(request.org_id, request.role)
    return {
        "api_key": key,
        "key_id": key_id,
        "org_id": request.org_id,
        "role": request.role,
        "warning": "Store this key securely. It will not be shown again.",
    }


@_app.get("/admin/api-keys")
def list_api_keys(user: User = Depends(require_permission(Permission.MANAGE_KEYS))):
    """List all API keys for the authenticated user's organization."""
    if _api_key_store is None:
        raise HTTPException(503, "Auth not initialized")
    keys = _api_key_store.list_keys(user.org_id)
    return {"keys": [k.model_dump() for k in keys], "total": len(keys)}


@_app.delete("/admin/api-keys/{key_id}")
def revoke_api_key(
    key_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_KEYS)),
):
    """Revoke an API key."""
    if _api_key_store is None:
        raise HTTPException(503, "Auth not initialized")
    revoked = _api_key_store.revoke_key(key_id)
    if not revoked:
        raise HTTPException(404, f"Key {key_id} not found")
    return {"success": True, "key_id": key_id, "message": "Key revoked"}


@_app.post("/admin/api-keys/{key_id}/rotate")
def rotate_api_key(
    key_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_KEYS)),
):
    """Rotate an API key with dual-key overlap."""
    if _api_key_store is None:
        raise HTTPException(503, "Auth not initialized")
    try:
        new_key, new_key_id = _api_key_store.rotate_key(user.org_id, key_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "new_api_key": new_key,
        "new_key_id": new_key_id,
        "old_key_id": key_id,
        "warning": "Store the new key securely. Old key valid during grace period.",
    }


def start_admin_server(
    config_manager: ConfigManager,
    port: int = 8003,
    module_loader=None,
    module_registry=None,
    credential_store=None,
    api_key_store: Optional[APIKeyStore] = None,
) -> None:
    """Start admin API in a daemon thread. Safe to call from gRPC serve()."""
    global _config_manager, _module_loader, _module_registry, _credential_store, _api_key_store
    _config_manager = config_manager
    _module_loader = module_loader
    _module_registry = module_registry
    _credential_store = credential_store

    # Initialize auth
    _api_key_store = api_key_store or APIKeyStore(
        db_path=os.getenv("AUTH_DB_PATH", "data/api_keys.db")
    )
    _app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=_api_key_store,
        public_paths=[
            "/admin/health",
            "/admin/bootstrap",
            "/docs",
            "/openapi.json",
            "/redoc",
        ],
    )

    def _run():
        # Use Config + Server so we can disable signal handlers
        # (gRPC owns signals; uvicorn.run() no longer accepts that kwarg)
        config = uvicorn.Config(
            _app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = False
        server.run()

    thread = threading.Thread(target=_run, name="admin-api", daemon=True)
    thread.start()
    logger.info(f"Admin API started on port {port} (daemon thread)")
