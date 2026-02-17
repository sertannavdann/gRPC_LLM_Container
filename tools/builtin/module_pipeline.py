"""
ModulePipelineTool - Consolidated module build/write/repair/validate/install.

Replaces:
    - module_builder.py (build_module, write_module_code, repair_module)
    - module_validator.py (validate_module)
    - module_installer.py (install_module)

Uses CompositeTool with ActionStrategy dispatch.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from tools.base import CompositeTool, ActionStrategy

logger = logging.getLogger(__name__)


class BuildStrategy(ActionStrategy):
    """Create a new adapter module scaffold."""
    action_name = "build"
    description = "Create a new adapter module using LLM-driven stage pipeline"

    def __init__(self, llm_gateway=None, modules_dir=None, audit_dir=None):
        self._llm_gateway = llm_gateway
        self._modules_dir = Path(modules_dir or os.getenv("MODULES_DIR", "/app/modules"))
        self._audit_dir = Path(audit_dir or os.getenv("AUDIT_DIR", "/app/data/audit"))

    def execute(self, **kwargs) -> Dict[str, Any]:
        # Import the original function and call it
        from tools.builtin.module_builder import build_module as _build
        return _build(**kwargs)


class WriteCodeStrategy(ActionStrategy):
    """Write or update adapter code for an existing module."""
    action_name = "write_code"
    description = "Write or update the adapter code for an existing module"

    def execute(self, **kwargs) -> Dict[str, Any]:
        from tools.builtin.module_builder import write_module_code as _write
        return _write(**kwargs)


class RepairStrategy(ActionStrategy):
    """Repair module using LLM with bounded retry loop."""
    action_name = "repair"
    description = "Repair module adapter code using LLM with validation feedback"

    def execute(self, **kwargs) -> Dict[str, Any]:
        from tools.builtin.module_builder import repair_module as _repair
        return _repair(**kwargs)


class ValidateStrategy(ActionStrategy):
    """Validate an adapter module with static + runtime checks."""
    action_name = "validate"
    description = "Validate an adapter module with merged static + runtime checks"

    def __init__(self, sandbox_client=None):
        self._sandbox_client = sandbox_client

    def execute(self, **kwargs) -> Dict[str, Any]:
        from tools.builtin.module_validator import validate_module as _validate
        return _validate(**kwargs)


class InstallStrategy(ActionStrategy):
    """Install a validated module into the live system."""
    action_name = "install"
    description = "Install a validated module into the live system"

    def __init__(self, module_loader=None, module_registry=None, credential_store=None):
        self._module_loader = module_loader
        self._module_registry = module_registry
        self._credential_store = credential_store

    def execute(self, **kwargs) -> Dict[str, Any]:
        from tools.builtin.module_installer import install_module as _install
        return _install(**kwargs)


class ModulePipelineTool(CompositeTool):
    """
    Consolidated module pipeline: build, write_code, repair, validate, install.

    Actions:
        - build: Create module scaffold
        - write_code: Write adapter code
        - repair: LLM-driven repair
        - validate: Static + runtime validation
        - install: Deploy to live system
    """

    name = "module_pipeline"
    description = (
        "Module build pipeline: build, write_code, repair, validate, install. "
        "Use action='build' to create, action='validate' to test, action='install' to deploy."
    )
    version = "2.0.0"

    def __init__(
        self,
        llm_gateway=None,
        sandbox_client=None,
        modules_dir=None,
        audit_dir=None,
        module_loader=None,
        module_registry=None,
        credential_store=None,
    ):
        super().__init__()

        self._register_strategy(BuildStrategy(
            llm_gateway=llm_gateway,
            modules_dir=modules_dir,
            audit_dir=audit_dir,
        ))
        self._register_strategy(WriteCodeStrategy())
        self._register_strategy(RepairStrategy())
        self._register_strategy(ValidateStrategy(sandbox_client=sandbox_client))
        self._register_strategy(InstallStrategy(
            module_loader=module_loader,
            module_registry=module_registry,
            credential_store=credential_store,
        ))
