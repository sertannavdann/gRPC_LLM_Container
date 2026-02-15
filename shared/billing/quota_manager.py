"""
Quota Manager — tier-based usage quota enforcement.

Checks current-period usage against plan limits and provides
pre-flight checks for expensive operations.
"""
import logging
from typing import Optional

from pydantic import BaseModel

from .usage_store import UsageStore

logger = logging.getLogger(__name__)

TIER_QUOTAS = {
    "free": 100.0,
    "team": 5000.0,
    "enterprise": -1.0,
}


class QuotaResult(BaseModel):
    """Result of a quota check."""
    allowed: bool
    current_usage: float
    limit: float
    remaining: float
    period: str
    org_id: str
    plan: str


class QuotaManager:
    """Enforces per-org usage quotas based on plan tier."""

    def __init__(
        self,
        usage_store: UsageStore,
        api_key_store=None,
    ):
        self._usage_store = usage_store
        self._api_key_store = api_key_store

    def _resolve_plan(self, org_id: str, plan: Optional[str] = None) -> str:
        """Resolve the plan tier for an org."""
        if plan:
            return plan
        if self._api_key_store:
            org = self._api_key_store.get_organization(org_id)
            if org:
                return org.plan
        return "free"

    def check_quota(
        self,
        org_id: str,
        plan: Optional[str] = None,
    ) -> QuotaResult:
        """
        Check whether an org is within its usage quota.

        Returns QuotaResult with allowed/denied status and usage details.
        """
        resolved_plan = self._resolve_plan(org_id, plan)
        limit = TIER_QUOTAS.get(resolved_plan, TIER_QUOTAS["free"])
        current_usage = self._usage_store.get_period_total(org_id)
        period = self._usage_store.get_usage_summary(org_id)["period"]

        if limit < 0:
            return QuotaResult(
                allowed=True,
                current_usage=current_usage,
                limit=-1.0,
                remaining=float("inf"),
                period=period,
                org_id=org_id,
                plan=resolved_plan,
            )

        remaining = max(0.0, limit - current_usage)
        allowed = current_usage < limit

        return QuotaResult(
            allowed=allowed,
            current_usage=current_usage,
            limit=limit,
            remaining=remaining,
            period=period,
            org_id=org_id,
            plan=resolved_plan,
        )

    def get_remaining(
        self,
        org_id: str,
        plan: Optional[str] = None,
    ) -> float:
        """Get remaining run-units for current period. -1.0 means unlimited."""
        result = self.check_quota(org_id, plan)
        if result.limit < 0:
            return -1.0
        return result.remaining

    def would_exceed(
        self,
        org_id: str,
        estimated_units: float,
        plan: Optional[str] = None,
    ) -> bool:
        """Pre-flight check: would adding estimated_units exceed quota?"""
        result = self.check_quota(org_id, plan)
        if result.limit < 0:
            return False
        return (result.current_usage + estimated_units) > result.limit
