"""
Unified validation result types for NEXUS module system.

Single source of truth for validation reports used by validator and sandbox runner.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class ValidationSeverity(str, Enum):
    """Severity levels for validation entries."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationEntry:
    """
    Single validation finding.

    Attributes:
        severity: Severity level (ERROR, WARNING, INFO)
        category: Category of issue (import_violation, test_failure, etc.)
        message: Human-readable description
        file: Optional file path where issue occurred
        line: Optional line number
        fix_hint: Optional suggestion for fixing the issue
    """
    severity: ValidationSeverity
    category: str
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    fix_hint: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "fix_hint": self.fix_hint,
        }


@dataclass
class ValidationResult:
    """
    Unified validation result.

    Attributes:
        passed: Whether validation passed (no errors)
        entries: List of validation findings
        summary: High-level summary message
        checked_at: ISO timestamp of validation
    """
    passed: bool
    entries: List[ValidationEntry] = field(default_factory=list)
    summary: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")

    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary,
            "checked_at": self.checked_at,
        }

    def has_errors(self) -> bool:
        """Check if result contains any errors."""
        return any(e.severity == ValidationSeverity.ERROR for e in self.entries)

    def get_errors(self) -> List[ValidationEntry]:
        """Get all error entries."""
        return [e for e in self.entries if e.severity == ValidationSeverity.ERROR]

    def get_warnings(self) -> List[ValidationEntry]:
        """Get all warning entries."""
        return [e for e in self.entries if e.severity == ValidationSeverity.WARNING]


def merge_results(*results: ValidationResult) -> ValidationResult:
    """
    Merge multiple validation results into a single result.

    Args:
        *results: Variable number of ValidationResult objects

    Returns:
        Merged ValidationResult (passed only if all passed)
    """
    if not results:
        return ValidationResult(passed=True, summary="No validation results to merge")

    # Combine all entries
    all_entries = []
    for result in results:
        all_entries.extend(result.entries)

    # Passed only if all passed
    all_passed = all(r.passed for r in results)

    # Combine summaries
    summaries = [r.summary for r in results if r.summary]
    combined_summary = "; ".join(summaries) if summaries else ""

    return ValidationResult(
        passed=all_passed,
        entries=all_entries,
        summary=combined_summary,
        checked_at=datetime.now(timezone.utc).isoformat() + "Z"
    )
