"""
File Parser Scenario - Local file parsing (CSV, Excel, JSON).

Example: Bank CSV, Excel reports, JSON dumps
Pattern: Local file reading, column mapping, data transformation
"""
from .registry import ScenarioDefinition

SCENARIO = ScenarioDefinition(
    id="file_parser",
    name="File Parser",
    description="Local file parser for CSV, Excel, or JSON data files",
    nl_intent="Parse local CSV/Excel/JSON files and transform them into canonical data format",
    category="finance",
    auth_type="none",
    capabilities={
        "read": True,
        "write": False,
        "pagination": False,
        "rate_limited": False,
    },
    required_methods=["fetch_raw", "transform", "get_schema"],
    test_suites=["schema_drift"],  # No auth needed
    edge_cases=[
        "Missing columns in CSV",
        "Extra/unexpected columns",
        "Empty files or headers only",
        "Encoding issues (UTF-8 vs Latin-1)",
        "Date/number format variations",
        "Null/None values in cells",
    ],
    example_platforms=["cibc_csv", "excel_reports", "json_dumps"],
)
