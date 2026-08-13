"""
Shared fixtures for Admin API integration tests.

Provides TestClient wired with auth middleware, isolated databases,
and API keys for all roles (viewer, operator, admin, owner).
"""
import csv
import dataclasses
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import pytest
from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.testclient import TestClient

# Import the components we need directly (avoiding orchestrator/__init__.py)
from orchestrator.config_manager import ConfigManager
from orchestrator.routing_config import RoutingConfig, CategoryRouting, TierConfig, PerformanceConstraints
from shared.audit import AuditContextMiddleware, AuditStore, audit_action, set_audit_store
from shared.auth.api_keys import APIKeyStore
from shared.auth.middleware import APIKeyAuthMiddleware
from shared.auth.models import Role, User
from shared.auth.rbac import Permission, get_current_user, require_permission
from shared.billing import QuotaManager, UsageStore
from shared.modules.approval import approve_module, reject_module
from shared.modules.audit import DevModeAuditLog
from shared.modules.credentials import CredentialStore
from shared.modules.loader import ModuleLoader
from shared.modules.manifest import ModuleManifest
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
    app.state.modules_dir = None
    app.state.audit_log = None
    app.state.audit_store = None

    def _module_credential_keys_snapshot(**kwargs):
        """NEVER return credential values — key names only (D-04).

        Field name deliberately avoids the literal substring "credential" —
        shared.audit.redaction.SECRET_KEY_PATTERN matches any dict KEY
        containing that substring and would redact this whole safe metadata
        field (a list of field NAMES, not values) down to "[REDACTED]".
        """
        request = kwargs.get("request")
        creds = getattr(request, "credentials", None) if request is not None else None
        if not creds:
            return None
        return {"field_names": sorted(creds.keys())}

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

    # Enable module — representative decorated "module" mutation (REQ-011 Task 3)
    @app.post("/admin/modules/{category}/{platform}/enable")
    @audit_action("module_enabled", "module", resource_id="{category}/{platform}")
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

    # Store module credentials — representative decorated "credential" mutation
    # (REQ-011 Task 3). Mirrors orchestrator/admin_api.py's store_credentials:
    # NEVER puts credential values in the audit event, key names only (D-04).
    class TestModuleCredentialRequest(BaseModel):
        credentials: Dict[str, str]

    @app.post("/admin/modules/{category}/{platform}/credentials")
    @audit_action(
        "module_credentials_stored",
        "module_credentials",
        resource_id="{category}/{platform}",
        snapshot=_module_credential_keys_snapshot,
    )
    def store_credentials(
        category: str,
        platform: str,
        request: TestModuleCredentialRequest,
        user: User = Depends(require_permission(Permission.MANAGE_CREDENTIALS)),
    ):
        from fastapi import HTTPException

        module_id = f"{category}/{platform}"
        if app.state.credential_store is None:
            raise HTTPException(status_code=503, detail="Credential store not initialized")
        app.state.credential_store.store(module_id, request.credentials)
        return {
            "success": True,
            "module_id": module_id,
            "message": f"Credentials stored for {module_id}",
        }

    # Routing config endpoints
    @app.get("/admin/routing-config")
    def get_routing_config(user: User = Depends(get_current_user)):
        from fastapi import HTTPException
        if app.state.config_manager is None:
            raise HTTPException(status_code=503, detail="ConfigManager not initialized")
        return app.state.config_manager.get_config().model_dump()

    # Representative decorated "config" mutation (REQ-011 Task 3)
    @app.put("/admin/routing-config")
    @audit_action("routing_config_updated", "routing_config")
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

    # ------------------------------------------------------------------
    # Approval gate endpoints (Phase 8 plan 08-01 — D-16/D-17/D-09/D-10/D-19)
    # Mirrors orchestrator/admin_api.py's approve/reject/review/audit
    # endpoints, reading dependencies from app.state instead of module
    # globals (this factory deliberately avoids importing orchestrator/).
    # ------------------------------------------------------------------

    class RejectModuleRequest(BaseModel):
        feedback: Optional[str] = None

    @app.post("/admin/modules/{category}/{platform}/approve")
    def approve_module_endpoint(
        category: str,
        platform: str,
        user: User = Depends(require_permission(Permission.WRITE_CONFIG)),
    ):
        from fastapi import HTTPException
        if app.state.audit_log is None or app.state.modules_dir is None:
            raise HTTPException(status_code=503, detail="Approval gate not initialized")

        module_id = f"{category}/{platform}"
        result = approve_module(
            module_id=module_id,
            actor=user.org_id,
            audit_log=app.state.audit_log,
            modules_dir=app.state.modules_dir,
        )
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result.get("error", "Approval failed"))
        return result

    @app.post("/admin/modules/{category}/{platform}/reject")
    def reject_module_endpoint(
        category: str,
        platform: str,
        request: RejectModuleRequest,
        user: User = Depends(require_permission(Permission.WRITE_CONFIG)),
    ):
        from fastapi import HTTPException
        if app.state.audit_log is None or app.state.modules_dir is None:
            raise HTTPException(status_code=503, detail="Approval gate not initialized")

        module_id = f"{category}/{platform}"
        result = reject_module(
            module_id=module_id,
            feedback=request.feedback,
            actor=user.org_id,
            audit_log=app.state.audit_log,
            modules_dir=app.state.modules_dir,
        )
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result.get("error", "Rejection failed"))
        return result

    def _test_blueprint_summary(module_dir: Path, manifest) -> Dict[str, Any]:
        """Minimal mirror of admin_api.py's _build_blueprint_summary for tests
        (kept local to avoid importing the orchestrator package)."""
        import ast

        summary: Dict[str, Any] = {
            "adapter_name": manifest.class_name,
            "schema_field_count": 0,
            "output_types": [],
            "credential_names": [manifest.name] if manifest.requires_api_key else [],
        }
        adapter_file = module_dir / "adapter.py"
        if not adapter_file.exists():
            return summary
        try:
            tree = ast.parse(adapter_file.read_text())
            for node in ast.walk(tree):
                if not (isinstance(node, ast.FunctionDef) and node.name == "get_schema"):
                    continue
                for stmt in ast.walk(node):
                    if not (isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict)):
                        continue
                    for key, value in zip(stmt.value.keys, stmt.value.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "properties"
                            and isinstance(value, ast.Dict)
                        ):
                            summary["schema_field_count"] = len(value.keys)
        except Exception:
            pass
        return summary

    @app.get("/admin/modules/{category}/{platform}/review")
    def review_module_endpoint(
        category: str,
        platform: str,
        user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
    ):
        from fastapi import HTTPException
        if app.state.modules_dir is None:
            raise HTTPException(status_code=503, detail="Approval gate not initialized")

        module_id = f"{category}/{platform}"
        module_dir = Path(app.state.modules_dir) / category / platform
        manifest_path = module_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail=f"Module not found: {module_id}")

        manifest = ModuleManifest.load(manifest_path)
        return {
            "module_id": module_id,
            "status": manifest.status,
            "validation_results": manifest.validation_results.to_dict(),
            "walkthrough": getattr(manifest, "walkthrough", ""),
            "credentials": {
                "requires_api_key": manifest.requires_api_key,
                "auth_type": manifest.auth_type,
                "api_key_instructions": manifest.api_key_instructions,
            },
            "blueprint": _test_blueprint_summary(module_dir, manifest),
        }

    @app.get("/admin/modules/{category}/{platform}/audit")
    def audit_module_endpoint(
        category: str,
        platform: str,
        user: User = Depends(require_permission(Permission.MANAGE_MODULES)),
    ):
        from fastapi import HTTPException
        if app.state.modules_dir is None:
            raise HTTPException(status_code=503, detail="Approval gate not initialized")

        module_id = f"{category}/{platform}"
        module_dir = Path(app.state.modules_dir) / category / platform
        if not module_dir.exists():
            raise HTTPException(status_code=404, detail=f"Module not found: {module_id}")

        events = []
        if app.state.audit_log is not None:
            events = [
                e.to_dict() for e in app.state.audit_log.get_events(module_id=module_id)
            ]
        return {"module_id": module_id, "attempts": events}

    # ------------------------------------------------------------------
    # Audit query API (REQ-012, Phase 07-03) — mirrors orchestrator/
    # admin_api.py's three read-only audit endpoints, wired against
    # app.state.audit_store instead of the module-global _audit_store
    # (this factory deliberately avoids importing orchestrator/).
    # ------------------------------------------------------------------

    _AUDIT_CSV_COLUMNS = [
        "id", "timestamp", "org_id", "actor_id", "action", "resource_type",
        "resource_id", "ip_address", "before_state", "after_state",
        "details", "prev_hash", "row_hash",
    ]

    def _audit_query_filters(user, org_id, actor_id, action, resource_type, resource_id, start, end):
        filters: Dict[str, Any] = {}
        if user.role == Role.OWNER:
            if org_id is not None:
                filters["org_id"] = org_id
        else:
            filters["org_id"] = user.org_id
        if actor_id is not None:
            filters["actor_id"] = actor_id
        if action is not None:
            filters["action"] = action
        if resource_type is not None:
            filters["resource_type"] = resource_type
        if resource_id is not None:
            filters["resource_id"] = resource_id
        if start is not None:
            filters["start_time"] = start
        if end is not None:
            filters["end_time"] = end
        return filters

    def _audit_csv_cell(value: Any) -> str:
        if value is None:
            return ""
        text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if text[:1] in ("=", "+", "-", "@"):
            text = "'" + text
        return text

    @app.get("/admin/audit-logs")
    def query_audit_logs(
        start: Optional[str] = None,
        end: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        org_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        user: User = Depends(require_permission(Permission.READ_AUDIT)),
    ):
        from fastapi import HTTPException
        if app.state.audit_store is None:
            raise HTTPException(status_code=503, detail="AuditStore not initialized")

        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        filters = _audit_query_filters(
            user, org_id, actor_id, action, resource_type, resource_id, start, end
        )

        events = app.state.audit_store.query(limit=limit, offset=offset, **filters)
        total = app.state.audit_store.count(**filters)

        return {
            "events": events,
            "count": len(events),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/admin/audit-logs/export")
    def export_audit_logs(
        start: Optional[str] = None,
        end: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        org_id: Optional[str] = None,
        user: User = Depends(require_permission(Permission.READ_AUDIT)),
    ):
        from fastapi import HTTPException
        if app.state.audit_store is None:
            raise HTTPException(status_code=503, detail="AuditStore not initialized")

        filters = _audit_query_filters(
            user, org_id, actor_id, action, resource_type, resource_id, start, end
        )

        def _generate() -> Iterator[str]:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(_AUDIT_CSV_COLUMNS)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

            for event in app.state.audit_store.iter_events(batch_size=1000, **filters):
                writer.writerow([_audit_csv_cell(event.get(col)) for col in _AUDIT_CSV_COLUMNS])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

        filename = f"audit_events_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
        return StreamingResponse(
            _generate(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/admin/audit-logs/verify")
    def verify_audit_chain(
        start_id: Optional[int] = None,
        end_id: Optional[int] = None,
        user: User = Depends(require_permission(Permission.READ_AUDIT)),
    ):
        from fastapi import HTTPException
        if app.state.audit_store is None:
            raise HTTPException(status_code=503, detail="AuditStore not initialized")

        result = app.state.audit_store.verify_chain(start_id=start_id, end_id=end_id)
        return dataclasses.asdict(result)

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
        "audit": str(tmp_path / "audit_events.db"),
    }


@pytest.fixture
def audit_store(tmp_databases):
    """
    Create an isolated AuditStore for testing and register it as the
    module-level singleton (shared.audit.get_audit_store()) so
    @audit_action-decorated endpoints — which resolve their store lazily
    at call time — write into this test's isolated DB.
    """
    store = AuditStore(db_path=tmp_databases["audit"])
    set_audit_store(store)
    return store


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
def modules_dir(tmp_path):
    """Modules directory backing the approval-gate endpoints (shared with module_loader)."""
    d = tmp_path / "modules"
    d.mkdir(exist_ok=True)
    return d


@pytest.fixture
def audit_log(tmp_path):
    """DevModeAuditLog instance for approval-gate audit trail tests (D-19)."""
    return DevModeAuditLog(audit_dir=tmp_path / "audit")


@pytest.fixture
def admin_app(
    config_manager,
    module_loader,
    module_registry,
    credential_store,
    api_key_store,
    usage_store,
    quota_manager,
    modules_dir,
    audit_log,
    audit_store,
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
    app.state.modules_dir = modules_dir
    app.state.audit_log = audit_log
    app.state.audit_store = audit_store

    # AuditContextMiddleware must run INNER of the auth middleware (after
    # request.state.user is set) — Starlette's add_middleware() makes the
    # LAST-added middleware the OUTERMOST, so this call must come BEFORE
    # the APIKeyAuthMiddleware add_middleware() call below.
    app.add_middleware(AuditContextMiddleware)

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
