"""
Showroom Metrics Demo Adapter

Generates synthetic data to exercise the NEXUS module pipeline.
When fetched, it produces demo data points that show up in the
pipeline stream and validate the full module → adapter → dashboard flow.
"""
import random
import time
from typing import Dict, Any, List

from shared.adapters.base import BaseAdapter, AdapterConfig
from shared.adapters.registry import register_adapter


@register_adapter(
    category="showroom",
    platform="metrics_demo",
    display_name="Showroom Metrics Demo",
    description="Generates synthetic metrics for pipeline demonstration",
    icon="\U0001f3aa",
    requires_auth=False,
    auth_type="none",
)
class MetricsDemoAdapter(BaseAdapter[Dict[str, Any]]):
    """Produces synthetic data to validate the full NEXUS pipeline."""

    category = "showroom"
    platform = "metrics_demo"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        return {
            "items": [
                {
                    "metric": "demo_request_count",
                    "value": random.randint(10, 500),
                    "unit": "requests",
                    "timestamp": time.time(),
                },
                {
                    "metric": "demo_latency_ms",
                    "value": round(random.uniform(5.0, 200.0), 1),
                    "unit": "ms",
                    "timestamp": time.time(),
                },
                {
                    "metric": "demo_success_rate",
                    "value": round(random.uniform(0.90, 1.0), 4),
                    "unit": "ratio",
                    "timestamp": time.time(),
                },
            ],
            "module_status": "active",
            "pipeline_stage": "showroom",
        }

    def transform(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return raw_data.get("items", [])

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": True,
            "webhooks": False,
        }
