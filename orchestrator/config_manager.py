"""
Configuration manager with hot-reload and observer pattern.

Loads/saves RoutingConfig from JSON, notifies observers on changes.
Thread-safe for concurrent gRPC workers.
"""

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, List

from .routing_config import (
    RoutingConfig,
    CategoryRouting,
    TierConfig,
    PerformanceConstraints,
)

logger = logging.getLogger(__name__)


def _build_default_config() -> RoutingConfig:
    """Build default RoutingConfig from current hardcoded values + env vars."""
    from .capability_map import CAPABILITY_MAP

    categories = {}
    for name, entry in CAPABILITY_MAP.items():
        categories[name] = CategoryRouting(
            tier=entry.get("tier", "standard"),
            priority=entry.get("priority", "medium"),
        )

    tiers = {
        "heavy": TierConfig(
            endpoint=os.getenv("LLM_HEAVY_HOST", "llm_service:50051"),
            priority=1,
        ),
        "standard": TierConfig(
            endpoint=os.getenv("LLM_STANDARD_HOST", "llm_service_standard:50051"),
            priority=2,
        ),
    }

    ultra_host = os.getenv("LLM_ULTRA_HOST", "")
    if ultra_host:
        tiers["ultra"] = TierConfig(endpoint=ultra_host, priority=0)

    return RoutingConfig(
        version="1.0",
        categories=categories,
        tiers=tiers,
        performance=PerformanceConstraints(),
    )


class ConfigManager:
    """
    Manages RoutingConfig lifecycle: load, save, reload, observe.

    Thread-safe via RLock. Observers are called synchronously on update.
    """

    def __init__(self, config_path: str):
        self._config_path = Path(config_path)
        self._lock = threading.RLock()
        self._observers: List[Callable[[RoutingConfig], None]] = []
        self._config = self._load_or_default()
        logger.info(
            f"ConfigManager initialized: path={self._config_path}, "
            f"categories={len(self._config.categories)}, "
            f"tiers={len(self._config.tiers)}"
        )

    def _load_or_default(self) -> RoutingConfig:
        """Load config from disk, or build defaults if file doesn't exist."""
        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text())
                config = RoutingConfig.model_validate(data)
                logger.info(f"Loaded routing config from {self._config_path}")
                return config
            except Exception as e:
                logger.warning(
                    f"Failed to load {self._config_path}: {e}. Using defaults."
                )

        config = _build_default_config()
        self._persist(config)
        return config

    def get_config(self) -> RoutingConfig:
        """Return current config (thread-safe read)."""
        with self._lock:
            return self._config

    def update_config(self, new_config: RoutingConfig) -> None:
        """Validate, persist, and notify observers of new config."""
        with self._lock:
            self._config = new_config
            self._persist(new_config)
        self._notify_observers(new_config)
        logger.info(f"Config updated: version={new_config.version}")

    def reload(self) -> RoutingConfig:
        """Reload config from disk and notify observers."""
        with self._lock:
            if not self._config_path.exists():
                logger.warning("Config file not found on reload, keeping current.")
                return self._config
            try:
                data = json.loads(self._config_path.read_text())
                self._config = RoutingConfig.model_validate(data)
                logger.info("Config reloaded from disk.")
            except Exception as e:
                logger.error(f"Reload failed: {e}. Keeping current config.")
                return self._config
            config = self._config
        self._notify_observers(config)
        return config

    def register_observer(self, callback: Callable[[RoutingConfig], None]) -> None:
        """Register a callback to be notified on config changes."""
        with self._lock:
            self._observers.append(callback)

    def _persist(self, config: RoutingConfig) -> None:
        """Atomically write config to disk (write to temp + rename)."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._config_path.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(config.model_dump_json(indent=2))
                os.replace(tmp_path, str(self._config_path))
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error(f"Failed to persist config: {e}")

    def _notify_observers(self, config: RoutingConfig) -> None:
        """Call all registered observers with new config."""
        with self._lock:
            observers = list(self._observers)
        for cb in observers:
            try:
                cb(config)
            except Exception as e:
                logger.error(f"Observer {cb} failed: {e}")
