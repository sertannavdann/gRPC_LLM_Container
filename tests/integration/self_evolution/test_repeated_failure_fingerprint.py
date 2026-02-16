"""
Integration test: Repeated failure fingerprint detection.

Verifies that the repair loop stops early when the same failure fingerprint
appears twice consecutively (thrash detection).
"""
import pytest
from shared.modules.audit import (
    BuildAuditLog,
    AttemptRecord,
    AttemptStatus,
    FailureType,
    FailureFingerprint,
)


def test_repeated_failure_fingerprint_stops_early(tmp_path):
    """Test that identical failure fingerprint twice stops repair loop."""
    # Create audit log with two consecutive identical failures
    audit_log = BuildAuditLog(
        job_id="test_thrashing",
        module_id="test/module"
    )

    # Same failure fingerprint for both attempts
    fingerprint = "same_failure_hash"

    # Add first failed attempt
    attempt1 = AttemptRecord(
        attempt_number=1,
        bundle_sha256="hash_1",
        stage="repair",
        status=AttemptStatus.FAILED,
        failure_type=FailureType.TEST_FAILURE,
        failure_fingerprint=fingerprint
    )
    audit_log.add_attempt(attempt1)

    # Add second failed attempt with same fingerprint
    attempt2 = AttemptRecord(
        attempt_number=2,
        bundle_sha256="hash_2",
        stage="repair",
        status=AttemptStatus.FAILED,
        failure_type=FailureType.TEST_FAILURE,
        failure_fingerprint=fingerprint
    )
    audit_log.add_attempt(attempt2)

    # Verify thrashing detection
    assert audit_log.has_consecutive_identical_failures() is True


def test_different_failure_fingerprints_allow_continuation(tmp_path):
    """Test that different failure fingerprints allow repair to continue."""
    # Create audit log with different failures
    audit_log = BuildAuditLog(
        job_id="test_different_failures",
        module_id="test/module"
    )

    # Add attempts with different fingerprints
    attempt1 = AttemptRecord(
        attempt_number=1,
        bundle_sha256="hash_1",
        stage="repair",
        status=AttemptStatus.FAILED,
        failure_type=FailureType.TEST_FAILURE,
        failure_fingerprint="fp_1"
    )
    audit_log.add_attempt(attempt1)

    attempt2 = AttemptRecord(
        attempt_number=2,
        bundle_sha256="hash_2",
        stage="repair",
        status=AttemptStatus.FAILED,
        failure_type=FailureType.TEST_FAILURE,
        failure_fingerprint="fp_2"  # Different fingerprint
    )
    audit_log.add_attempt(attempt2)

    # Verify no thrashing
    assert audit_log.has_consecutive_identical_failures() is False


def test_failure_fingerprint_from_validation_report():
    """Test fingerprint generation from validation report."""
    validation_report = {
        "status": "FAILED",
        "static_results": [
            {"name": "syntax", "passed": False},
            {"name": "imports", "passed": False},
        ],
        "runtime_results": {
            "stderr": "FAIL: test_fetch_data\nERROR: test_transform",
            "stdout": "PASS: test_init",
        },
        "fix_hints": [
            {"category": "syntax_error", "message": "Fix syntax"},
            {"category": "import_violation", "message": "Remove forbidden import"},
        ],
    }

    fingerprint = FailureFingerprint.from_validation_report(validation_report)

    # Should extract error types
    assert "syntax" in fingerprint.error_types
    assert "imports" in fingerprint.error_types

    # Should extract failing tests
    assert "test_fetch_data" in fingerprint.failing_tests
    assert "test_transform" in fingerprint.failing_tests

    # Should extract fix hint categories
    assert "syntax_error" in fingerprint.fix_hint_categories
    assert "import_violation" in fingerprint.fix_hint_categories

    # Hash should be deterministic
    hash1 = fingerprint.hash
    fingerprint2 = FailureFingerprint.from_validation_report(validation_report)
    assert hash1 == fingerprint2.hash


def test_success_between_failures_resets_thrashing():
    """Test that a success between failures prevents thrashing detection."""
    audit_log = BuildAuditLog(
        job_id="test_success_reset",
        module_id="test/module"
    )

    # Fail 1
    audit_log.add_attempt(AttemptRecord(
        attempt_number=1,
        bundle_sha256="hash_1",
        stage="repair",
        status=AttemptStatus.FAILED,
        failure_fingerprint="fp_1"
    ))

    # Success
    audit_log.add_attempt(AttemptRecord(
        attempt_number=2,
        bundle_sha256="hash_2",
        stage="repair",
        status=AttemptStatus.SUCCESS,
        failure_fingerprint=None
    ))

    # Fail 2 (same fingerprint as Fail 1)
    audit_log.add_attempt(AttemptRecord(
        attempt_number=3,
        bundle_sha256="hash_3",
        stage="repair",
        status=AttemptStatus.FAILED,
        failure_fingerprint="fp_1"
    ))

    # Should NOT detect thrashing (success in between)
    assert audit_log.has_consecutive_identical_failures() is False
