"""
Module Loader - Dynamic import and lifecycle management for NEXUS modules.

Uses importlib to load adapter modules from the modules/ directory at runtime.
The @register_adapter decorator fires automatically on import, so no special
registration logic is needed — just importing the module file is sufficient.

Key design decisions:
- importlib.util.spec_from_file_location() for arbitrary path loading
- Parent package pre-loaded before child modules (Python requirement)
- ModuleHandle tracks loaded state for clean unload/reload
- AdapterRegistry.unregister() used for clean removal
"""
import importlib
import importlib.util
import logging
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .manifest import ModuleManifest, ModuleStatus

logger = logging.getLogger(__name__)


@dataclass
class ModuleHandle:
    """Tracks a loaded module's runtime state."""
    manifest: ModuleManifest
    module_obj: Optional[types.ModuleType] = None
    module_path: Optional[Path] = None
    loaded_at: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return self.module_obj is not None

    @property
    def module_id(self) -> str:
        return self.manifest.module_id


class ModuleLoader:
    """
    Dynamic module loader for NEXUS.

    Discovers, loads, and manages adapter modules from a directory structure:
        modules/{category}/{platform}/
            manifest.json
            adapter.py      (contains @register_adapter decorated class)
            test_adapter.py

    Usage:
        loader = ModuleLoader(modules_dir=Path("modules"))
        loaded = loader.load_all_modules()
        loader.unload_module("gaming/clashroyale")
        loader.reload_module("gaming/clashroyale")
    """

    def __init__(self, modules_dir: Path):
        self.modules_dir = modules_dir
        self._loaded: Dict[str, ModuleHandle] = {}
        self._module_prefix = "nexus_modules"

    @property
    def loaded_modules(self) -> Dict[str, ModuleHandle]:
        return dict(self._loaded)

    def load_all_modules(self) -> List[ModuleHandle]:
        """
        Discover and load all modules from the modules directory.

        Returns list of ModuleHandle for each discovered module.
        Modules that fail to load are included with error details.
        """
        manifests = ModuleManifest.discover(self.modules_dir)
        results = []

        for manifest in manifests:
            if manifest.status in (ModuleStatus.DISABLED, ModuleStatus.UNINSTALLED):
                logger.info(f"Skipping disabled/uninstalled module: {manifest.module_id}")
                continue

            handle = self.load_module(manifest)
            results.append(handle)

        logger.info(
            f"Module loader: {sum(1 for h in results if h.is_loaded)}/{len(results)} "
            f"modules loaded successfully"
        )
        return results

    def load_module(self, manifest_or_path) -> ModuleHandle:
        """
        Load a single module by manifest or path.

        Args:
            manifest_or_path: ModuleManifest instance or Path to manifest.json

        Returns:
            ModuleHandle with loaded module or error details.
        """
        if isinstance(manifest_or_path, Path):
            manifest = ModuleManifest.load(manifest_or_path)
        else:
            manifest = manifest_or_path

        module_id = manifest.module_id

        # Already loaded? Return existing handle.
        if module_id in self._loaded and self._loaded[module_id].is_loaded:
            logger.debug(f"Module already loaded: {module_id}")
            return self._loaded[module_id]

        # Resolve the adapter file
        adapter_file = self.modules_dir / manifest.category / manifest.platform / manifest.entry_point
        if not adapter_file.exists():
            error = f"Entry point not found: {adapter_file}"
            logger.error(error)
            handle = ModuleHandle(manifest=manifest, error=error)
            self._loaded[module_id] = handle
            return handle

        # Build a unique module name for sys.modules
        module_name = f"{self._module_prefix}.{manifest.category}.{manifest.platform}"

        try:
            # Ensure parent packages exist in sys.modules for relative imports
            self._ensure_parent_packages(manifest.category, manifest.platform)

            # Load using importlib
            spec = importlib.util.spec_from_file_location(
                module_name,
                str(adapter_file),
                submodule_search_locations=[str(adapter_file.parent)]
            )
            if spec is None or spec.loader is None:
                error = f"Could not create module spec for {adapter_file}"
                logger.error(error)
                handle = ModuleHandle(manifest=manifest, error=error)
                self._loaded[module_id] = handle
                return handle

            module_obj = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module_obj

            # Execute the module — @register_adapter fires here
            spec.loader.exec_module(module_obj)

            handle = ModuleHandle(
                manifest=manifest,
                module_obj=module_obj,
                module_path=adapter_file,
                loaded_at=datetime.utcnow().isoformat(),
            )
            self._loaded[module_id] = handle

            # Update manifest status
            manifest.status = ModuleStatus.INSTALLED
            manifest.health_status = "healthy"

            logger.info(f"Loaded module: {module_id} from {adapter_file}")
            return handle

        except Exception as e:
            error = f"Failed to load module {module_id}: {e}"
            logger.error(error, exc_info=True)

            # Clean up partial load
            if module_name in sys.modules:
                del sys.modules[module_name]

            manifest.status = ModuleStatus.FAILED
            manifest.health_status = "unhealthy"

            handle = ModuleHandle(manifest=manifest, error=error)
            self._loaded[module_id] = handle
            return handle

    def unload_module(self, module_id: str) -> bool:
        """
        Unload a module and remove it from the adapter registry.

        Args:
            module_id: "category/platform" identifier

        Returns:
            True if module was unloaded, False if not found.
        """
        handle = self._loaded.get(module_id)
        if handle is None:
            logger.warning(f"Module not found for unload: {module_id}")
            return False

        manifest = handle.manifest

        # Remove from AdapterRegistry
        try:
            from shared.adapters.registry import adapter_registry
            adapter_registry.unregister(manifest.category, manifest.platform)
        except Exception as e:
            logger.warning(f"Failed to unregister adapter {module_id}: {e}")

        # Remove from sys.modules
        module_name = f"{self._module_prefix}.{manifest.category}.{manifest.platform}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Update state
        handle.module_obj = None
        handle.loaded_at = None
        manifest.status = ModuleStatus.UNINSTALLED

        logger.info(f"Unloaded module: {module_id}")
        return True

    def reload_module(self, module_id: str) -> ModuleHandle:
        """
        Unload then reload a module (picks up code changes).

        Args:
            module_id: "category/platform" identifier

        Returns:
            ModuleHandle with fresh load state.
        """
        handle = self._loaded.get(module_id)
        if handle is None:
            raise ValueError(f"Module not found: {module_id}")

        manifest = handle.manifest
        self.unload_module(module_id)
        return self.load_module(manifest)

    def disable_module(self, module_id: str) -> bool:
        """Unload a module and mark it disabled (won't load on startup)."""
        handle = self._loaded.get(module_id)
        if handle is None:
            return False

        self.unload_module(module_id)
        handle.manifest.status = ModuleStatus.DISABLED

        # Persist disabled state to manifest.json
        manifest_file = (
            self.modules_dir / handle.manifest.category
            / handle.manifest.platform / "manifest.json"
        )
        if manifest_file.exists():
            handle.manifest.save(self.modules_dir)

        logger.info(f"Disabled module: {module_id}")
        return True

    def enable_module(self, module_id: str) -> ModuleHandle:
        """Re-enable a disabled module and load it."""
        handle = self._loaded.get(module_id)
        if handle is None:
            # Try to discover from disk
            parts = module_id.split("/")
            if len(parts) != 2:
                raise ValueError(f"Invalid module_id format: {module_id}")
            manifest_path = self.modules_dir / parts[0] / parts[1] / "manifest.json"
            if not manifest_path.exists():
                raise ValueError(f"Module manifest not found: {manifest_path}")
            handle = ModuleHandle(manifest=ModuleManifest.load(manifest_path))

        handle.manifest.status = ModuleStatus.PENDING
        handle.manifest.save(self.modules_dir)
        return self.load_module(handle.manifest)

    def get_module(self, module_id: str) -> Optional[ModuleHandle]:
        """Get a loaded module's handle."""
        return self._loaded.get(module_id)

    def list_modules(self) -> List[Dict]:
        """List all known modules with their status."""
        # Include both loaded and discovered-on-disk modules
        known = {}

        # Start with loaded modules
        for mid, handle in self._loaded.items():
            known[mid] = handle.manifest.to_dict()
            known[mid]["is_loaded"] = handle.is_loaded
            known[mid]["loaded_at"] = handle.loaded_at
            known[mid]["error"] = handle.error

        # Add any on-disk modules not yet loaded
        for manifest in ModuleManifest.discover(self.modules_dir):
            mid = manifest.module_id
            if mid not in known:
                known[mid] = manifest.to_dict()
                known[mid]["is_loaded"] = False
                known[mid]["loaded_at"] = None
                known[mid]["error"] = None

        return list(known.values())

    def _ensure_parent_packages(self, category: str, platform: str) -> None:
        """
        Ensure parent package stubs exist in sys.modules.
        Python requires parent packages to be loaded before child modules.
        """
        root = self._module_prefix
        if root not in sys.modules:
            pkg = types.ModuleType(root)
            pkg.__path__ = [str(self.modules_dir)]
            pkg.__package__ = root
            sys.modules[root] = pkg

        cat_name = f"{root}.{category}"
        if cat_name not in sys.modules:
            cat_dir = self.modules_dir / category
            pkg = types.ModuleType(cat_name)
            pkg.__path__ = [str(cat_dir)]
            pkg.__package__ = cat_name
            sys.modules[cat_name] = pkg
