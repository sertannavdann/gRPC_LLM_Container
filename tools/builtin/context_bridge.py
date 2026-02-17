"""
ContextBridge - Service object bridging tool layer and dashboard service.

Fetches real context data via HTTP from the dashboard REST API and delegates
normalization to each adapter's normalize_category_for_tools() classmethod.

The orchestrator runs in a separate container from the dashboard service,
so we use HTTP calls instead of direct Python imports.
"""
import os
from typing import Dict, Any, Optional, List
import logging

import requests

logger = logging.getLogger(__name__)


class ContextBridge:
    """
    Service object injected into tools that need context data.

    Replaces the former module-level functions (fetch_context_sync,
    _normalize_context_for_tools) with an injectable class that
    delegates per-category normalization to adapter classmethods.
    """

    def __init__(
        self,
        dashboard_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 10,
    ):
        self.dashboard_url = dashboard_url or os.getenv(
            "DASHBOARD_URL", "http://dashboard:8001"
        )
        self.api_key = api_key or os.getenv("DASHBOARD_API_KEY") or os.getenv(
            "INTERNAL_API_KEY"
        )
        self.timeout = timeout

    @property
    def _headers(self) -> Optional[Dict[str, str]]:
        """Build auth headers for dashboard requests."""
        return {"X-API-Key": self.api_key} if self.api_key else None

    def fetch(
        self,
        categories: Optional[List[str]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        Fetch unified context from the dashboard service via HTTP.

        Args:
            categories: Optional list of categories to fetch
            user_id: User identifier

        Returns:
            Dict with context data or empty dict on failure
        """
        if os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true":
            logger.debug("Using mock context (USE_MOCK_CONTEXT=true)")
            return {}

        if categories:
            result = {}
            for category in categories:
                try:
                    resp = requests.get(
                        f"{self.dashboard_url}/context/{category}",
                        params={"user_id": user_id},
                        headers=self._headers,
                        timeout=self.timeout,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        result[category] = data.get("data", {})
                    else:
                        logger.warning(
                            f"Dashboard returned {resp.status_code} for {category}"
                        )
                except requests.RequestException as e:
                    logger.warning(f"Failed to fetch {category} context: {e}")
            return self.normalize(result)

        # Fetch full unified context
        try:
            resp = requests.get(
                f"{self.dashboard_url}/context",
                params={"user_id": user_id},
                headers=self._headers,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                raw_dict = resp.json()
                context_data = raw_dict.get("context", raw_dict)
                return self.normalize(context_data)
            else:
                logger.warning(
                    f"Dashboard returned {resp.status_code} for unified context"
                )
                return {}
        except requests.RequestException as e:
            logger.warning(f"Dashboard unreachable at {self.dashboard_url}: {e}")
            return {}

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegate normalization to each adapter's normalize_category_for_tools().

        Replaces the former hardcoded 6-category switch in
        _normalize_context_for_tools(). Each adapter knows its own data shape.
        """
        from shared.adapters.finance.cibc import CIBCAdapter
        from shared.adapters.weather.openweather import OpenWeatherAdapter
        from shared.adapters.calendar.google_calendar import GoogleCalendarAdapter
        from shared.adapters.gaming.clashroyale import ClashRoyaleAdapter

        adapter_map: Dict[str, type] = {
            "finance": CIBCAdapter,
            "weather": OpenWeatherAdapter,
            "calendar": GoogleCalendarAdapter,
            "gaming": ClashRoyaleAdapter,
        }

        result: Dict[str, Any] = {}

        for category, data in raw.items():
            if not data:
                continue
            adapter_cls = adapter_map.get(category)
            if adapter_cls:
                result[category] = adapter_cls.normalize_category_for_tools(data)
            else:
                # Categories without a real adapter (health, navigation)
                result[category] = {"status": "no adapter configured", "raw": data}

        return result

    def fetch_and_normalize(
        self,
        categories: Optional[List[str]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Convenience method: fetch + normalize in one call."""
        raw = self.fetch(categories=categories, user_id=user_id)
        return raw  # Already normalized inside fetch()

    @staticmethod
    def is_mock_mode() -> bool:
        """Check if mock mode is enabled."""
        return os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true"


# Backward-compat module-level functions for gradual migration
def fetch_context_sync(
    categories: Optional[List[str]] = None,
    user_id: str = "default",
) -> Dict[str, Any]:
    """Legacy wrapper — creates a temporary ContextBridge instance."""
    bridge = ContextBridge()
    return bridge.fetch(categories=categories, user_id=user_id)


def is_mock_mode() -> bool:
    """Legacy wrapper."""
    return ContextBridge.is_mock_mode()
