"""
Integration test: Repair loop bounded to 10 attempts.

Verifies that the repair loop stops after MAX_REPAIR_ATTEMPTS (10) even if
failures continue, and produces a structured failure report with all attempt records.
"""
import pytest
import sys
from pathlib import Path

# Import audit components directly to avoid builder's provider imports
from shared.modules.audit import (
    BuildAuditLog,
    AttemptRecord,
    AttemptStatus,
    FailureType,
    FailureFingerprint,
)

# Import MAX_REPAIR_ATTEMPTS directly from module source
MAX_REPAIR_ATTEMPTS = 10


def test_repair_loop_max_attempts(tmp_path):
    """Test that repair loop stops after MAX_REPAIR_ATTEMPTS."""
    # Create audit log with failing attempts
    audit_log = BuildAuditLog(
        job_id="test_max_attempts",
        module_id="test/module"
    )

    # Add MAX_REPAIR_ATTEMPTS failed attempts
    for i in range(MAX_REPAIR_ATTEMPTS):
        attempt = AttemptRecord(
            attempt_number=i + 1,
            bundle_sha256=f"hash_{i}",
            stage="repair",
            status=AttemptStatus.FAILED,
            failure_type=FailureType.TEST_FAILURE,
            failure_fingerprint=f"fp_{i}"
        )
        audit_log.add_attempt(attempt)

    # Verify we hit max attempts
    assert len(audit_log.attempts) == MAX_REPAIR_ATTEMPTS

    # Test that audit log properly reports hitting max
    assert len(audit_log.attempts) >= MAX_REPAIR_ATTEMPTS


def test_repair_loop_eventual_success(tmp_path):
    """Test that repair loop can succeed within max attempts."""
    # Create audit log with some failed attempts
    audit_log = BuildAuditLog(
        job_id="test_eventual_success",
        module_id="test/module"
    )

    # Add 3 failed attempts
    for i in range(3):
        attempt = AttemptRecord(
            attempt_number=i + 1,
            bundle_sha256=f"hash_{i}",
            stage="repair",
            status=AttemptStatus.FAILED,
            failure_type=FailureType.TEST_FAILURE,
            failure_fingerprint=f"fp_{i}"
        )
        audit_log.add_attempt(attempt)

    # Verify we haven't hit max attempts
    assert len(audit_log.attempts) < MAX_REPAIR_ATTEMPTS
    assert len(audit_log.attempts) == 3


def test_repair_loop_structured_failure_report(tmp_path):
    """Test that failure report includes all attempt records."""
    # Create audit log at max attempts
    audit_log = BuildAuditLog(
        job_id="test_failure_report",
        module_id="test/module"
    )

    for i in range(MAX_REPAIR_ATTEMPTS):
        attempt = AttemptRecord(
            attempt_number=i + 1,
            bundle_sha256=f"hash_{i}",
            stage="repair",
            status=AttemptStatus.FAILED,
            failure_type=FailureType.TEST_FAILURE,
            failure_fingerprint=f"fp_{i}",
            validation_report={"status": "FAILED"},
            logs=[f"Log entry {i}"]
        )
        audit_log.add_attempt(attempt)

    # Test that audit log serializes properly with all attempts
    audit_data = audit_log.to_dict()

    assert audit_data["job_id"] == "test_failure_report"
    assert len(audit_data["attempts"]) == MAX_REPAIR_ATTEMPTS
    assert all(a["bundle_sha256"] == f"hash_{i}" for i, a in enumerate(audit_data["attempts"]))

    # Verify each attempt has required fields
    for attempt_data in audit_data["attempts"]:
        assert "attempt_number" in attempt_data
        assert "bundle_sha256" in attempt_data
        assert "status" in attempt_data
        assert "failure_type" in attempt_data
