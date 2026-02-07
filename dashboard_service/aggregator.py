"""
Dashboard Aggregator - Unified Context Builder

The aggregator fetches data from all configured adapters and builds
a unified context object that can be used by ClawdBot and the UI.

Key features:
- Parallel fetching from multiple adapters
- Caching with configurable TTL
- Relevance-based data classification
- Platform-agnostic data normalization
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from shared.adapters.registry import AdapterRegistry, adapter_registry
from shared.adapters.base import AdapterConfig, AdapterResult, AdapterCategory
from shared.schemas.canonical import UnifiedContext
from .relevance import RelevanceEngine

logger = logging.getLogger(__name__)


@dataclass
class UserConfig:
    """
    User-specific configuration for adapters.
    Defines which platforms are enabled and credentials.
    """
    user_id: str
    
    # Enabled platforms per category
    finance: List[str] = field(default_factory=lambda: ["mock", "cibc"])
    calendar: List[str] = field(default_factory=lambda: ["mock"])
    health: List[str] = field(default_factory=lambda: ["mock"])
    navigation: List[str] = field(default_factory=lambda: ["mock"])
    
    # Platform credentials (keyed by platform name)
    credentials: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Settings per platform
    settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def get_enabled_platforms(self, category: str) -> List[str]:
        """Get list of enabled platforms for a category."""
        return getattr(self, category, [])
    
    def get_credentials(self, platform: str) -> Dict[str, Any]:
        """Get credentials for a platform."""
        return self.credentials.get(platform, {})
    
    def get_settings(self, platform: str) -> Dict[str, Any]:
        """Get settings for a platform."""
        return self.settings.get(platform, {})


class DashboardAggregator:
    """
    Dashboard aggregator that builds unified context from multiple adapters.
    
    The aggregator is the central hub for fetching and normalizing
    user data from various platforms (banks, calendars, health, maps).
    """
    
    def __init__(
        self,
        user_config: UserConfig,
        registry: Optional[AdapterRegistry] = None,
        cache_ttl_seconds: int = 300,  # 5 minutes default
    ):
        self.user_config = user_config
        self.registry = registry or adapter_registry
        self.cache_ttl = cache_ttl_seconds
        self.relevance_engine = RelevanceEngine()
        
        # In-memory cache (replace with Redis in production)
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
    
    async def get_unified_context(
        self,
        force_refresh: bool = False,
        categories: Optional[List[str]] = None,
    ) -> UnifiedContext:
        """
        Fetch and aggregate data from all configured adapters.
        
        Args:
            force_refresh: Bypass cache and fetch fresh data
            categories: List of categories to fetch (default: all)
        
        Returns:
            UnifiedContext with aggregated data from all platforms
        """
        user_id = self.user_config.user_id
        cache_key = f"context:{user_id}"
        
        # Check cache
        if not force_refresh and self._is_cached(cache_key):
            logger.debug(f"Returning cached context for {user_id}")
            return self._cache[cache_key]
        
        # Determine which categories to fetch
        all_categories = categories or ["finance", "calendar", "health", "navigation"]
        
        # Build fetch tasks for all enabled adapters
        tasks = []
        task_metadata = []
        
        for category in all_categories:
            platforms = self.user_config.get_enabled_platforms(category)
            
            for platform in platforms:
                if not self.registry.has_adapter(category, platform):
                    logger.warning(f"Adapter not found: {category}/{platform}")
                    continue
                
                # Create adapter config
                config = AdapterConfig(
                    category=AdapterCategory(category),
                    platform=platform,
                    credentials=self.user_config.get_credentials(platform),
                    settings=self.user_config.get_settings(platform),
                )
                
                # Create adapter and add fetch task
                adapter = self.registry.create_adapter(category, platform, config)
                tasks.append(adapter.fetch(config))
                task_metadata.append({"category": category, "platform": platform})
        
        # Execute all fetches in parallel
        logger.info(f"Fetching data from {len(tasks)} adapters for user {user_id}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        context = await self._build_context(results, task_metadata)
        
        # Apply relevance classification
        context.relevance = self.relevance_engine.classify(context)
        
        # Cache result
        self._cache[cache_key] = context
        self._cache_timestamps[cache_key] = datetime.now()
        
        return context
    
    async def _build_context(
        self,
        results: List[Any],
        task_metadata: List[Dict[str, str]],
    ) -> UnifiedContext:
        """Build unified context from adapter results."""
        context = UnifiedContext(user_id=self.user_config.user_id)
        
        # Group results by category
        category_data: Dict[str, Dict[str, Any]] = {
            "finance": {"transactions": [], "accounts": [], "platforms": []},
            "calendar": {"events": [], "platforms": []},
            "health": {"metrics": [], "today": {}, "platforms": []},
            "navigation": {"routes": [], "commute": {}, "platforms": []},
        }
        
        for i, result in enumerate(results):
            meta = task_metadata[i]
            category = meta["category"]
            platform = meta["platform"]
            
            if isinstance(result, Exception):
                logger.error(f"Adapter error {category}/{platform}: {result}")
                continue
            
            if not isinstance(result, AdapterResult):
                logger.error(f"Unexpected result type from {category}/{platform}")
                continue
            
            if not result.success:
                logger.warning(f"Adapter failed {category}/{platform}: {result.error}")
                continue
            
            # Add platform to list
            category_data[category]["platforms"].append(platform)
            context.last_updated[platform] = result.fetched_at
            
            # Process data by category
            if category == "finance":
                category_data["finance"]["transactions"].extend([
                    d.to_dict() for d in result.data
                ])
            
            elif category == "calendar":
                category_data["calendar"]["events"].extend([
                    d.to_dict() for d in result.data
                ])
            
            elif category == "health":
                category_data["health"]["metrics"].extend([
                    d.to_dict() for d in result.data
                ])
                # Get today's summary if available
                if hasattr(result, 'metadata') and 'today' in result.metadata:
                    category_data["health"]["today"] = result.metadata["today"]
            
            elif category == "navigation":
                category_data["navigation"]["routes"].extend([
                    d.to_dict() for d in result.data
                ])
        
        # Build final context structure
        context.finance = self._build_finance_summary(category_data["finance"])
        context.calendar = self._build_calendar_summary(category_data["calendar"])
        context.health = self._build_health_summary(category_data["health"])
        context.navigation = self._build_navigation_summary(category_data["navigation"])
        
        return context
    
    def _build_finance_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build finance summary from aggregated data."""
        transactions = data["transactions"]
        
        # Sort by timestamp (newest first)
        transactions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Calculate summary stats
        total_expenses = sum(
            t["amount"] for t in transactions 
            if t.get("category") == "expense"
        )
        total_income = sum(
            t["amount"] for t in transactions 
            if t.get("category") == "income"
        )
        
        return {
            "transactions": transactions[:20],  # Last 20
            "recent_count": len(transactions),
            "total_expenses_period": total_expenses,
            "total_income_period": total_income,
            "net_cashflow": total_income - total_expenses,
            "platforms": data["platforms"],
        }
    
    def _build_calendar_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build calendar summary from aggregated data."""
        events = data["events"]
        now = datetime.now()
        
        # Sort by start time
        events.sort(key=lambda x: x.get("start_time", ""))
        
        # Filter upcoming events
        upcoming = [
            e for e in events 
            if e.get("start_time", "") > now.isoformat()
        ]
        
        # Get next 3 events
        next_3 = upcoming[:3]
        
        # Find events in next 2 hours (HIGH urgency)
        two_hours = (now + timedelta(hours=2)).isoformat()
        imminent = [
            e for e in upcoming 
            if e.get("start_time", "") < two_hours
        ]
        
        return {
            "events": events[:30],  # Next 30 events
            "next_3": next_3,
            "imminent": imminent,
            "today_count": len([
                e for e in events 
                if e.get("start_time", "")[:10] == now.date().isoformat()
            ]),
            "platforms": data["platforms"],
        }
    
    def _build_health_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build health summary from aggregated data."""
        metrics = data["metrics"]
        today = data.get("today", {})
        
        # Sort by timestamp (newest first)
        metrics.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "metrics": metrics[:50],  # Last 50 readings
            "today": today,
            "steps": today.get("steps", 0),
            "steps_goal": today.get("goal_steps", 10000),
            "steps_progress": today.get("steps_progress", 0),
            "heart_rate": today.get("current_heart_rate"),
            "hrv": today.get("hrv"),
            "sleep_hours": today.get("sleep_last_night"),
            "sleep_score": today.get("sleep_score"),
            "readiness": today.get("readiness"),
            "platforms": data["platforms"],
        }
    
    def _build_navigation_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build navigation summary from aggregated data."""
        routes = data["routes"]
        
        # Get primary route
        primary = routes[0] if routes else None
        
        return {
            "routes": routes,
            "primary_route": primary,
            "commute": data.get("commute", {}),
            "platforms": data["platforms"],
        }
    
    def _is_cached(self, key: str) -> bool:
        """Check if cache entry is valid."""
        if key not in self._cache:
            return False
        
        timestamp = self._cache_timestamps.get(key)
        if not timestamp:
            return False
        
        age = (datetime.now() - timestamp).total_seconds()
        return age < self.cache_ttl
    
    def clear_cache(self, user_id: Optional[str] = None) -> None:
        """Clear cache for a user or all users."""
        if user_id:
            key = f"context:{user_id}"
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
    
    async def get_category_data(
        self,
        category: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch data for a single category.
        
        Useful for refreshing specific widgets without full context rebuild.
        """
        context = await self.get_unified_context(
            force_refresh=force_refresh,
            categories=[category],
        )
        
        return getattr(context, category, {})


# Convenience function for quick context retrieval
async def get_user_context(
    user_id: str,
    platforms: Optional[Dict[str, List[str]]] = None,
) -> UnifiedContext:
    """
    Quick access to user context with default configuration.
    
    Args:
        user_id: User identifier
        platforms: Optional dict of category -> platform list
    
    Returns:
        UnifiedContext with aggregated user data
    """
    config = UserConfig(user_id=user_id)
    
    if platforms:
        for category, platform_list in platforms.items():
            setattr(config, category, platform_list)
    
    aggregator = DashboardAggregator(config)
    return await aggregator.get_unified_context()
