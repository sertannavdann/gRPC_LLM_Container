"""
Relevance Engine - Task-Oriented Data Classification

Classifies aggregated data by relevance/urgency for:
- Prioritizing what to show in the dashboard
- Deciding storage tier (Redis/PostgreSQL/S3)
- Context injection into LLM prompts
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
from dataclasses import dataclass

from shared.schemas.canonical import UnifiedContext


@dataclass
class RelevanceRule:
    """A rule for classifying data relevance."""
    name: str
    category: str
    condition: str  # Description of the condition
    relevance: str  # HIGH, MEDIUM, LOW
    priority: int = 0  # Higher = more important


class RelevanceEngine:
    """
    Classifies data into HIGH/MEDIUM/LOW relevance buckets.
    
    HIGH: Actionable within 2 hours (show prominently, cache in Redis)
    MEDIUM: Contextually relevant within 24h-7d (show, store in PostgreSQL)
    LOW: Historical/archival (hide by default, archive to S3)
    """
    
    # Time thresholds
    HIGH_THRESHOLD_HOURS = 2
    MEDIUM_THRESHOLD_HOURS = 24
    
    def classify(self, context: UnifiedContext) -> Dict[str, List[Dict[str, Any]]]:
        """
        Classify all data in context by relevance.
        
        Returns dict with 'high', 'medium', 'low' lists.
        """
        result = {
            "high": [],
            "medium": [],
            "low": [],
        }
        
        now = datetime.now()
        
        # Classify calendar events
        self._classify_calendar(context.calendar, result, now)
        
        # Classify finance data
        self._classify_finance(context.finance, result, now)
        
        # Classify health metrics
        self._classify_health(context.health, result, now)
        
        # Classify navigation
        self._classify_navigation(context.navigation, result, now)
        
        # Sort each bucket by priority
        for bucket in result.values():
            bucket.sort(key=lambda x: x.get("priority", 0), reverse=True)
        
        return result
    
    def _classify_calendar(
        self,
        calendar_data: Dict[str, Any],
        result: Dict[str, List],
        now: datetime,
    ) -> None:
        """Classify calendar events by urgency."""
        events = calendar_data.get("events", [])
        
        for event in events:
            start_str = event.get("start_time", "")
            if not start_str:
                continue
            
            try:
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_time.tzinfo:
                    start_time = start_time.replace(tzinfo=None)
            except ValueError:
                continue
            
            time_until = start_time - now
            
            item = {
                "type": "calendar",
                "subtype": "event",
                "data": event,
                "title": event.get("title", "Event"),
                "timestamp": start_str,
            }
            
            if time_until < timedelta(0):
                # Past event
                item["priority"] = 0
                result["low"].append(item)
            
            elif time_until < timedelta(hours=self.HIGH_THRESHOLD_HOURS):
                # Imminent event - HIGH
                item["priority"] = 100 - int(time_until.total_seconds() / 60)  # Higher priority = sooner
                item["alert"] = f"In {int(time_until.total_seconds() / 60)} minutes"
                result["high"].append(item)
            
            elif time_until < timedelta(hours=self.MEDIUM_THRESHOLD_HOURS):
                # Today's events - MEDIUM
                item["priority"] = 50
                result["medium"].append(item)
            
            else:
                # Future events - LOW
                item["priority"] = 10
                result["low"].append(item)
    
    def _classify_finance(
        self,
        finance_data: Dict[str, Any],
        result: Dict[str, List],
        now: datetime,
    ) -> None:
        """Classify financial data by relevance."""
        transactions = finance_data.get("transactions", [])
        
        # Budget alert (if net cashflow is negative)
        net_cashflow = finance_data.get("net_cashflow", 0)
        if net_cashflow < 0:
            result["high"].append({
                "type": "finance",
                "subtype": "budget_alert",
                "title": "Budget Alert",
                "alert": f"Spending exceeds income by ${abs(net_cashflow):.2f}",
                "priority": 80,
                "data": {
                    "net_cashflow": net_cashflow,
                    "expenses": finance_data.get("total_expenses_period", 0),
                    "income": finance_data.get("total_income_period", 0),
                },
            })
        
        # Classify transactions
        for txn in transactions:
            timestamp_str = txn.get("timestamp", "")
            if not timestamp_str:
                continue
            
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=None)
            except ValueError:
                continue
            
            age = now - timestamp
            
            item = {
                "type": "finance",
                "subtype": "transaction",
                "data": txn,
                "title": txn.get("merchant", "Transaction"),
                "timestamp": timestamp_str,
            }
            
            # Pending transactions are HIGH relevance
            if txn.get("pending"):
                item["priority"] = 70
                item["alert"] = "Pending transaction"
                result["high"].append(item)
            
            # Recent (today) transactions are MEDIUM
            elif age < timedelta(days=1):
                item["priority"] = 40
                result["medium"].append(item)
            
            # Older transactions are LOW
            else:
                item["priority"] = 5
                result["low"].append(item)
    
    def _classify_health(
        self,
        health_data: Dict[str, Any],
        result: Dict[str, List],
        now: datetime,
    ) -> None:
        """Classify health metrics by relevance."""
        today = health_data.get("today", {})
        
        # Check for health anomalies
        hrv = today.get("hrv")
        if hrv and hrv < 30:  # Low HRV threshold
            result["high"].append({
                "type": "health",
                "subtype": "hrv_alert",
                "title": "Low HRV Detected",
                "alert": f"HRV is {hrv}ms (below normal)",
                "priority": 75,
                "data": {"hrv": hrv},
            })
        
        # Sleep quality alert
        sleep_score = today.get("sleep_score")
        if sleep_score and sleep_score < 60:
            result["medium"].append({
                "type": "health",
                "subtype": "sleep_alert",
                "title": "Poor Sleep Quality",
                "alert": f"Sleep score was {sleep_score}",
                "priority": 45,
                "data": {"sleep_score": sleep_score},
            })
        
        # Readiness score
        readiness = today.get("readiness")
        if readiness:
            relevance = "high" if readiness < 50 else "medium" if readiness < 70 else "low"
            result[relevance].append({
                "type": "health",
                "subtype": "readiness",
                "title": "Readiness Score",
                "data": {"readiness": readiness},
                "priority": 60 if relevance == "high" else 30,
            })
        
        # Steps progress
        steps_progress = today.get("steps_progress", 0)
        if steps_progress > 0:
            result["medium"].append({
                "type": "health",
                "subtype": "steps",
                "title": f"Steps: {int(steps_progress * 100)}% of goal",
                "data": {
                    "steps": today.get("steps", 0),
                    "goal": today.get("goal_steps", 10000),
                    "progress": steps_progress,
                },
                "priority": 35,
            })
    
    def _classify_navigation(
        self,
        navigation_data: Dict[str, Any],
        result: Dict[str, List],
        now: datetime,
    ) -> None:
        """Classify navigation data by relevance."""
        routes = navigation_data.get("routes", [])
        
        for route in routes:
            traffic = route.get("traffic_level", "unknown")
            duration = route.get("duration_minutes", 0)
            
            item = {
                "type": "navigation",
                "subtype": "route",
                "data": route,
                "title": f"Route to {route.get('destination', {}).get('address', 'destination')}",
            }
            
            # Heavy traffic or long delays are HIGH
            if traffic == "heavy":
                item["priority"] = 65
                item["alert"] = f"Heavy traffic - {duration} min expected"
                result["high"].append(item)
            
            # Active routes are MEDIUM
            elif traffic in ["light", "moderate"]:
                item["priority"] = 25
                result["medium"].append(item)
            
            else:
                item["priority"] = 5
                result["low"].append(item)
    
    def get_high_priority_alerts(self, context: UnifiedContext) -> List[Dict[str, Any]]:
        """Get only HIGH relevance items with alerts."""
        classification = self.classify(context)
        return [
            item for item in classification["high"]
            if item.get("alert")
        ]
    
    def get_context_summary_for_llm(self, context: UnifiedContext) -> str:
        """
        Generate a natural language summary for LLM context injection.
        
        Used by ClawdBot to provide personalized responses.
        """
        classification = self.classify(context)
        
        lines = ["Current User Context:"]
        
        # High priority alerts
        high_items = classification["high"]
        if high_items:
            lines.append("\n**Urgent:**")
            for item in high_items[:5]:  # Top 5
                if item.get("alert"):
                    lines.append(f"- {item['alert']}")
                else:
                    lines.append(f"- {item['title']}")
        
        # Calendar summary
        calendar = context.calendar
        if calendar.get("next_3"):
            lines.append("\n**Upcoming Events:**")
            for event in calendar["next_3"]:
                lines.append(f"- {event.get('title')} at {event.get('start_time', '')[:16]}")
        
        # Health summary
        health = context.health
        if health.get("today"):
            today = health["today"]
            lines.append("\n**Health Today:**")
            if today.get("steps"):
                lines.append(f"- Steps: {today['steps']:,} / {today.get('goal_steps', 10000):,}")
            if today.get("sleep_hours"):
                lines.append(f"- Sleep: {today['sleep_hours']}h (score: {today.get('sleep_score', 'N/A')})")
        
        # Finance summary
        finance = context.finance
        if finance.get("net_cashflow") is not None:
            status = "under budget" if finance["net_cashflow"] >= 0 else "over budget"
            lines.append(f"\n**Finance:** Currently {status}")
        
        return "\n".join(lines)
