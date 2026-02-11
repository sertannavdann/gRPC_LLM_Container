"""
Bank Data Service Layer

Loads CIBC CSV data via the adapter, provides query/filter/aggregate methods
for the REST API endpoints.
"""
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List, Optional

from shared.adapters.finance.cibc import CIBCAdapter
from shared.adapters.base import AdapterConfig, AdapterCategory

logger = logging.getLogger(__name__)


class BankService:
    """Service layer for bank transaction data with caching."""

    def __init__(self, data_dir: str = "/app/dashboard_service/Bank"):
        self._data_dir = data_dir
        self._transactions: List[Dict[str, Any]] = []
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Load and cache transactions on first access."""
        if self._loaded:
            return

        adapter = CIBCAdapter(
            config=AdapterConfig(
                category=AdapterCategory.FINANCE,
                platform="cibc",
                settings={"data_dir": self._data_dir},
            )
        )
        result = await adapter.fetch(
            AdapterConfig(
                category=AdapterCategory.FINANCE,
                platform="cibc",
                settings={"data_dir": self._data_dir},
            )
        )

        if result.success:
            self._transactions = [t.to_dict() for t in result.data]
            # Enrich with spending_category from metadata
            for txn in self._transactions:
                meta = txn.get("metadata", {})
                txn["spending_category"] = meta.get("spending_category", "Other")
                txn["parent_company"] = meta.get("parent_company", "Other")
                txn["account_type"] = meta.get("account_type", "unknown")
                txn["is_debit"] = meta.get("is_debit", True)
            logger.info(f"Loaded {len(self._transactions)} bank transactions")
        else:
            logger.error(f"Failed to load bank data: {result.error}")

        self._loaded = True

    async def reload(self) -> int:
        """Force reload from CSV files."""
        self._loaded = False
        self._transactions = []
        await self._ensure_loaded()
        return len(self._transactions)

    async def get_transactions(
        self,
        category: Optional[str] = None,
        account: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        amount_min: Optional[float] = None,
        amount_max: Optional[float] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None,
        sort_dir: str = "desc",
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """Query transactions with filters, sorting, and pagination."""
        await self._ensure_loaded()

        filtered = self._transactions

        if category:
            filtered = [t for t in filtered if t["spending_category"].lower() == category.lower()]

        if account:
            filtered = [
                t for t in filtered
                if account.lower() in t.get("account_type", "").lower()
                or account.lower() in t.get("account_id", "").lower()
            ]

        if date_from:
            filtered = [t for t in filtered if t["timestamp"] >= date_from]

        if date_to:
            # Include the entire end date
            date_to_end = date_to + "T23:59:59" if "T" not in date_to else date_to
            filtered = [t for t in filtered if t["timestamp"] <= date_to_end]

        if amount_min is not None:
            filtered = [t for t in filtered if t["amount"] >= amount_min]

        if amount_max is not None:
            filtered = [t for t in filtered if t["amount"] <= amount_max]

        if search:
            search_lower = search.lower()
            filtered = [
                t for t in filtered
                if search_lower in t.get("merchant", "").lower()
                or search_lower in t.get("description", "").lower()
                or search_lower in t.get("spending_category", "").lower()
            ]

        # Sort
        if sort:
            sort_key_map = {
                "timestamp": lambda t: t.get("timestamp", ""),
                "merchant": lambda t: t.get("merchant", "").lower(),
                "description": lambda t: t.get("description", "").lower(),
                "amount": lambda t: t.get("amount", 0),
                "category": lambda t: t.get("spending_category", "").lower(),
            }
            key_fn = sort_key_map.get(sort, sort_key_map["timestamp"])
            filtered = sorted(filtered, key=key_fn, reverse=(sort_dir == "desc"))

        total = len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        page_data = filtered[start:end]

        return {
            "transactions": page_data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
        }

    async def get_summary(
        self,
        group_by: str = "category",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category: Optional[str] = None,
        account: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate transactions by category, company, month, or year."""
        await self._ensure_loaded()

        filtered = self._transactions

        if category:
            filtered = [t for t in filtered if t.get("spending_category", "").lower() == category.lower()]

        if account:
            filtered = [
                t for t in filtered
                if account.lower() in t.get("account_type", "").lower()
                or account.lower() in t.get("account_id", "").lower()
            ]

        if date_from:
            filtered = [t for t in filtered if t["timestamp"] >= date_from]
        if date_to:
            date_to_end = date_to + "T23:59:59" if "T" not in date_to else date_to
            filtered = [t for t in filtered if t["timestamp"] <= date_to_end]

        if search:
            search_lower = search.lower()
            filtered = [
                t for t in filtered
                if search_lower in t.get("merchant", "").lower()
                or search_lower in t.get("description", "").lower()
                or search_lower in t.get("spending_category", "").lower()
            ]

        groups: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"total": 0.0, "count": 0, "debits": 0.0, "credits": 0.0}
        )

        for txn in filtered:
            if group_by == "category":
                key = txn.get("spending_category", "Other")
            elif group_by == "company":
                key = txn.get("merchant", "Other")
            elif group_by == "month":
                key = txn["timestamp"][:7]  # YYYY-MM
            elif group_by == "year":
                key = txn["timestamp"][:4]  # YYYY
            else:
                key = txn.get("spending_category", "Other")

            amount = txn["amount"]
            groups[key]["count"] += 1

            if txn.get("is_debit", True):
                groups[key]["debits"] += amount
                groups[key]["total"] += amount
            else:
                groups[key]["credits"] += amount

        # Sort by total descending
        sorted_groups = sorted(groups.items(), key=lambda x: x[1]["total"], reverse=True)

        return {
            "group_by": group_by,
            "groups": [
                {
                    "name": name,
                    "total": round(data["total"], 2),
                    "debits": round(data["debits"], 2),
                    "credits": round(data["credits"], 2),
                    "count": data["count"],
                }
                for name, data in sorted_groups
            ],
            "total_transactions": len(filtered),
        }

    async def get_categories(self) -> Dict[str, Any]:
        """List all spending categories with totals."""
        await self._ensure_loaded()

        cats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"total": 0.0, "count": 0}
        )

        for txn in self._transactions:
            cat = txn.get("spending_category", "Other")
            if txn.get("is_debit", True):
                cats[cat]["total"] += txn["amount"]
            cats[cat]["count"] += 1

        sorted_cats = sorted(cats.items(), key=lambda x: x[1]["total"], reverse=True)

        return {
            "categories": [
                {"name": name, "total": round(data["total"], 2), "count": data["count"]}
                for name, data in sorted_cats
            ],
        }

    async def search(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """Full text search across descriptions and merchants."""
        await self._ensure_loaded()

        query_lower = query.lower()
        matches = [
            t for t in self._transactions
            if query_lower in t.get("merchant", "").lower()
            or query_lower in t.get("description", "").lower()
            or query_lower in t.get("spending_category", "").lower()
            or query_lower in t.get("parent_company", "").lower()
        ]

        return {
            "query": query,
            "results": matches[:limit],
            "total": len(matches),
        }
