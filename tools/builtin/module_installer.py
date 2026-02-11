"""
Module Installer Tool — deploys validated modules into the live system.

This is the final step in the self-evolution pipeline:
    build_module() → write_module_code() → validate_module() → install_module()

The installer hot-loads the module into the AdapterRegistry via ModuleLoader,
records it in the persistent ModuleRegistry, and prompts for credentials
if needed.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any

from shared.modules.manifest import ModuleManifest, ModuleStatus

logger = logging.getLogger(__name__)

MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))

# References set by orchestrator at startup
_module_loader = None
_module_registry = None
_credential_store = None


def set_installer_deps(loader, registry, credential_store) -> None:
    """Wire dependencies from orchestrator."""
    global _module_loader, _module_registry, _credential_store
    _module_loader = loader
    _module_registry = registry
    _credential_store = credential_store


def install_module(module_id: str) -> Dict[str, Any]:
    """
    Install a validated module into the live system.

    Hot-loads the adapter into the registry so it's immediately
    available for queries. Records the installation in the
    persistent database for restart survival.

    Only call this after validate_module() returns success
    AND the user has explicitly approved the installation.

    Args:
        module_id (str): Module identifier in "category/platform" format,
            e.g. "gaming/clashroyale".

    Returns:
        Dict with installation status, whether credentials are needed,
        and instructions for the user.
    """
    parts = module_id.split("/")
    if len(parts) != 2:
        return {"status": "error", "error": f"Invalid module_id: {module_id}"}

    category, platform = parts
    module_dir = MODULES_DIR / category / platform
    manifest_path = module_dir / "manifest.json"

    if not manifest_path.exists():
        return {"status": "error", "error": f"Module not found: {module_id}. Run build_module() first."}

    manifest = ModuleManifest.load(manifest_path)

    # Check validation status
    if manifest.status == ModuleStatus.FAILED:
        return {
            "status": "error",
            "error": f"Module {module_id} failed validation. Fix errors and run validate_module() again.",
        }

    if not _module_loader:
        return {"status": "error", "error": "Module loader not available"}

    # Hot-load into AdapterRegistry
    handle = _module_loader.load_module(manifest)

    if not handle.is_loaded:
        return {
            "status": "error",
            "error": f"Failed to load module: {handle.error}",
        }

    # Record in persistent registry
    if _module_registry:
        _module_registry.install(manifest)

    # Update manifest on disk
    manifest.status = ModuleStatus.INSTALLED
    manifest.save(MODULES_DIR)

    logger.info(f"Module installed: {module_id}")

    # Check if credentials are needed
    needs_credentials = manifest.requires_api_key
    has_credentials = False
    if needs_credentials and _credential_store:
        has_credentials = _credential_store.has_credentials(module_id)

    result = {
        "status": "success",
        "module_id": module_id,
        "display_name": manifest.display_name,
        "is_loaded": True,
        "needs_credentials": needs_credentials and not has_credentials,
        "message": f"Module '{manifest.display_name}' installed and active.",
    }

    if needs_credentials and not has_credentials:
        instructions = manifest.api_key_instructions or (
            f"Please provide your {manifest.display_name} API key "
            f"so I can connect to the service."
        )
        result["credential_prompt"] = instructions
        result["message"] += f" However, it needs API credentials to function. {instructions}"

    return result


def uninstall_module(module_id: str) -> Dict[str, Any]:
    """
    Uninstall a module from the live system.

    Removes it from the adapter registry and persistent database.
    The module files remain on disk for potential reinstallation.

    Args:
        module_id (str): Module identifier in "category/platform" format.

    Returns:
        Dict with uninstallation status.
    """
    if not _module_loader:
        return {"status": "error", "error": "Module loader not available"}

    # Unload from runtime
    _module_loader.unload_module(module_id)

    # Remove from persistent registry
    if _module_registry:
        _module_registry.uninstall(module_id)

    # Update manifest on disk
    parts = module_id.split("/")
    if len(parts) == 2:
        manifest_path = MODULES_DIR / parts[0] / parts[1] / "manifest.json"
        if manifest_path.exists():
            manifest = ModuleManifest.load(manifest_path)
            manifest.status = ModuleStatus.UNINSTALLED
            manifest.save(MODULES_DIR)

    logger.info(f"Module uninstalled: {module_id}")

    return {
        "status": "success",
        "module_id": module_id,
        "message": f"Module {module_id} uninstalled. Files preserved on disk.",
    }
