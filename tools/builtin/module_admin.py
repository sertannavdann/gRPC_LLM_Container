"""
ModuleAdminTool - Consolidated module management and lifecycle operations.

Replaces:
    - module_manager.py (list, enable, disable, credentials)
    - module_installer.py (uninstall)
    - orchestrator closures (draft/version tools)

Uses CompositeTool with ActionStrategy dispatch.
"""
import json
import logging
from typing import Dict, Any, Optional

from tools.base import CompositeTool, ActionStrategy

logger = logging.getLogger(__name__)


class ListStrategy(ActionStrategy):
    """List all installed and available modules."""
    action_name = "list"
    description = "List all installed and available modules"

    def __init__(self, module_loader=None, module_registry=None, credential_store=None):
        self._module_loader = module_loader
        self._module_registry = module_registry
        self._credential_store = credential_store

    def execute(self, **kwargs) -> Dict[str, Any]:
        modules = []
        if self._module_loader:
            for m in self._module_loader.list_modules():
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
                if self._credential_store and entry["requires_api_key"]:
                    entry["has_credentials"] = self._credential_store.has_credentials(
                        entry["module_id"]
                    )
                modules.append(entry)
        return {
            "status": "success",
            "modules": modules,
            "total": len(modules),
            "loaded": sum(1 for m in modules if m.get("is_loaded")),
        }


class EnableStrategy(ActionStrategy):
    action_name = "enable"
    description = "Enable a disabled module and load it"

    def __init__(self, module_loader=None, module_registry=None):
        self._module_loader = module_loader
        self._module_registry = module_registry

    def execute(self, **kwargs) -> Dict[str, Any]:
        module_id = kwargs.get("module_id")
        if not self._module_loader:
            return {"status": "error", "error": "Module loader not available"}
        try:
            handle = self._module_loader.enable_module(module_id)
            if self._module_registry:
                self._module_registry.enable(module_id)
            return {"status": "success", "module_id": module_id, "is_loaded": handle.is_loaded,
                    "message": f"Module {module_id} enabled and loaded."}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class DisableStrategy(ActionStrategy):
    action_name = "disable"
    description = "Disable a module without uninstalling it"

    def __init__(self, module_loader=None, module_registry=None):
        self._module_loader = module_loader
        self._module_registry = module_registry

    def execute(self, **kwargs) -> Dict[str, Any]:
        module_id = kwargs.get("module_id")
        if not self._module_loader:
            return {"status": "error", "error": "Module loader not available"}
        success = self._module_loader.disable_module(module_id)
        if self._module_registry:
            self._module_registry.disable(module_id)
        if success:
            return {"status": "success", "module_id": module_id, "message": f"Module {module_id} disabled."}
        return {"status": "error", "error": f"Module {module_id} not found"}


class CredentialStrategy(ActionStrategy):
    action_name = "credentials"
    description = "Store API credentials for a module"

    def __init__(self, credential_store=None, module_loader=None):
        self._credential_store = credential_store
        self._module_loader = module_loader

    def execute(self, **kwargs) -> Dict[str, Any]:
        module_id = kwargs.get("module_id")
        api_key = kwargs.get("api_key", "")
        credentials_json = kwargs.get("credentials_json", "")

        if not self._credential_store:
            return {"status": "error", "error": "Credential store not available"}

        if credentials_json:
            try:
                creds = json.loads(credentials_json)
            except json.JSONDecodeError:
                return {"status": "error", "error": "Invalid JSON in credentials_json"}
        elif api_key:
            creds = {"api_key": api_key}
        else:
            return {"status": "error", "error": "Provide either api_key or credentials_json"}

        self._credential_store.store(module_id, creds)

        if self._module_loader:
            handle = self._module_loader.get_module(module_id)
            if handle and handle.is_loaded:
                self._module_loader.reload_module(module_id)

        return {"status": "success", "module_id": module_id,
                "message": f"Credentials stored for {module_id}. Module reloaded."}


class UninstallStrategy(ActionStrategy):
    action_name = "uninstall"
    description = "Uninstall a module from the live system"

    def __init__(self, module_loader=None, module_registry=None):
        self._module_loader = module_loader
        self._module_registry = module_registry

    def execute(self, **kwargs) -> Dict[str, Any]:
        from tools.builtin.module_installer import uninstall_module as _uninstall
        return _uninstall(**kwargs)


class CreateDraftStrategy(ActionStrategy):
    action_name = "create_draft"
    description = "Create a new draft from an installed module for editing"

    def __init__(self, draft_manager=None):
        self._dm = draft_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._dm:
            return {"status": "error", "error": "Draft manager not available"}
        return self._dm.create_draft(module_id=kwargs.get("module_id"), actor="chat_agent")


class EditDraftStrategy(ActionStrategy):
    action_name = "edit_draft"
    description = "Edit a file in a draft workspace"

    def __init__(self, draft_manager=None):
        self._dm = draft_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._dm:
            return {"status": "error", "error": "Draft manager not available"}
        return self._dm.edit_file(
            draft_id=kwargs.get("draft_id"),
            file_path=kwargs.get("file_path"),
            content=kwargs.get("content"),
            actor="chat_agent",
        )


class DiffDraftStrategy(ActionStrategy):
    action_name = "diff_draft"
    description = "Show unified diff of draft changes vs source module"

    def __init__(self, draft_manager=None):
        self._dm = draft_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._dm:
            return {"status": "error", "error": "Draft manager not available"}
        return self._dm.get_diff(draft_id=kwargs.get("draft_id"), actor="chat_agent")


class ValidateDraftStrategy(ActionStrategy):
    action_name = "validate_draft"
    description = "Run validation pipeline on a draft"

    def __init__(self, draft_manager=None):
        self._dm = draft_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._dm:
            return {"status": "error", "error": "Draft manager not available"}
        return self._dm.validate_draft(draft_id=kwargs.get("draft_id"), actor="chat_agent")


class PromoteDraftStrategy(ActionStrategy):
    action_name = "promote_draft"
    description = "Promote a validated draft to a new module version"

    def __init__(self, draft_manager=None):
        self._dm = draft_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._dm:
            return {"status": "error", "error": "Draft manager not available"}
        return self._dm.promote_draft(draft_id=kwargs.get("draft_id"), actor="chat_agent")


class ListVersionsStrategy(ActionStrategy):
    action_name = "list_versions"
    description = "List all versions of a module"

    def __init__(self, version_manager=None):
        self._vm = version_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._vm:
            return {"status": "error", "error": "Version manager not available"}
        versions = self._vm.list_versions(module_id=kwargs.get("module_id"))
        return {"status": "success", "versions": versions}


class RollbackVersionStrategy(ActionStrategy):
    action_name = "rollback_version"
    description = "Roll back a module to a specific prior version"

    def __init__(self, version_manager=None):
        self._vm = version_manager

    def execute(self, **kwargs) -> Dict[str, Any]:
        if not self._vm:
            return {"status": "error", "error": "Version manager not available"}
        return self._vm.rollback_to_version(
            module_id=kwargs.get("module_id"),
            target_version_id=kwargs.get("target_version_id"),
            actor="chat_agent",
        )


class ModuleAdminTool(CompositeTool):
    """
    Consolidated module administration: list, enable, disable, credentials,
    uninstall, draft lifecycle, version management.
    """

    name = "module_admin"
    description = (
        "Module administration: list, enable, disable, credentials, uninstall, "
        "create_draft, edit_draft, diff_draft, validate_draft, promote_draft, "
        "list_versions, rollback_version."
    )
    version = "2.0.0"

    def __init__(
        self,
        module_loader=None,
        module_registry=None,
        credential_store=None,
        draft_manager=None,
        version_manager=None,
    ):
        super().__init__()

        self._register_strategy(ListStrategy(module_loader, module_registry, credential_store))
        self._register_strategy(EnableStrategy(module_loader, module_registry))
        self._register_strategy(DisableStrategy(module_loader, module_registry))
        self._register_strategy(CredentialStrategy(credential_store, module_loader))
        self._register_strategy(UninstallStrategy(module_loader, module_registry))
        self._register_strategy(CreateDraftStrategy(draft_manager))
        self._register_strategy(EditDraftStrategy(draft_manager))
        self._register_strategy(DiffDraftStrategy(draft_manager))
        self._register_strategy(ValidateDraftStrategy(draft_manager))
        self._register_strategy(PromoteDraftStrategy(draft_manager))
        self._register_strategy(ListVersionsStrategy(version_manager))
        self._register_strategy(RollbackVersionStrategy(version_manager))
