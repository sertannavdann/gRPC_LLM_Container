"""
Mock Health Adapter - Development/Testing

Generates realistic mock health/fitness data for UI development.
Simulates data from Apple Health, Garmin, Oura, etc.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
import random
import uuid
import math

from ..base import BaseAdapter, AdapterConfig
from ..registry import register_adapter
from ...schemas.canonical import (
    HealthMetric,
    HealthSummary,
    MetricType,
)


@register_adapter(
    category="health",
    platform="mock",
    display_name="Mock Health",
    description="Development mock adapter with realistic health metrics",
    icon="💓",
    requires_auth=False,
)
class MockHealthAdapter(BaseAdapter[HealthMetric]):
    """
    Mock health adapter for development and testing.
    Generates realistic health metrics data.
    """
    
    category = "health"
    platform = "mock"
    
    # Baseline values for realistic data generation
    BASELINES = {
        MetricType.STEPS: {"mean": 8000, "std": 3000, "min": 500, "max": 20000},
        MetricType.HEART_RATE: {"mean": 72, "std": 8, "min": 50, "max": 180},
        MetricType.HRV: {"mean": 45, "std": 12, "min": 15, "max": 100},
        MetricType.SLEEP_DURATION: {"mean": 7.5, "std": 1.2, "min": 4, "max": 10},
        MetricType.SLEEP_SCORE: {"mean": 75, "std": 15, "min": 30, "max": 100},
        MetricType.CALORIES_BURNED: {"mean": 2200, "std": 400, "min": 1500, "max": 4000},
        MetricType.ACTIVE_MINUTES: {"mean": 45, "std": 20, "min": 0, "max": 180},
        MetricType.BLOOD_OXYGEN: {"mean": 97, "std": 1.5, "min": 90, "max": 100},
        MetricType.READINESS: {"mean": 70, "std": 15, "min": 20, "max": 100},
    }
    
    def __init__(self, config: AdapterConfig = None):
        super().__init__(config)
        self._seed = random.randint(1, 10000)
    
    def _generate_metric_value(self, metric_type: MetricType, day_factor: float = 1.0) -> float:
        """Generate realistic metric value based on baselines."""
        if metric_type not in self.BASELINES:
            return random.uniform(0, 100)
        
        baseline = self.BASELINES[metric_type]
        value = random.gauss(baseline["mean"] * day_factor, baseline["std"])
        return max(baseline["min"], min(baseline["max"], value))
    
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Generate mock raw data simulating API response."""
        random.seed(self._seed)
        
        metrics = []
        summaries = []
        now = datetime.now()
        
        # Generate daily summaries for the last 14 days
        for day_offset in range(14):
            day_date = now.date() - timedelta(days=day_offset)
            day_datetime = datetime.combine(day_date, datetime.min.time())
            
            # Simulate weekday vs weekend patterns
            is_weekend = day_date.weekday() >= 5
            activity_factor = 0.8 if is_weekend else 1.0
            
            # Daily summary
            steps = int(self._generate_metric_value(MetricType.STEPS, activity_factor))
            sleep_hours = round(self._generate_metric_value(MetricType.SLEEP_DURATION), 1)
            
            summary = {
                "date": day_date.isoformat(),
                "steps": steps,
                "avg_heart_rate": round(self._generate_metric_value(MetricType.HEART_RATE)),
                "hrv": round(self._generate_metric_value(MetricType.HRV)),
                "sleep_hours": sleep_hours,
                "sleep_score": int(self._generate_metric_value(MetricType.SLEEP_SCORE)),
                "calories_burned": int(self._generate_metric_value(MetricType.CALORIES_BURNED, activity_factor)),
                "active_minutes": int(self._generate_metric_value(MetricType.ACTIVE_MINUTES, activity_factor)),
                "readiness_score": int(self._generate_metric_value(MetricType.READINESS)),
            }
            summaries.append(summary)
            
            # Generate hourly heart rate samples for today and yesterday
            if day_offset < 2:
                for hour in range(24):
                    # Simulate circadian rhythm
                    hour_factor = 1.0
                    if 0 <= hour < 6:  # Sleep
                        hour_factor = 0.85
                    elif 6 <= hour < 9:  # Morning
                        hour_factor = 0.95
                    elif 12 <= hour < 14:  # Post-lunch
                        hour_factor = 1.05
                    elif 17 <= hour < 19:  # Exercise window
                        hour_factor = 1.15 if random.random() > 0.7 else 1.0
                    
                    metrics.append({
                        "id": f"hr_{day_date}_{hour}",
                        "timestamp": day_datetime.replace(hour=hour).isoformat(),
                        "type": "heart_rate",
                        "value": round(self._generate_metric_value(MetricType.HEART_RATE) * hour_factor),
                        "unit": "bpm",
                        "source": "apple_watch",
                    })
        
        # Today's real-time metrics
        today_summary = summaries[0] if summaries else {}
        
        return {
            "metrics": metrics,
            "summaries": summaries,
            "today": {
                "steps": today_summary.get("steps", 0),
                "goal_steps": 10000,
                "steps_progress": today_summary.get("steps", 0) / 10000,
                "calories_burned": today_summary.get("calories_burned", 0),
                "active_minutes": today_summary.get("active_minutes", 0),
                "current_heart_rate": round(self._generate_metric_value(MetricType.HEART_RATE)),
                "hrv": today_summary.get("hrv", 0),
                "sleep_last_night": summaries[1].get("sleep_hours", 0) if len(summaries) > 1 else 0,
                "sleep_score": summaries[1].get("sleep_score", 0) if len(summaries) > 1 else 0,
                "readiness": today_summary.get("readiness_score", 0),
            },
            "mock": True,
        }
    
    def transform(self, raw_data: Dict[str, Any]) -> List[HealthMetric]:
        """Transform mock data to canonical format."""
        metrics = []
        
        for m in raw_data.get("metrics", []):
            metric_type = MetricType(m["type"])
            
            metrics.append(HealthMetric(
                id=f"mock:{m['id']}",
                timestamp=datetime.fromisoformat(m["timestamp"]),
                metric_type=metric_type,
                value=float(m["value"]),
                unit=m["unit"],
                source_device=m.get("source", "unknown"),
                platform=self.platform,
                metadata={"raw": m}
            ))
        
        return metrics
    
    def transform_summaries(self, raw_data: Dict[str, Any]) -> List[HealthSummary]:
        """Transform daily summaries to canonical format."""
        summaries = []
        
        for s in raw_data.get("summaries", []):
            summaries.append(HealthSummary(
                date=datetime.fromisoformat(s["date"]),
                steps=s.get("steps"),
                avg_heart_rate=s.get("avg_heart_rate"),
                hrv=s.get("hrv"),
                sleep_hours=s.get("sleep_hours"),
                sleep_score=s.get("sleep_score"),
                calories_burned=s.get("calories_burned"),
                active_minutes=s.get("active_minutes"),
                readiness_score=s.get("readiness_score"),
            ))
        
        return summaries
    
    def get_today_summary(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get today's health summary for dashboard display."""
        return raw_data.get("today", {})
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": True,  # Simulates real-time data
            "batch": True,
            "webhooks": False,
            "steps": True,
            "heart_rate": True,
            "hrv": True,
            "sleep": True,
            "activity": True,
        }
