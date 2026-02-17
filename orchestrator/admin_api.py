"""
Admin HTTP API for dynamic routing configuration and module management.

Runs as a FastAPI server in a daemon thread on port 8003.
Provides CRUD endpoints for hot-reloading routing config
and managing NEXUS dynamic modules without container restarts.
"""

import logging
import os
import re
import subprocess
import threading
import time

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from typing import Optional, Dict, Any, List

from shared.auth.api_keys import APIKeyStore
from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.models import User
from shared.auth.rbac import Permission, get_current_user, require_permission
from shared.billing import UsageStore, QuotaManager

from .config_manager import ConfigManager
from .routing_config import CategoryRouting, RoutingConfig
from tools.builtin.chart_validator import validate_chart, ChartValidationResult

logger = logging.getLogger(__name__)

_app = FastAPI(title="Orchestrator Admin API", version="2.0")
_config_manager: Optional[ConfigManager] = None

# Module system references (set by start_admin_server)
_module_loader = None
_module_registry = None
_credential_store = None

# Auth (set by start_admin_server)
_api_key_store: Optional[APIKeyStore] = None

# Billing (set by start_admin_server)
_usage_store: Optional[UsageStore] = None
_quota_manager: Optional[QuotaManager] = None

# Dev-mode (set by start_admin_server)
_draft_manager = None
_version_manager = None

# Chart artifacts (set by start_admin_server)
_artifacts_dir = None

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


def _dashboard_auth_headers(forwarded_api_key: Optional[str] = None) -> Dict[str, str]:
    """Build auth headers for orchestrator->dashboard proxy calls."""
    api_key = forwarded_api_key or os.getenv("DASHBOARD_API_KEY") or os.getenv("INTERNAL_API_KEY")
    if not api_key:
        return {}
    return {"X-API-Key": api_key}


def _check_module_credentials(module_id: str, forwarded_api_key: Optional[str] = None) -> bool:
    """Check if a module has credentials stored in the dashboard credential store."""
    import requests as http_req
    dashboard_url = os.getenv("DASHBOARD_URL", "http://dashboard:8001")
    try:
        parts = module_id.split("/", 1)
        if len(parts) != 2:
            return False
        resp = http_req.get(
            f"{dashboard_url}/admin/module-credentials/{parts[0]}/{parts[1]}/status",
            headers=_dashboard_auth_headers(forwarded_api_key),
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
def list_modules(request: Request, user: User = Depends(get_current_user)):
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
        entry["has_credentials"] = _check_module_credentials(module_id, request.headers.get("X-API-Key"))

        enriched.append(entry)

    return {
        "modules": enriched,
        "total": len(enriched),
        "loaded": sum(1 for m in enriched if m.get("is_loaded")),
    }


@_app.get("/admin/modules/{category}/{platform}")
def get_module(category: str, platform: str, request: Request, user: User = Depends(get_current_user)):
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
    result["has_credentials"] = _check_module_credentials(module_id, request.headers.get("X-API-Key"))

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


class TestRunResult(BaseModel):
    module_id: str
    exit_code: int
    tests_total: int
    tests_passed: int
    tests_failed: int
    stdout: str
    stderr: str
    duration_ms: float


@_app.post("/admin/modules/{category}/{platform}/run-tests")
def run_module_tests(
    category: str,
    platform: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Run a module's test_adapter.py and return results."""
    module_id = f"{category}/{platform}"
    modules_dir = os.getenv("MODULES_DIR", "modules")
    test_file = os.path.join(modules_dir, category, platform, "test_adapter.py")

    if not os.path.isfile(test_file):
        raise HTTPException(status_code=404, detail=f"No test file found for {module_id}")

    start = time.monotonic()
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", test_file, "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.path.dirname(os.path.dirname(modules_dir)) or ".",
        )
    except subprocess.TimeoutExpired:
        return TestRunResult(
            module_id=module_id,
            exit_code=124,
            tests_total=0,
            tests_passed=0,
            tests_failed=0,
            stdout="",
            stderr="Test execution timed out (60s limit)",
            duration_ms=(time.monotonic() - start) * 1000,
        )

    elapsed = (time.monotonic() - start) * 1000
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    # Parse pytest summary line (e.g. "3 passed, 1 failed")
    passed = 0
    failed = 0
    for line in stdout.splitlines():
        line_lower = line.strip().lower()
        if "passed" in line_lower or "failed" in line_lower:
            p = re.search(r"(\d+)\s+passed", line_lower)
            f = re.search(r"(\d+)\s+failed", line_lower)
            if p:
                passed = int(p.group(1))
            if f:
                failed = int(f.group(1))

    return TestRunResult(
        module_id=module_id,
        exit_code=result.returncode,
        tests_total=passed + failed,
        tests_passed=passed,
        tests_failed=failed,
        stdout=stdout,
        stderr=stderr,
        duration_ms=elapsed,
    )


@_app.delete("/admin/modules/{category}/{platform}")
def uninstall_module(
    category: str,
    platform: str,
    request: Request,
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
        dashboard_url = os.getenv("DASHBOARD_URL", "http://dashboard:8001")
        try:
            http_req.delete(
                f"{dashboard_url}/admin/module-credentials/{category}/{platform}",
                headers=_dashboard_auth_headers(request.headers.get("X-API-Key")),
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
    http_request: Request,
    user: User = Depends(require_permission(Permission.MANAGE_CREDENTIALS)),
):
    """Store API credentials for a module — proxies to dashboard credential store."""
    import requests as http_req
    dashboard_url = os.getenv("DASHBOARD_URL", "http://dashboard:8001")

    try:
        resp = http_req.post(
            f"{dashboard_url}/admin/module-credentials/{category}/{platform}",
            json={"credentials": request.credentials},
            headers=_dashboard_auth_headers(http_request.headers.get("X-API-Key")),
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
    request: Request,
    user: User = Depends(require_permission(Permission.MANAGE_CREDENTIALS)),
):
    """Remove stored credentials for a module — proxies to dashboard credential store."""
    import requests as http_req
    dashboard_url = os.getenv("DASHBOARD_URL", "http://dashboard:8001")

    try:
        resp = http_req.delete(
            f"{dashboard_url}/admin/module-credentials/{category}/{platform}",
            headers=_dashboard_auth_headers(request.headers.get("X-API-Key")),
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
def get_providers():
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


# =============================================================================
# DEV-MODE ENDPOINTS: DRAFT / PROMOTE / ROLLBACK
# =============================================================================

# Module-level references (set by start_admin_server)
_draft_manager = None
_version_manager = None


class DraftCreateRequest(BaseModel):
    """Request to create a draft from installed module."""
    from_version: str = "active"


class DraftEditRequest(BaseModel):
    """Request to edit a file in draft."""
    file_path: str
    content: str


class RollbackRequest(BaseModel):
    """Request to rollback to prior version."""
    target_version: str
    reason: str = ""


@_app.post("/admin/modules/{category}/{platform}/draft")
def create_draft(
    category: str,
    platform: str,
    request: DraftCreateRequest,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Create a draft from installed module (operator+ role)."""
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    module_id = f"{category}/{platform}"

    result = _draft_manager.create_draft(
        module_id=module_id,
        from_version=request.from_version,
        actor=user.org_id
    )

    if result.get("status") != "success":
        raise HTTPException(400, result.get("error", "Draft creation failed"))

    return result


@_app.patch("/admin/modules/drafts/{draft_id}")
def edit_draft_file(
    draft_id: str,
    request: DraftEditRequest,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Edit a file in draft (operator+ role)."""
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.edit_file(
        draft_id=draft_id,
        file_path=request.file_path,
        content=request.content,
        actor=user.org_id
    )

    if result.get("status") != "success":
        raise HTTPException(400, result.get("error", "Edit failed"))

    return result


@_app.get("/admin/modules/drafts/{draft_id}/diff")
def get_draft_diff(
    draft_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """View diff between draft and source (operator+ role)."""
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.get_diff(draft_id=draft_id, actor=user.org_id)

    if result.get("status") != "success":
        raise HTTPException(400, result.get("error", "Diff failed"))

    return result


@_app.post("/admin/modules/drafts/{draft_id}/validate")
def validate_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.WRITE_CONFIG)),  # admin+ role
):
    """Trigger sandbox validation on draft (admin+ role)."""
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.validate_draft(draft_id=draft_id, actor=user.org_id)

    if result.get("status") not in ["success", "failed"]:
        raise HTTPException(400, result.get("error", "Validation error"))

    return result


@_app.post("/admin/modules/drafts/{draft_id}/promote")
def promote_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.WRITE_CONFIG)),  # admin+ role
):
    """Promote validated draft to new version (admin+ role)."""
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.promote_draft(draft_id=draft_id, actor=user.org_id)

    if result.get("status") != "success":
        raise HTTPException(400, result.get("error", "Promotion failed"))

    return result


@_app.delete("/admin/modules/drafts/{draft_id}")
def discard_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """Discard a draft (operator+ role)."""
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.discard_draft(draft_id=draft_id, actor=user.org_id)

    if result.get("status") != "success":
        raise HTTPException(400, result.get("error", "Discard failed"))

    return result


@_app.post("/admin/modules/{category}/{platform}/rollback")
def rollback_module(
    category: str,
    platform: str,
    request: RollbackRequest,
    user: User = Depends(require_permission(Permission.WRITE_CONFIG)),  # admin+ role
):
    """Rollback module to prior version (admin+ role)."""
    if _version_manager is None:
        raise HTTPException(503, "Version manager not initialized")

    module_id = f"{category}/{platform}"

    result = _version_manager.rollback_to_version(
        module_id=module_id,
        target_version_id=request.target_version,
        actor=user.org_id,
        reason=request.reason
    )

    if result.get("status") != "success":
        raise HTTPException(400, result.get("error", "Rollback failed"))

    return result


@_app.get("/admin/modules/{category}/{platform}/versions")
def list_module_versions(
    category: str,
    platform: str,
    user: User = Depends(get_current_user),  # viewer+ role
):
    """List all validated versions for a module (viewer+ role)."""
    if _version_manager is None:
        raise HTTPException(503, "Version manager not initialized")

    module_id = f"{category}/{platform}"
    versions = _version_manager.list_versions(module_id)

    return {
        "module_id": module_id,
        "versions": [v.to_dict() for v in versions],
        "total": len(versions),
        "active": next((v.to_dict() for v in versions if v.status == "ACTIVE"), None)
    }


# =============================================================================
# CAPABILITY CONTRACT ENDPOINTS (Phase 6)
# =============================================================================

import hashlib
from shared.contracts.ui_capability_schema import (
    CapabilityEnvelope,
    ToolCapability,
    ModuleCapability,
    ProviderCapability,
    AdapterCapability,
    FeatureHealth,
    FeatureStatus,
)


def _compute_etag(data: Any) -> str:
    """Compute ETag from JSON-serialized data."""
    if isinstance(data, str):
        content = data
    else:
        import json
        content = json.dumps(data, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _get_config_version() -> str:
    """Compute config version hash from routing config."""
    mgr = _get_mgr()
    config = mgr.get_config()
    return _compute_etag(config.model_dump())


def _gather_tool_capabilities() -> list[ToolCapability]:
    """Query tool registry for available tools."""
    # TODO: Wire to orchestrator tool registry when available
    # For now, return empty list - will be populated when tool registry is exposed
    return []


def _gather_module_capabilities() -> list[ModuleCapability]:
    """Query module registry for installed and draft modules."""
    if not _module_registry:
        return []

    modules = []
    # Query all modules from registry (installed + draft)
    # Using raw SQL since registry doesn't expose list_all method yet
    try:
        with _module_registry._connect() as conn:
            rows = conn.execute("""
                SELECT module_id, name, category, platform, status,
                       failure_count, success_count
                FROM modules
            """).fetchall()

            for row in rows:
                module_id, name, category, platform, status, failure_count, success_count = row
                # Determine version from active_versions if available
                version = None
                # Check if module has test suite by looking for test files
                has_tests = False  # TODO: Check artifacts for test presence

                modules.append(ModuleCapability(
                    id=module_id,
                    name=name,
                    category=category,
                    platform=platform,
                    status=status,
                    version=version,
                    has_tests=has_tests,
                ))
    except Exception as e:
        logger.warning(f"Failed to gather module capabilities: {e}")

    return modules


def _gather_provider_capabilities() -> list[ProviderCapability]:
    """Query provider config for LLM providers with lock status."""
    providers = []

    try:
        mgr = _get_mgr()
        config = mgr.get_config()

        # Read raw JSON for provider metadata
        import json
        raw_data = json.loads(mgr._config_path.read_text())
        providers_config = raw_data.get("providers", {})

        for tier_name, tier_config in config.tiers.items():
            # Determine if locked based on missing endpoint or disabled
            locked = not tier_config.enabled or not tier_config.endpoint

            providers.append(ProviderCapability(
                id=tier_name,
                name=tier_name.replace("_", " ").title(),
                tier=tier_name,
                locked=locked,
                connection_tested=False,
                last_test_ok=None,
            ))
    except Exception as e:
        logger.warning(f"Failed to gather provider capabilities: {e}")

    return providers


def _gather_adapter_capabilities() -> list[AdapterCapability]:
    """Query adapter registry for installed adapters with lock status."""
    adapters = []

    try:
        from shared.adapters.registry import adapter_registry

        all_adapters = adapter_registry.list_all_flat()

        for adapter_info in all_adapters:
            # Check if adapter has credentials via module credential store
            module_id = f"{adapter_info.category}/{adapter_info.platform}"
            has_credentials = _check_module_credentials(module_id)

            # Adapter is locked if it requires auth and has no credentials
            locked = adapter_info.requires_auth and not has_credentials

            # Determine missing fields (simplified - assumes API key for now)
            missing_fields = []
            if locked:
                if adapter_info.auth_type == "api_key":
                    missing_fields = ["api_key"]
                elif adapter_info.auth_type == "oauth2":
                    missing_fields = ["oauth_token"]

            adapters.append(AdapterCapability(
                id=module_id,
                name=adapter_info.display_name,
                category=adapter_info.category,
                locked=locked,
                missing_fields=missing_fields,
                last_data_timestamp=None,
                connection_tested=False,
                last_test_ok=None,
            ))
    except Exception as e:
        logger.warning(f"Failed to gather adapter capabilities: {e}")

    return adapters


def _derive_feature_health(
    modules: list[ModuleCapability],
    providers: list[ProviderCapability],
    adapters: list[AdapterCapability],
) -> list[FeatureHealth]:
    """Derive per-feature health status from capability data."""
    features = []

    # Feature: modules
    module_status = FeatureStatus.HEALTHY
    module_reasons = []
    disabled_count = sum(1 for m in modules if m.status == "disabled")
    draft_count = sum(1 for m in modules if m.status == "draft")
    failed_count = sum(1 for m in modules if m.status == "failed")
    if disabled_count > 0:
        module_status = FeatureStatus.DEGRADED
        module_reasons.append(f"{disabled_count} module(s) disabled")
    if draft_count > 0 and module_status == FeatureStatus.HEALTHY:
        module_status = FeatureStatus.DEGRADED
        module_reasons.append(f"{draft_count} module(s) in draft state")
    if failed_count > 0:
        module_status = FeatureStatus.DEGRADED
        module_reasons.append(f"{failed_count} module(s) failed to load")

    features.append(FeatureHealth(
        feature="modules",
        status=module_status,
        degraded_reasons=module_reasons,
        dependencies=["module_registry", "module_loader"],
    ))

    # Feature: providers
    unlocked_providers = [p for p in providers if not p.locked]
    if len(unlocked_providers) == 0:
        provider_status = FeatureStatus.DEGRADED
        provider_reasons = ["All LLM providers locked"]
    else:
        provider_status = FeatureStatus.HEALTHY
        provider_reasons = []

    features.append(FeatureHealth(
        feature="providers",
        status=provider_status,
        degraded_reasons=provider_reasons,
        dependencies=["routing_config"],
    ))

    # Feature: adapters
    locked_adapters = [a for a in adapters if a.locked]
    if len(locked_adapters) > 0:
        adapter_status = FeatureStatus.DEGRADED
        adapter_reasons = [f"{a.name} locked (missing: {', '.join(a.missing_fields)})" for a in locked_adapters]
    else:
        adapter_status = FeatureStatus.HEALTHY
        adapter_reasons = []

    features.append(FeatureHealth(
        feature="adapters",
        status=adapter_status,
        degraded_reasons=adapter_reasons,
        dependencies=["credential_store"],
    ))

    # Feature: billing (check quota usage)
    billing_status = FeatureStatus.UNKNOWN
    billing_reasons = []
    if _quota_manager:
        try:
            # Check default org for now (TODO: per-user org)
            result = _quota_manager.check_quota("default")
            usage_pct = (result.current_usage / result.quota_limit) * 100 if result.quota_limit > 0 else 0
            if usage_pct >= 80:
                billing_status = FeatureStatus.DEGRADED
                billing_reasons.append(f"Quota usage at {usage_pct:.1f}%")
            else:
                billing_status = FeatureStatus.HEALTHY
        except Exception:
            billing_status = FeatureStatus.UNKNOWN

    features.append(FeatureHealth(
        feature="billing",
        status=billing_status,
        degraded_reasons=billing_reasons,
        dependencies=["quota_manager", "usage_store"],
    ))

    return features


@_app.get("/admin/capabilities")
def get_capabilities(
    request: Request,
    user: User = Depends(get_current_user),
):
    """
    Get full capability envelope (tools, modules, providers, adapters, features).

    Supports ETag-based conditional requests via If-None-Match header.
    Returns 304 Not Modified if ETag matches current state.

    RBAC: viewer+ role required.
    """
    from datetime import datetime

    # Gather data from all registries
    tools = _gather_tool_capabilities()
    modules = _gather_module_capabilities()
    providers = _gather_provider_capabilities()
    adapters = _gather_adapter_capabilities()
    features = _derive_feature_health(modules, providers, adapters)

    # Build envelope
    envelope = CapabilityEnvelope(
        tools=tools,
        modules=modules,
        providers=providers,
        adapters=adapters,
        features=features,
        config_version=_get_config_version(),
        timestamp=datetime.utcnow().isoformat() + "Z",
    )

    # Compute ETag
    envelope_json = envelope.model_dump_json(exclude_none=True)
    etag = _compute_etag(envelope_json)

    # Check If-None-Match header
    if_none_match = request.headers.get("If-None-Match", "").strip('"')
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": f'"{etag}"'})

    # Return full envelope with ETag
    return Response(
        content=envelope_json,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@_app.get("/admin/feature-health")
def get_feature_health(user: User = Depends(get_current_user)):
    """
    Get per-feature health status.

    Returns health status for modules, providers, adapters, billing, sandbox, pipeline.

    RBAC: viewer+ role required.
    """
    import json

    # Gather minimal data needed for health derivation
    modules = _gather_module_capabilities()
    providers = _gather_provider_capabilities()
    adapters = _gather_adapter_capabilities()
    features = _derive_feature_health(modules, providers, adapters)

    # Add sandbox feature (check if reachable)
    sandbox_status = FeatureStatus.UNKNOWN
    sandbox_reasons = []
    try:
        import requests
        sandbox_url = os.getenv("SANDBOX_URL", "http://sandbox:50052")
        # Quick health check (HTTP if available, otherwise assume gRPC)
        # For now, mark as unknown since sandbox is gRPC-only
        sandbox_status = FeatureStatus.UNKNOWN
        sandbox_reasons = ["Health check not implemented"]
    except Exception as e:
        sandbox_status = FeatureStatus.UNAVAILABLE
        sandbox_reasons = [str(e)]

    features.append(FeatureHealth(
        feature="sandbox",
        status=sandbox_status,
        degraded_reasons=sandbox_reasons,
        dependencies=["sandbox_service"],
    ))

    # Add pipeline feature (check last build status)
    # TODO: Wire to actual pipeline status when available
    features.append(FeatureHealth(
        feature="pipeline",
        status=FeatureStatus.UNKNOWN,
        degraded_reasons=["Pipeline status tracking not yet implemented"],
        dependencies=["builder", "validator"],
    ))

    return JSONResponse(content=[f.model_dump() for f in features])


@_app.get("/admin/config/version")
def get_config_version(request: Request, user: User = Depends(get_current_user)):
    """
    Get config version hash (lightweight polling endpoint).

    Supports ETag-based conditional requests.
    Clients poll this endpoint cheaply to detect changes, then fetch full /capabilities.

    RBAC: viewer+ role required.
    """
    config_version = _get_config_version()
    etag = _compute_etag({"config_version": config_version})

    # Check If-None-Match header
    if_none_match = request.headers.get("If-None-Match", "").strip('"')
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": f'"{etag}"'})

    return JSONResponse(
        content={"config_version": config_version, "etag": etag},
        headers={"ETag": f'"{etag}"'},
    )


# ── Server launcher ──────────────────────────────────────────────────────────


# =============================================================================
# USER PREFERENCES ENDPOINTS (Phase 6)
# =============================================================================


_user_prefs_store = None


class UserPrefsUpdateRequest(BaseModel):
    """Request body for updating user preferences."""
    prefs: Dict[str, Any]
    version: int


@_app.get("/admin/user/prefs")
def get_user_prefs(user: User = Depends(get_current_user)):
    """
    Get user preferences + version.

    Returns defaults if no preferences stored yet.
    RBAC: viewer+ role required.
    """
    if _user_prefs_store is None:
        # Lazy-init user prefs store
        _init_user_prefs_store()

    if _user_prefs_store is None:
        raise HTTPException(503, "User preferences store not initialized")

    prefs, version = _user_prefs_store.get_prefs(user.org_id)
    return {
        "prefs": prefs.model_dump(),
        "version": version,
    }


@_app.put("/admin/user/prefs")
def update_user_prefs(
    request: UserPrefsUpdateRequest,
    user: User = Depends(get_current_user),
):
    """
    Update user preferences with optimistic concurrency.

    Returns 409 on version conflict.
    RBAC: viewer+ role required (users can only update their own prefs).
    """
    if _user_prefs_store is None:
        _init_user_prefs_store()

    if _user_prefs_store is None:
        raise HTTPException(503, "User preferences store not initialized")

    from shared.auth.user_prefs import UserPreferences, ConflictError

    try:
        prefs = UserPreferences(**request.prefs)
    except Exception as e:
        raise HTTPException(400, f"Invalid preferences: {e}")

    try:
        new_version = _user_prefs_store.set_prefs(
            user_id=user.org_id,
            prefs=prefs,
            expected_version=request.version,
        )
    except ConflictError as e:
        raise HTTPException(
            409,
            {
                "error": "Version conflict",
                "current_version": e.current_version,
                "expected_version": e.expected_version,
            },
        )

    return {
        "prefs": prefs.model_dump(),
        "version": new_version,
    }


def _init_user_prefs_store():
    """Lazy-initialize the user preferences store."""
    global _user_prefs_store
    try:
        from shared.auth.user_prefs import UserPrefsStore
        _user_prefs_store = UserPrefsStore(
            db_path=os.getenv("USER_PREFS_DB_PATH", "data/user_prefs.db")
        )
    except Exception as e:
        logger.warning(f"Failed to initialize user prefs store: {e}")


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


# =============================================================================
# BILLING & USAGE ENDPOINTS
# =============================================================================


@_app.get("/admin/billing/usage")
def get_billing_usage(
    period: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Get usage summary for the authenticated user's organization."""
    if _usage_store is None:
        raise HTTPException(503, "Billing not initialized")
    return _usage_store.get_usage_summary(user.org_id, period)


@_app.get("/admin/billing/usage/history")
def get_billing_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
):
    """Get usage history for the authenticated user's organization."""
    if _usage_store is None:
        raise HTTPException(503, "Billing not initialized")
    records = _usage_store.get_usage_history(
        user.org_id,
        start_date=start_date,
        end_date=end_date,
        limit=min(limit, 1000),
    )
    return {"records": records, "count": len(records)}


@_app.get("/admin/billing/quota")
def get_billing_quota(user: User = Depends(get_current_user)):
    """Get quota status for the authenticated user's organization."""
    if _quota_manager is None:
        raise HTTPException(503, "Billing not initialized")
    result = _quota_manager.check_quota(user.org_id)
    return result.model_dump()


# =============================================================================
# DEV-MODE ENDPOINTS (Draft lifecycle + version management)
# =============================================================================


class DraftCreateRequest(BaseModel):
    """Request to create a draft from an installed module."""
    from_version: str = "active"


class DraftEditRequest(BaseModel):
    """Request to edit a file in a draft."""
    file_path: str
    content: str


class RollbackRequest(BaseModel):
    """Request to rollback to a prior version."""
    target_version_id: str
    reason: str = ""


@_app.post("/admin/modules/{module_id}/draft")
def create_draft(
    module_id: str,
    request: DraftCreateRequest,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """
    Create a draft from an installed module.

    RBAC: operator+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.create_draft(
        module_id=module_id,
        from_version=request.from_version,
        actor=user.org_id
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.patch("/admin/modules/drafts/{draft_id}")
def edit_draft(
    draft_id: str,
    request: DraftEditRequest,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """
    Edit a file in a draft.

    RBAC: operator+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.edit_file(
        draft_id=draft_id,
        file_path=request.file_path,
        content=request.content,
        actor=user.org_id
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.get("/admin/modules/drafts/{draft_id}/diff")
def get_draft_diff(
    draft_id: str,
    user: User = Depends(get_current_user),
):
    """
    View diff between draft and source version.

    RBAC: viewer+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.get_diff(draft_id=draft_id, actor=user.org_id)

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.post("/admin/modules/drafts/{draft_id}/validate")
def validate_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),
):
    """
    Trigger sandbox validation for a draft.

    RBAC: admin+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.validate_draft(
        draft_id=draft_id,
        actor=user.org_id
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.post("/admin/modules/drafts/{draft_id}/promote")
def promote_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),
):
    """
    Promote a validated draft to a new version.

    RBAC: admin+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.promote_draft(
        draft_id=draft_id,
        actor=user.org_id
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.delete("/admin/modules/drafts/{draft_id}")
def discard_draft(
    draft_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """
    Discard a draft.

    RBAC: operator+ role required.
    """
    if _draft_manager is None:
        raise HTTPException(503, "Draft manager not initialized")

    result = _draft_manager.discard_draft(
        draft_id=draft_id,
        actor=user.org_id
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.post("/admin/modules/{module_id}/rollback")
def rollback_module(
    module_id: str,
    request: RollbackRequest,
    user: User = Depends(require_permission(Permission.ADMIN_ALL)),
):
    """
    Rollback to a prior validated version.

    RBAC: admin+ role required.
    """
    if _version_manager is None:
        raise HTTPException(503, "Version manager not initialized")

    result = _version_manager.rollback_to_version(
        module_id=module_id,
        target_version_id=request.target_version_id,
        actor=user.org_id,
        reason=request.reason
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Unknown error"))

    return result


@_app.get("/admin/modules/{module_id}/versions")
def list_module_versions(
    module_id: str,
    user: User = Depends(get_current_user),
):
    """
    List all validated versions for a module.

    RBAC: viewer+ role required.
    """
    if _version_manager is None:
        raise HTTPException(503, "Version manager not initialized")

    versions = _version_manager.list_versions(module_id=module_id)
    active = _version_manager.get_active_version(module_id=module_id)

    return {
        "module_id": module_id,
        "active_version": active.to_dict() if active else None,
        "versions": [v.to_dict() for v in versions],
        "total": len(versions)
    }


# =============================================================================
# CHART ARTIFACT ENDPOINTS
# =============================================================================

@_app.get("/admin/modules/{category}/{platform}/charts")
def list_chart_artifacts(
    category: str,
    platform: str,
    user: User = Depends(get_current_user),
):
    """
    List available chart artifacts for a module.

    RBAC: viewer+ role required.
    """
    from pathlib import Path
    import mimetypes

    if _artifacts_dir is None:
        raise HTTPException(503, "Artifacts directory not configured")

    artifacts_path = Path(_artifacts_dir) / category / platform
    if not artifacts_path.exists():
        return {"module_id": f"{category}/{platform}", "charts": [], "total": 0}

    charts = []
    for f in sorted(artifacts_path.iterdir()):
        if f.is_file() and f.suffix in (".json", ".png", ".svg", ".jpg", ".jpeg"):
            mime_type, _ = mimetypes.guess_type(str(f))
            charts.append({
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "mime_type": mime_type or "application/octet-stream",
                "modified_at": f.stat().st_mtime,
            })

    return {
        "module_id": f"{category}/{platform}",
        "charts": charts,
        "total": len(charts),
    }


@_app.get("/admin/modules/{category}/{platform}/charts/{chart_name}")
def get_chart_artifact(
    category: str,
    platform: str,
    chart_name: str,
    user: User = Depends(get_current_user),
):
    """
    Serve a specific chart artifact with proper Content-Type.

    RBAC: viewer+ role required.
    """
    from pathlib import Path
    import mimetypes

    if _artifacts_dir is None:
        raise HTTPException(503, "Artifacts directory not configured")

    chart_path = Path(_artifacts_dir) / category / platform / chart_name
    if not chart_path.exists() or not chart_path.is_file():
        raise HTTPException(404, f"Chart artifact not found: {chart_name}")

    mime_type, _ = mimetypes.guess_type(str(chart_path))
    mime_type = mime_type or "application/octet-stream"

    content = chart_path.read_bytes()

    # JSON charts: return as JSON response
    if mime_type == "application/json":
        import json
        try:
            data = json.loads(content)
            return JSONResponse(content=data)
        except json.JSONDecodeError:
            pass

    return Response(content=content, media_type=mime_type)


class ChartValidateRequest(BaseModel):
    """Request body for chart validation."""
    chart_data_base64: str
    expected_series: Optional[List[str]] = None
    expected_title: Optional[str] = None
    check_rendering_hash: bool = False
    expected_hash: Optional[str] = None


@_app.post("/admin/modules/{category}/{platform}/charts/validate")
def validate_chart_artifact(
    category: str,
    platform: str,
    body: ChartValidateRequest,
    user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
):
    """
    Validate an uploaded chart artifact.

    RBAC: operator+ role required (MANAGE_MODULES permission).
    """
    import base64

    try:
        artifact_bytes = base64.b64decode(body.chart_data_base64)
    except Exception:
        raise HTTPException(400, "Invalid base64 chart data")

    result = validate_chart(
        artifact_bytes=artifact_bytes,
        expected_series=body.expected_series,
        expected_title=body.expected_title,
        check_rendering_hash=body.check_rendering_hash,
        expected_hash=body.expected_hash,
    )

    return {
        "module_id": f"{category}/{platform}",
        "validation": result.to_dict(),
    }


def start_admin_server(
    config_manager: ConfigManager,
    port: int = 8003,
    module_loader=None,
    module_registry=None,
    credential_store=None,
    api_key_store: Optional[APIKeyStore] = None,
    usage_store: Optional[UsageStore] = None,
    quota_manager: Optional[QuotaManager] = None,
    draft_manager=None,
    version_manager=None,
    artifacts_dir=None,
) -> None:
    """Start admin API in a daemon thread. Safe to call from gRPC serve()."""
    global _config_manager, _module_loader, _module_registry, _credential_store, _api_key_store
    global _usage_store, _quota_manager, _draft_manager, _version_manager, _artifacts_dir
    _config_manager = config_manager
    _module_loader = module_loader
    _module_registry = module_registry
    _credential_store = credential_store
    _draft_manager = draft_manager
    _version_manager = version_manager
    _artifacts_dir = artifacts_dir

    # Initialize auth
    _api_key_store = api_key_store or APIKeyStore(
        db_path=os.getenv("AUTH_DB_PATH", "data/api_keys.db")
    )

    # Initialize billing
    _usage_store = usage_store or UsageStore(
        db_path=os.getenv("BILLING_DB_PATH", "data/billing.db")
    )
    _quota_manager = quota_manager or QuotaManager(
        usage_store=_usage_store,
        api_key_store=_api_key_store,
    )

    _app.add_middleware(
        APIKeyAuthMiddleware,
        api_key_store=_api_key_store,
        public_paths=[
            "/admin/health",
            "/admin/bootstrap",
            "/admin/providers",
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
