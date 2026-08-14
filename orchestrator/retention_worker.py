"""
Tiered per-org usage retention pruning (REQ-017).

RESEARCH Assumption A1: REQ-017's literal requirement ("Prometheus retention
flags per org") is implemented here as app-level org-scoped SQLite retention
against `shared/billing/usage_store.py::usage_records`, not as native
per-tenant Prometheus retention. The deployed observability stack is a
single-instance Prometheus/Tempo pair; true per-tenant retention there would
require Mimir/Cortex plus `X-Scope-OrgID` header propagation across the
scrape and query paths — that is Phase 9 territory (multi-tenant enterprise
hardening), not something this phase's single-instance stack can express.
The billing usage_records table is the closest first-class per-org,
per-record store this phase has, so tiered retention is enforced there.

TIER_RETENTION_DAYS mirrors shared/billing/quota_manager.py::TIER_QUOTAS'
`-1 = unlimited` sentinel convention: enterprise retention is unbounded and
is skipped entirely by prune_expired_usage().
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

TIER_RETENTION_DAYS = {
    "free": 7,
    "team": 90,
    "enterprise": -1,  # -1 = unlimited, mirrors quota_manager.TIER_QUOTAS convention
}


def prune_expired_usage(usage_store, api_key_store=None) -> dict:
    """
    Prune usage records older than each org's tier retention window.

    For every org_id present in usage_store, resolves the org's plan tier
    (via api_key_store.get_organization(org_id).plan, defaulting to "free"
    when the store or org record is missing), looks up the retention window
    for that tier, and deletes records older than the cutoff. Enterprise
    (-1 retention) is skipped entirely — its usage records are never pruned.

    Each org is processed inside its own try/except so a single org's
    failure (e.g. a lookup error) can never abort the pass for the rest.

    Args:
        usage_store: UsageStore instance (delete_before / list_org_ids)
        api_key_store: Optional APIKeyStore for plan resolution

    Returns:
        {"pruned": {org_id: deleted_count, ...}, "errors": [{"org_id": ..., "error": ...}]}
    """
    result: dict = {"pruned": {}, "errors": []}

    try:
        org_ids = usage_store.list_org_ids()
    except Exception as e:
        logger.warning(f"Retention: failed to list org ids: {e}")
        result["errors"].append({"org_id": None, "error": str(e)})
        return result

    now = datetime.now(timezone.utc)

    for org_id in org_ids:
        try:
            plan = "free"
            if api_key_store is not None:
                org = api_key_store.get_organization(org_id)
                if org is not None:
                    plan = org.plan

            retention_days = TIER_RETENTION_DAYS.get(plan, TIER_RETENTION_DAYS["free"])
            if retention_days < 0:
                # Enterprise (or any negative-retention tier) is unlimited.
                continue

            cutoff = (now - timedelta(days=retention_days)).isoformat()
            deleted = usage_store.delete_before(org_id, cutoff)
            result["pruned"][org_id] = deleted
            logger.info(
                f"Retention: pruned {deleted} usage records for org={org_id} "
                f"plan={plan} retention_days={retention_days}"
            )
        except Exception as e:
            logger.warning(f"Retention: failed to prune org={org_id}: {e}")
            result["errors"].append({"org_id": org_id, "error": str(e)})

    return result
