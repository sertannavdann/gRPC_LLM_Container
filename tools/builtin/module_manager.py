"""
Module Manager Tool — list, enable, disable, and manage credentials.

Provides the LLM with tools to manage the module lifecycle after
installation. These tools are the interface between the conversational
agent and the module infrastructure.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# References set by orchestrator at startup
_module_loader = None
_module_registry = None
_credential_store = None


def set_module_loader(loader) -> None:
    global _module_loader
    _module_loader = loader


def set_module_registry(registry) -> None:
    global _module_registry
    _module_registry = registry


def set_credential_store(store) -> None:
    global _credential_store
    _credential_store = store


def list_modules() -> Dict[str, Any]:
    """
    List all installed and available modules.

    Use this tool when the user asks about their integrations,
    modules, or available data sources. Shows module name, status,
    health, and whether credentials are configured.

    Returns:
        Dict with list of modules and their status.
    """
    modules = []

    # Get from loader (in-memory state)
    if _module_loader:
        for m in _module_loader.list_modules():
            entry = {
                "module_id": f"{m.get('category', '')}/{m.get('platform', '')}",
                "name": m.get("display_name", m.get("name", "")),
                "category": m.get("category", ""),
                "platform": m.get("platform", ""),
                "status": m.get("status", "unknown"),
                "health": m.get("health_status", "unknown"),
                "is_loaded": m.get("is_loaded", False),
                "requires_api_key": m.get("requires_api_key", False),
                "has_credentials": False,
            }
            # Check credentials
            if _credential_store and entry["requires_api_key"]:
                entry["has_credentials"] = _credential_store.has_credentials(
                    entry["module_id"]
                )
            modules.append(entry)

    return {
        "status": "success",
        "modules": modules,
        "total": len(modules),
        "loaded": sum(1 for m in modules if m.get("is_loaded")),
    }


def enable_module(module_id: str) -> Dict[str, Any]:
    """
    Enable a disabled module and load it.

    Use this when the user asks to turn on or enable a module
    that was previously disabled.

    Args:
        module_id (str): Module identifier in "category/platform" format.

    Returns:
        Dict with status and whether the module was loaded.
    """
    if not _module_loader:
        return {"status": "error", "error": "Module loader not available"}

    try:
        handle = _module_loader.enable_module(module_id)
        if _module_registry:
            _module_registry.enable(module_id)

        return {
            "status": "success",
            "module_id": module_id,
            "is_loaded": handle.is_loaded,
            "message": f"Module {module_id} enabled and loaded.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def disable_module(module_id: str) -> Dict[str, Any]:
    """
    Disable a module without uninstalling it.

    The module remains on disk but is unloaded from the adapter
    registry. It won't load on next restart until re-enabled.

    Args:
        module_id (str): Module identifier in "category/platform" format.

    Returns:
        Dict with status confirmation.
    """
    if not _module_loader:
        return {"status": "error", "error": "Module loader not available"}

    success = _module_loader.disable_module(module_id)
    if _module_registry:
        _module_registry.disable(module_id)

    if success:
        return {
            "status": "success",
            "module_id": module_id,
            "message": f"Module {module_id} disabled.",
        }
    return {"status": "error", "error": f"Module {module_id} not found"}


def store_module_credentials(
    module_id: str,
    api_key: str = "",
    credentials_json: str = "",
) -> Dict[str, Any]:
    """
    Store API credentials for a module.

    Use this when the user provides their API key or credentials
    for a module. Credentials are encrypted at rest and never
    exposed in conversation context.

    Args:
        module_id (str): Module identifier in "category/platform" format.
        api_key (str): API key string. Use this for simple API key auth.
        credentials_json (str): JSON string with multiple credential fields.
            Use this for OAuth2 or complex auth (e.g. '{"client_id": "...",
            "client_secret": "..."}').

    Returns:
        Dict with status confirmation.
    """
    if not _credential_store:
        return {"status": "error", "error": "Credential store not available"}

    if credentials_json:
        import json
        try:
            creds = json.loads(credentials_json)
        except json.JSONDecodeError:
            return {"status": "error", "error": "Invalid JSON in credentials_json"}
    elif api_key:
        creds = {"api_key": api_key}
    else:
        return {"status": "error", "error": "Provide either api_key or credentials_json"}

    _credential_store.store(module_id, creds)

    # Reload the module so credentials are picked up
    if _module_loader:
        handle = _module_loader.get_module(module_id)
        if handle and handle.is_loaded:
            _module_loader.reload_module(module_id)

    return {
        "status": "success",
        "module_id": module_id,
        "message": f"Credentials stored for {module_id}. Module reloaded with new credentials.",
    }
