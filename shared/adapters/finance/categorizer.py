"""
Transaction Categorizer - CIBC Description Pattern Matching

Maps raw bank transaction descriptions to structured company/category data
using regex patterns derived from historical transaction analysis.
"""
import re
from typing import Tuple, Optional

from ...schemas.canonical import TransactionCategory


# (regex_pattern, company_name, parent_company, spending_category)
COMPANY_MAPPINGS = [
    # Rideshare & Delivery
    (r'UBER.*EATS|UBEREATS', 'Uber Eats', 'Uber', 'Food Delivery'),
    (r'UBER.*TRIP|UBERTRIP', 'Uber Trip', 'Uber', 'Rideshare'),
    (r'LYFT', 'Lyft', 'Lyft', 'Rideshare'),

    # Amazon
    (r'AMZN\s*Mktp|Amazon\.ca', 'Amazon Marketplace', 'Amazon', 'Shopping'),
    (r'AMAZON|AMZN', 'Amazon', 'Amazon', 'Shopping'),

    # Shopping
    (r'ADIDAS', 'Adidas', 'Adidas', 'Shopping'),
    (r'IKEA', 'IKEA', 'IKEA', 'Shopping'),
    (r'COACH \d+', 'Coach', 'Coach', 'Shopping'),
    (r'KLARNA', 'Klarna', 'Klarna', 'Shopping'),
    (r'ZARA', 'Zara', 'Zara', 'Shopping'),

    # Software & Subscriptions
    (r'ABLETON', 'Ableton', 'Ableton', 'Software'),
    (r'GITHUB', 'GitHub', 'GitHub', 'Software'),
    (r'ANTHROPIC|CLAUDE\.AI', 'Anthropic', 'Anthropic', 'Software'),
    (r'PERPLEXITY', 'Perplexity', 'Perplexity', 'Software'),
    (r'APPLE\.COM/BILL', 'Apple', 'Apple', 'Software'),

    # Telecom
    (r'FREEDOM MOBILE', 'Freedom Mobile', 'Freedom Mobile', 'Telecom'),
    (r'BELL CANADA', 'Bell Canada', 'Bell Canada', 'Telecom'),

    # Utilities
    (r'WYSE METER', 'Wyse Meter Solutions', 'Wyse Meter Solutions', 'Utilities'),
    (r'HYDRO-OTTAWA|HYDRO OTTAWA', 'Hydro Ottawa', 'Hydro Ottawa', 'Utilities'),

    # Gas Stations
    (r'ULTRAMAR', 'Ultramar', 'Ultramar', 'Gas'),
    (r'PETRO-CANADA|PETRO CANADA', 'Petro-Canada', 'Petro-Canada', 'Gas'),
    (r'SHELL', 'Shell', 'Shell', 'Gas'),
    (r'ONROUTE', 'ONroute', 'ONroute', 'Gas'),

    # Coffee
    (r'TIM HORTONS', 'Tim Hortons', 'Tim Hortons', 'Coffee'),
    (r'STARBUCKS', 'Starbucks', 'Starbucks', 'Coffee'),
    (r'HAPPY GOAT', 'Happy Goat Coffee', 'Happy Goat Coffee', 'Coffee'),
    (r'BALZAC', "Balzac's Coffee", "Balzac's Coffee", 'Coffee'),
    (r'BRIDGEHEAD', 'Bridgehead Coffee', 'Bridgehead Coffee', 'Coffee'),
    (r'LITTLE VICTORIES', 'Little Victories Coffee', 'Little Victories Coffee', 'Coffee'),

    # Groceries
    (r'T&T SUPERMARKET', 'T&T Supermarket', 'T&T Supermarket', 'Groceries'),
    (r'METRO \d+', 'Metro', 'Metro', 'Groceries'),
    (r'FARM BOY', 'Farm Boy', 'Farm Boy', 'Groceries'),
    (r'RCSS', 'Real Canadian Superstore', 'Loblaw', 'Groceries'),
    (r'LOBLAW', 'Loblaws', 'Loblaw', 'Groceries'),
    (r'FOODLAND', 'Foodland', 'Sobeys', 'Groceries'),
    (r"MASSINE'S|MASSINES", "Massine's YIG", 'Sobeys', 'Groceries'),

    # Convenience
    (r"MACS CONV", "Mac's", 'Couche-Tard', 'Convenience'),
    (r'COUCHE-TARD', 'Couche-Tard', 'Couche-Tard', 'Convenience'),
    (r'7 ELEVEN|7-ELEVEN', '7-Eleven', '7-Eleven', 'Convenience'),

    # Transit
    (r'VIA RAIL', 'VIA Rail', 'VIA Rail', 'Transit'),
    (r'PRESTO', 'Presto', 'Presto', 'Transit'),
    (r'POPARIDE', 'Poparide', 'Poparide', 'Transit'),

    # Travel & Accommodation
    (r'AIRBNB', 'Airbnb', 'Airbnb', 'Travel'),
    (r'HERTZ', 'Hertz', 'Hertz', 'Travel'),

    # Entertainment
    (r'CINEPLEX', 'Cineplex', 'Cineplex', 'Entertainment'),
    (r'IGLOOFEST', 'Igloofest', 'Igloofest', 'Entertainment'),
    (r'ESCAPE MANOR', 'Escape Manor', 'Escape Manor', 'Entertainment'),
    (r'TCKTWEB|TICKETWEB|LINEUPINFO', 'Ticketweb', 'Ticketweb', 'Entertainment'),

    # Bars
    (r"LIEUTENANT.?S PUMP", "Lieutenant's Pump", "Lieutenant's Pump", 'Bar'),
    (r"MACLAREN.?S", "MacLaren's", "MacLaren's", 'Bar'),
    (r'CHELSEA PUB', 'Chelsea Pub', 'Chelsea Pub', 'Bar'),
    (r'RABBIT HOLE', 'Rabbit Hole', 'Rabbit Hole', 'Bar'),
    (r'DROM TABERNA', 'Drom Taberna', 'Drom Taberna', 'Bar'),

    # Restaurants
    (r'BOBINO BAGEL', 'Bobino Bagel', 'Bobino Bagel', 'Restaurant'),
    (r'TOMO RESTAURANT', 'Tomo Restaurant', 'Tomo Restaurant', 'Restaurant'),
    (r'THALI.*COCONUT|COCONUT LAGOON', 'Thali by Coconut Lagoon', 'Coconut Lagoon', 'Restaurant'),
    (r'PELICAN GRILL', 'Pelican Grill', 'Pelican Grill', 'Restaurant'),
    (r'ARAMARK', 'Aramark', 'Aramark', 'Restaurant'),

    # Education
    (r'GEORGE BROWN', 'George Brown College', 'George Brown College', 'Education'),

    # Health
    (r'REXALL', 'Rexall', 'Rexall', 'Health'),

    # Parking
    (r'PAYBYPHONE', 'PayByPhone', 'PayByPhone', 'Parking'),
    (r'TORONTO PARKING', 'Toronto Parking Authority', 'Toronto Parking Authority', 'Parking'),

    # Banking & Fees (Credit Card)
    (r'PAYMENT THANK YOU|PAIEMENT MERCI', 'Card Payment', 'CIBC', 'Banking'),
    (r'CASHBACK|REMISE EN ARGENT', 'Cashback Reward', 'CIBC', 'Banking'),
    (r'CASH ADVANCE|AVANCE DE FO', 'Cash Advance', 'CIBC', 'Banking'),
    (r'INSTALLMENT PLAN', 'Installment Plan', 'CIBC', 'Banking'),
    (r'OVERLIMIT FEE', 'Overlimit Fee', 'CIBC', 'Banking'),

    # Banking & Fees (Chequing)
    (r'E-TRANSFER', 'E-Transfer', 'Interac', 'Transfer'),
    (r'INTERNET TRANSFER', 'Internet Transfer', 'CIBC', 'Transfer'),
    (r'OVERDRAFT FEE', 'Overdraft Fee', 'CIBC', 'Banking'),
    (r'SERVICE CHARGE|MONTHLY FEE', 'Service Charge', 'CIBC', 'Banking'),
    (r'NETWORK TRANSACTION FEE', 'ATM Fee', 'CIBC', 'Banking'),

    # Rent & Housing
    (r'BUILDING_STACK|BUILDINGSTACK', 'BuildingStack (Rent)', 'BuildingStack', 'Rent'),

    # Income
    (r'INSIGHT GLOBAL', 'Insight Global', 'Insight Global', 'Income'),

    # Buy Now Pay Later
    (r'AFFIRM', 'Affirm', 'Affirm', 'Shopping'),
]

# Pre-compile regex patterns for performance
_COMPILED_MAPPINGS = [
    (re.compile(pattern, re.IGNORECASE), company, parent, category)
    for pattern, company, parent, category in COMPANY_MAPPINGS
]

# Map spending categories to TransactionCategory enum
CATEGORY_TO_TRANSACTION_TYPE = {
    'Income': TransactionCategory.INCOME,
    'Transfer': TransactionCategory.TRANSFER,
    'Banking': TransactionCategory.FEE,
    'Refund': TransactionCategory.REFUND,
}


def categorize(description: str) -> Tuple[str, str, str]:
    """
    Categorize a transaction description.

    Returns:
        (company_name, parent_company, spending_category)
        Falls back to ('Other', 'Other', 'Other') if no match.
    """
    for pattern, company, parent, category in _COMPILED_MAPPINGS:
        if pattern.search(description):
            return company, parent, category
    return 'Other', 'Other', 'Other'


def get_transaction_category(spending_category: str, is_debit: bool) -> TransactionCategory:
    """Map a spending category string to a TransactionCategory enum value."""
    if spending_category in CATEGORY_TO_TRANSACTION_TYPE:
        return CATEGORY_TO_TRANSACTION_TYPE[spending_category]
    if not is_debit:
        return TransactionCategory.INCOME
    return TransactionCategory.EXPENSE
