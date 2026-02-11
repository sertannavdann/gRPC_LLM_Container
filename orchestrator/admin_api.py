"""
Admin HTTP API for dynamic routing configuration.

Runs as a FastAPI server in a daemon thread on port 8003.
Provides CRUD endpoints for hot-reloading routing config
without container restarts.
"""

import logging
import threading

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from typing import Optional

from .config_manager import ConfigManager
from .routing_config import CategoryRouting, RoutingConfig

logger = logging.getLogger(__name__)

_app = FastAPI(title="Orchestrator Admin API", version="1.0")
_config_manager: Optional[ConfigManager] = None


def _get_mgr() -> ConfigManager:
    if _config_manager is None:
        raise HTTPException(status_code=503, detail="ConfigManager not initialized")
    return _config_manager


# ── Endpoints ────────────────────────────────────────────────────────────────


@_app.get("/admin/health")
def health():
    return {"status": "ok"}


@_app.get("/admin/routing-config")
def get_routing_config():
    mgr = _get_mgr()
    return mgr.get_config().model_dump()


@_app.put("/admin/routing-config")
def put_routing_config(payload: RoutingConfig):
    mgr = _get_mgr()
    mgr.update_config(payload)
    return {"status": "updated", "version": payload.version}


@_app.patch("/admin/routing-config/category/{name}")
def patch_category(name: str, payload: CategoryRouting):
    mgr = _get_mgr()
    config = mgr.get_config().model_copy(deep=True)
    config.categories[name] = payload
    mgr.update_config(config)
    return {"status": "updated", "category": name, "tier": payload.tier}


@_app.delete("/admin/routing-config/category/{name}")
def delete_category(name: str):
    mgr = _get_mgr()
    config = mgr.get_config().model_copy(deep=True)
    if name not in config.categories:
        raise HTTPException(status_code=404, detail=f"Category '{name}' not found")
    del config.categories[name]
    mgr.update_config(config)
    return {"status": "deleted", "category": name}


@_app.post("/admin/routing-config/reload")
def reload_config():
    mgr = _get_mgr()
    config = mgr.reload()
    return {"status": "reloaded", "categories": len(config.categories)}


# ── Server launcher ──────────────────────────────────────────────────────────


def start_admin_server(config_manager: ConfigManager, port: int = 8003) -> None:
    """Start admin API in a daemon thread. Safe to call from gRPC serve()."""
    global _config_manager
    _config_manager = config_manager

    def _run():
        uvicorn.run(
            _app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            access_log=False,
            # Critical: don't install signal handlers — gRPC owns signals
            install_signal_handlers=False,
        )

    thread = threading.Thread(target=_run, name="admin-api", daemon=True)
    thread.start()
    logger.info(f"Admin API started on port {port} (daemon thread)")
