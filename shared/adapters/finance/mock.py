"""
Mock Finance Adapter - Development/Testing

Generates realistic mock financial data for UI development
without requiring real bank connections.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List
import random
import uuid

from ..base import BaseAdapter, AdapterConfig
from ..registry import register_adapter
from ...schemas.canonical import (
    FinancialTransaction, 
    FinancialAccount,
    TransactionCategory,
    AccountType,
)


# Realistic merchant data for mock transactions
MOCK_MERCHANTS = {
    TransactionCategory.EXPENSE: [
        ("Starbucks", 5.75, 12.50),
        ("Amazon.ca", 15.00, 150.00),
        ("Uber Eats", 18.00, 45.00),
        ("Costco", 80.00, 250.00),
        ("Netflix", 16.99, 16.99),
        ("Spotify", 11.99, 11.99),
        ("Shell Gas", 45.00, 95.00),
        ("Loblaws", 50.00, 180.00),
        ("Tim Hortons", 3.50, 15.00),
        ("Apple.com", 1.29, 1599.00),
    ],
    TransactionCategory.INCOME: [
        ("Payroll - ACME Corp", 2500.00, 5000.00),
        ("E-Transfer Received", 50.00, 500.00),
        ("Interest Payment", 0.50, 25.00),
        ("Dividend - VGRO", 15.00, 150.00),
    ],
    TransactionCategory.TRANSFER: [
        ("Transfer to Savings", 100.00, 1000.00),
        ("Transfer from Checking", 100.00, 500.00),
        ("RRSP Contribution", 250.00, 1000.00),
    ],
}


@register_adapter(
    category="finance",
    platform="mock",
    display_name="Mock Bank",
    description="Development mock adapter with realistic financial data",
    icon="🏦",
    requires_auth=False,
)
class MockFinanceAdapter(BaseAdapter[FinancialTransaction]):
    """
    Mock finance adapter for development and testing.
    Generates realistic transaction and account data.
    """
    
    category = "finance"
    platform = "mock"
    
    def __init__(self, config: AdapterConfig = None):
        super().__init__(config)
        self._seed = random.randint(1, 10000)
    
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Generate mock raw data simulating API response."""
        random.seed(self._seed)
        
        # Generate transactions for the last 30 days
        transactions = []
        now = datetime.now()
        
        for i in range(50):
            days_ago = random.randint(0, 30)
            category = random.choice([
                TransactionCategory.EXPENSE,
                TransactionCategory.EXPENSE,
                TransactionCategory.EXPENSE,  # More expenses than income
                TransactionCategory.INCOME,
                TransactionCategory.TRANSFER,
            ])
            
            merchants = MOCK_MERCHANTS[category]
            merchant, min_amount, max_amount = random.choice(merchants)
            amount = round(random.uniform(min_amount, max_amount), 2)
            
            transactions.append({
                "id": f"mock_txn_{uuid.uuid4().hex[:8]}",
                "date": (now - timedelta(days=days_ago)).isoformat(),
                "amount": amount if category == TransactionCategory.INCOME else -amount,
                "merchant": merchant,
                "category": category.value,
                "account_id": "mock_checking_001",
                "pending": days_ago == 0 and random.random() > 0.7,
            })
        
        # Sort by date descending
        transactions.sort(key=lambda x: x["date"], reverse=True)
        
        # Generate accounts
        accounts = [
            {
                "id": "mock_checking_001",
                "name": "Primary Checking",
                "type": "checking",
                "balance": round(random.uniform(1500, 8000), 2),
                "currency": "CAD",
                "institution": "Mock Bank",
                "mask": "1234",
            },
            {
                "id": "mock_savings_001",
                "name": "High Interest Savings",
                "type": "savings",
                "balance": round(random.uniform(5000, 25000), 2),
                "currency": "CAD",
                "institution": "Mock Bank",
                "mask": "5678",
            },
            {
                "id": "mock_credit_001",
                "name": "Rewards Credit Card",
                "type": "credit",
                "balance": round(random.uniform(-2000, 0), 2),
                "currency": "CAD",
                "institution": "Mock Bank",
                "mask": "9012",
                "credit_limit": 5000.00,
            },
        ]
        
        return {
            "transactions": transactions,
            "accounts": accounts,
            "mock": True,
        }
    
    def transform(self, raw_data: Dict[str, Any]) -> List[FinancialTransaction]:
        """Transform mock data to canonical format."""
        transactions = []
        
        for txn in raw_data.get("transactions", []):
            amount = Decimal(str(abs(txn["amount"])))
            category = TransactionCategory(txn["category"])
            
            transactions.append(FinancialTransaction(
                id=f"mock:{txn['id']}",
                timestamp=datetime.fromisoformat(txn["date"]),
                amount=amount,
                currency="CAD",
                category=category,
                merchant=txn["merchant"],
                account_id=txn["account_id"],
                pending=txn.get("pending", False),
                platform=self.platform,
                metadata={
                    "raw": txn,
                    "is_debit": txn["amount"] < 0,
                }
            ))
        
        return transactions
    
    def transform_accounts(self, raw_data: Dict[str, Any]) -> List[FinancialAccount]:
        """Transform account data to canonical format."""
        accounts = []
        
        for acc in raw_data.get("accounts", []):
            account_type = AccountType(acc["type"])
            
            accounts.append(FinancialAccount(
                id=f"mock:{acc['id']}",
                name=acc["name"],
                account_type=account_type,
                balance=Decimal(str(acc["balance"])),
                currency=acc["currency"],
                institution=acc["institution"],
                mask=acc.get("mask"),
                credit_limit=Decimal(str(acc["credit_limit"])) if acc.get("credit_limit") else None,
                platform=self.platform,
            ))
        
        return accounts
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": True,
            "webhooks": False,
            "accounts": True,
            "transactions": True,
            "investments": False,
        }
