"""
Module Installer Tool — deploys validated modules into the live system.

This is the final step in the self-evolution pipeline:
    build_module() → write_module_code() → validate_module() → install_module()

The installer hot-loads the module into the AdapterRegistry via ModuleLoader,
records it in the persistent ModuleRegistry, and prompts for credentials
if needed.

Security features:
- Attestation-based install guard: only VALIDATED bundles can be installed
- Hash verification: bundle_sha256 must match validation attestation
- Audit trail: all install attempts (success and rejection) are logged
"""
import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from shared.modules.manifest import ModuleManifest, ModuleStatus
from shared.modules.artifacts import verify_bundle_hash, ArtifactBundleBuilder

logger = logging.getLogger(__name__)

MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))
AUDIT_DIR = Path(os.getenv("AUDIT_DIR", "/app/data/audit"))

# References set by orchestrator at startup
_module_loader = None
_module_registry = None
_credential_store = None
_validation_store = None  # Stores validation attestations


def set_installer_deps(loader, registry, credential_store, validation_store=None) -> None:
    """Wire dependencies from orchestrator."""
    global _module_loader, _module_registry, _credential_store, _validation_store
    _module_loader = loader
    _module_registry = registry
    _credential_store = credential_store
    _validation_store = validation_store or {}


def install_module(module_id: str, validation_attestation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Install a validated module into the live system.

    Hot-loads the adapter into the registry so it's immediately
    available for queries. Records the installation in the
    persistent database for restart survival.

    Only call this after validate_module() returns success
    AND the user has explicitly approved the installation.

    Pre-install checks:
    1. Validation status must be VALIDATED (not FAILED, ERROR, or PENDING)
    2. bundle_sha256 in attestation must match the actual bundle being installed
    3. Attestation must reference the most recent validation report

    Args:
        module_id: Module identifier in "category/platform" format
        validation_attestation: Optional validation attestation with bundle_sha256

    Returns:
        Dict with installation status, whether credentials are needed,
        and instructions for the user
    """
    parts = module_id.split("/")
    if len(parts) != 2:
        return {"status": "error", "error": f"Invalid module_id: {module_id}"}

    category, platform = parts
    module_dir = MODULES_DIR / category / platform
    manifest_path = module_dir / "manifest.json"

    if not manifest_path.exists():
        return {
            "status": "error",
            "error": f"Module not found: {module_id}. Run build_module() first.",
        }

    manifest = ModuleManifest.load(manifest_path)

    # ========== PRE-INSTALL CHECK 1: Validation status ==========
    if manifest.status == ModuleStatus.FAILED:
        _log_install_rejection(module_id, "validation_failed", "Module failed validation")
        return {
            "status": "error",
            "error": f"Module {module_id} failed validation. Fix errors and run validate_module() again.",
        }

    if manifest.status != ModuleStatus.VALIDATED and manifest.status != ModuleStatus.VALIDATED.value:
        _log_install_rejection(
            module_id, "not_validated", f"Status: {manifest.status}"
        )
        return {
            "status": "error",
            "error": (
                f"Module {module_id} has not been validated (status: {manifest.status}). "
                f"Call validate_module('{module_id}') first."
            ),
        }

    # ========== PRE-INSTALL CHECK 2: Bundle hash verification ==========
    if validation_attestation:
        attested_hash = validation_attestation.get("bundle_sha256")

        if not attested_hash:
            _log_install_rejection(
                module_id, "missing_attestation_hash", "Attestation missing bundle_sha256"
            )
            return {
                "status": "error",
                "error": "Validation attestation missing bundle_sha256 field",
            }

        # Compute current bundle hash
        adapter_file = module_dir / "adapter.py"
        test_file = module_dir / "test_adapter.py"

        current_files = {}
        if adapter_file.exists():
            current_files[f"{category}/{platform}/adapter.py"] = adapter_file.read_text()
        if test_file.exists():
            current_files[f"{category}/{platform}/test_adapter.py"] = test_file.read_text()
        if manifest_path.exists():
            current_files[f"{category}/{platform}/manifest.json"] = manifest_path.read_text()

        # Build artifact bundle to get current hash
        from shared.modules.artifacts import ArtifactBundleBuilder

        current_bundle = ArtifactBundleBuilder.build_from_dict(
            files=current_files,
            job_id="install_check",
            attempt_id=1,
            module_id=module_id
        )
        current_hash = current_bundle.bundle_sha256

        # Verify hashes match
        if current_hash != attested_hash:
            _log_install_rejection(
                module_id,
                "hash_mismatch",
                f"Expected {attested_hash}, got {current_hash}"
            )
            return {
                "status": "error",
                "error": (
                    f"Artifact integrity failure: bundle hash mismatch. "
                    f"Expected {attested_hash}, got {current_hash}. "
                    f"Files may have been modified after validation."
                ),
            }

    if not _module_loader:
        return {"status": "error", "error": "Module loader not available"}

    # ========== INSTALL APPROVED ==========

    if not _module_loader:
        return {"status": "error", "error": "Module loader not available"}

    # Hot-load into AdapterRegistry
    handle = _module_loader.load_module(manifest)

    if not handle.is_loaded:
        _log_install_rejection(module_id, "load_failed", str(handle.error))
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

    # Log successful installation
    _log_install_success(module_id, validation_attestation)

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


# ========== AUDIT TRAIL FUNCTIONS ==========


def _log_install_rejection(module_id: str, reason: str, details: str) -> None:
    """
    Log installation rejection to audit trail.

    Args:
        module_id: Module identifier
        reason: Rejection reason code (validation_failed, hash_mismatch, etc.)
        details: Additional context
    """
    from datetime import datetime, timezone
    import json

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_file = AUDIT_DIR / "install_rejections.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "module_id": module_id,
        "reason": reason,
        "details": details,
        "action": "install_rejected",
    }

    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.warning(f"Install rejected for {module_id}: {reason} - {details}")


def _log_install_success(
    module_id: str, validation_attestation: Optional[Dict[str, Any]]
) -> None:
    """
    Log successful installation to audit trail.

    Args:
        module_id: Module identifier
        validation_attestation: Validation attestation with bundle_sha256
    """
    from datetime import datetime, timezone
    import json

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_file = AUDIT_DIR / "install_success.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "module_id": module_id,
        "action": "install_success",
        "bundle_sha256": (
            validation_attestation.get("bundle_sha256") if validation_attestation else None
        ),
    }

    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(f"Install success logged for {module_id}")
