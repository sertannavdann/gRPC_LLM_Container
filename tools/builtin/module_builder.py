"""
Module Builder Tool — creates adapter module scaffolding for the LLM.

When the orchestrator detects a "build me X" intent, this tool creates
the directory structure, manifest, and code skeleton. The LLM then
fills in the API-specific fetch/transform logic.

Flow:
    1. LLM calls build_module() with high-level spec
    2. Tool creates modules/{category}/{platform}/ with manifest + skeleton
    3. Returns the skeleton code for LLM to refine with API-specific logic
    4. LLM calls write_module_code() with the refined adapter code
    5. LLM calls validate_module() to test in sandbox
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from shared.modules.manifest import ModuleManifest, ModuleStatus, ValidationResults
from shared.modules.templates.adapter_template import generate_adapter_code
from shared.modules.templates.test_template import generate_test_code

logger = logging.getLogger(__name__)

MODULES_DIR = Path(os.getenv("MODULES_DIR", "/app/modules"))


def build_module(
    name: str,
    category: str,
    platform: str = "",
    description: str = "",
    api_base_url: str = "https://api.example.com/v1",
    requires_api_key: bool = True,
    auth_type: str = "api_key",
    icon: str = "🔌",
    display_name: str = "",
) -> Dict[str, Any]:
    """
    Create a new adapter module with scaffolding code.

    Use this tool when the user asks to build, create, or add a new
    integration or data source. This generates the module directory,
    manifest, adapter skeleton, and test file.

    After calling this, review the generated code and call
    write_module_code() to customize the API-specific logic, then
    call validate_module() to test it.

    Args:
        name (str): Module name, e.g. "clashroyale" or "apple_health".
        category (str): Module category, e.g. "gaming", "health", "finance",
            "weather", "social", "productivity".
        platform (str): Platform identifier. Defaults to name if not provided.
        description (str): Human-readable description of what this module does.
        api_base_url (str): Base URL of the API to integrate with.
        requires_api_key (bool): Whether the API needs authentication. Default True.
        auth_type (str): Authentication type — "api_key", "oauth2", "basic", "none".
        icon (str): Emoji icon for the module.
        display_name (str): Human-readable display name.

    Returns:
        Dict with status, module_id, generated file paths, and skeleton code.
    """
    if not platform:
        platform = name

    if not display_name:
        display_name = name.replace("_", " ").title()

    module_dir = MODULES_DIR / category / platform

    # Check if module already exists
    if module_dir.exists() and (module_dir / "manifest.json").exists():
        return {
            "status": "error",
            "error": f"Module {category}/{platform} already exists. Use write_module_code() to update it.",
            "module_id": f"{category}/{platform}",
        }

    # Create manifest
    manifest = ModuleManifest(
        name=name,
        category=category,
        platform=platform,
        display_name=display_name,
        description=description,
        icon=icon,
        requires_api_key=requires_api_key,
        auth_type=auth_type,
        status=ModuleStatus.PENDING,
        created_by="executor_agent",
    )

    # Generate adapter code skeleton
    adapter_code = generate_adapter_code(
        module_name=name,
        category=category,
        platform=platform,
        display_name=display_name,
        description=description,
        icon=icon,
        class_name=manifest.class_name,
        requires_auth=requires_api_key,
        auth_type=auth_type,
        api_base_url=api_base_url,
    )

    # Generate test code
    test_code = generate_test_code(
        class_name=manifest.class_name,
        module_name=name,
        category=category,
        platform=platform,
        requires_auth=requires_api_key,
        api_base_url=api_base_url,
    )

    # Write files
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest.save(MODULES_DIR)
    (module_dir / "adapter.py").write_text(adapter_code)
    (module_dir / "test_adapter.py").write_text(test_code)

    logger.info(f"Module scaffolding created: {manifest.module_id}")

    return {
        "status": "success",
        "module_id": manifest.module_id,
        "module_dir": str(module_dir),
        "files_created": [
            str(module_dir / "manifest.json"),
            str(module_dir / "adapter.py"),
            str(module_dir / "test_adapter.py"),
        ],
        "class_name": manifest.class_name,
        "adapter_code": adapter_code,
        "instructions": (
            f"Module skeleton created at {module_dir}. "
            f"The adapter.py contains a default fetch/transform implementation. "
            f"Customize the fetch_raw() and transform() methods for the "
            f"{display_name} API, then call write_module_code() with the "
            f"updated code, and validate_module() to test it."
        ),
    }


def write_module_code(
    module_id: str,
    adapter_code: str,
    test_code: str = "",
) -> Dict[str, Any]:
    """
    Write or update the adapter code for an existing module.

    Use this after build_module() to write the LLM-generated
    API-specific adapter logic. The module_id is "{category}/{platform}".

    Args:
        module_id (str): Module identifier in "category/platform" format,
            e.g. "gaming/clashroyale".
        adapter_code (str): Complete Python source code for adapter.py.
            Must contain a class decorated with @register_adapter.
        test_code (str): Optional updated test code. If empty, keeps existing tests.

    Returns:
        Dict with status and file paths written.
    """
    parts = module_id.split("/")
    if len(parts) != 2:
        return {"status": "error", "error": f"Invalid module_id: {module_id}. Expected 'category/platform'."}

    category, platform = parts
    module_dir = MODULES_DIR / category / platform

    if not module_dir.exists():
        return {"status": "error", "error": f"Module directory not found: {module_dir}. Call build_module() first."}

    # Syntax check before writing
    try:
        compile(adapter_code, f"{module_id}/adapter.py", "exec")
    except SyntaxError as e:
        return {
            "status": "error",
            "error": f"Syntax error in adapter code: {e}",
            "line": e.lineno,
            "offset": e.offset,
        }

    # Write adapter
    (module_dir / "adapter.py").write_text(adapter_code)
    files_written = [str(module_dir / "adapter.py")]

    # Write tests if provided
    if test_code:
        try:
            compile(test_code, f"{module_id}/test_adapter.py", "exec")
        except SyntaxError as e:
            return {
                "status": "error",
                "error": f"Syntax error in test code: {e}",
                "line": e.lineno,
            }
        (module_dir / "test_adapter.py").write_text(test_code)
        files_written.append(str(module_dir / "test_adapter.py"))

    # Update manifest status
    manifest_path = module_dir / "manifest.json"
    if manifest_path.exists():
        manifest = ModuleManifest.load(manifest_path)
        manifest.status = ModuleStatus.PENDING
        manifest.save(MODULES_DIR)

    logger.info(f"Module code written: {module_id}")

    return {
        "status": "success",
        "module_id": module_id,
        "files_written": files_written,
        "instructions": f"Code written. Call validate_module('{module_id}') to test it.",
    }
