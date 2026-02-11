"""
Hello World Test Adapter - Verifies dynamic module loading works.

This module is loaded by ModuleLoader at runtime and registers itself
via @register_adapter. If this adapter appears in AdapterRegistry,
the dynamic loading pipeline is working correctly.
"""
from typing import Dict, Any, List

from shared.adapters.base import BaseAdapter, AdapterConfig
from shared.adapters.registry import register_adapter


@register_adapter(
    category="test",
    platform="hello",
    display_name="Hello World Test",
    description="Smoke-test adapter for dynamic loading",
    icon="🧪",
    requires_auth=False,
    auth_type="none",
)
class HelloAdapter(BaseAdapter[Dict[str, Any]]):
    """Minimal adapter that returns a greeting."""

    category = "test"
    platform = "hello"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        return {"items": [{"message": "Hello from dynamic module!", "status": "ok"}]}

    def transform(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return raw_data.get("items", [])

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": False,
            "webhooks": False,
        }
