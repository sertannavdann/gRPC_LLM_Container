"""
CIBC CSV Finance Adapter

Reads CIBC bank transaction CSV exports (credit card and chequing accounts)
and transforms them into canonical FinancialTransaction objects.

CSV format: Date, Description, Amount (debit), Payment (credit), Card
"""
import csv
import hashlib
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

from ..base import BaseAdapter, AdapterConfig
from ..registry import register_adapter
from ...schemas.canonical import FinancialTransaction, TransactionCategory
from .categorizer import categorize, get_transaction_category


DEFAULT_DATA_DIR = "/app/dashboard_service/Bank"


@register_adapter(
    category="finance",
    platform="cibc",
    display_name="CIBC Bank",
    description="CIBC CSV transaction import (credit card and chequing)",
    icon="🏦",
    requires_auth=False,
)
class CIBCAdapter(BaseAdapter[FinancialTransaction]):
    """
    CIBC CSV adapter. Reads exported CSV files from a configurable directory.
    Supports both credit card and chequing account formats.
    """

    category = "finance"
    platform = "cibc"

    def __init__(self, config: AdapterConfig = None):
        super().__init__(config)
        self._data_dir = (
            config.settings.get("data_dir", DEFAULT_DATA_DIR)
            if config and config.settings
            else DEFAULT_DATA_DIR
        )

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Read all CSV files from the data directory."""
        data_dir = (
            config.settings.get("data_dir", self._data_dir)
            if config and config.settings
            else self._data_dir
        )

        transactions = []
        csv_files = []

        if not os.path.isdir(data_dir):
            return {"transactions": [], "source_dir": data_dir, "files": []}

        for filename in sorted(os.listdir(data_dir)):
            if not filename.endswith(".csv"):
                continue

            filepath = os.path.join(data_dir, filename)
            csv_files.append(filename)

            # Determine account type from filename
            account_type = "chequing" if "chq" in filename.lower() else "credit"

            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["_source_file"] = filename
                    row["_account_type"] = account_type
                    transactions.append(row)

        return {
            "transactions": transactions,
            "source_dir": data_dir,
            "files": csv_files,
        }

    def transform(self, raw_data: Dict[str, Any]) -> List[FinancialTransaction]:
        """Transform CSV rows into canonical FinancialTransaction objects."""
        seen_ids: set = set()
        results = []

        for row in raw_data.get("transactions", []):
            txn = self._parse_row(row)
            if txn and txn.id not in seen_ids:
                seen_ids.add(txn.id)
                results.append(txn)

        # Sort newest first
        results.sort(key=lambda t: t.timestamp, reverse=True)
        return results

    def _parse_row(self, row: Dict[str, str]) -> FinancialTransaction | None:
        """Parse a single CSV row into a FinancialTransaction."""
        try:
            date_str = (row.get("Date") or "").strip()
            description = (row.get("Description") or "").strip()
            amount_str = (row.get("Amount") or "").strip()
            payment_str = (row.get("Payment") or "").strip()
            card = (row.get("Card") or "").strip()
            account_type = row.get("_account_type", "credit")
            source_file = row.get("_source_file", "")

            if not date_str or not description:
                return None

            # Parse date
            timestamp = datetime.strptime(date_str, "%Y-%m-%d")

            # Determine amount: Amount column = debit, Payment column = credit
            is_debit = bool(amount_str)
            if amount_str:
                amount = Decimal(amount_str.replace(",", ""))
            elif payment_str:
                amount = Decimal(payment_str.replace(",", ""))
            else:
                return None

            # Categorize
            company, parent_company, spending_category = categorize(description)
            txn_category = get_transaction_category(spending_category, is_debit)

            # Generate stable ID from row content
            id_source = f"{date_str}:{description}:{amount_str}:{payment_str}:{card}"
            txn_id = f"cibc:{hashlib.md5(id_source.encode()).hexdigest()[:12]}"

            # Account ID from card mask or account type
            account_id = f"cibc_{account_type}"
            if card:
                last4 = card.replace("*", "")[-4:] if card else ""
                account_id = f"cibc_{account_type}_{last4}"

            return FinancialTransaction(
                id=txn_id,
                timestamp=timestamp,
                amount=abs(amount),
                currency="CAD",
                category=txn_category,
                merchant=company,
                account_id=account_id,
                description=description,
                pending=False,
                platform=self.platform,
                metadata={
                    "raw_description": description,
                    "parent_company": parent_company,
                    "spending_category": spending_category,
                    "is_debit": is_debit,
                    "account_type": account_type,
                    "source_file": source_file,
                    "card_mask": card,
                },
            )
        except (ValueError, KeyError):
            return None

    @classmethod
    def normalize_category_for_tools(cls, raw_category_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize finance data for tool consumption."""
        return {
            "transactions": raw_category_data.get("transactions", []),
            "total_expenses_period": raw_category_data.get("total_expenses_period", 0),
            "total_income_period": raw_category_data.get("total_income_period", 0),
            "net_cashflow": raw_category_data.get("net_cashflow", 0),
        }

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": True,
            "webhooks": False,
            "accounts": False,
            "transactions": True,
            "investments": False,
        }
