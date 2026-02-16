"""
Audit trail system for module build and repair attempts.

Provides immutable per-attempt records with artifact references for:
- Build attempts (scaffold, implement, tests)
- Validation reports (static + runtime)
- Repair attempts with fix hints and failure fingerprints
- Terminal failure classification

Key features:
- Immutable AttemptRecord: never mutated after creation
- Failure fingerprinting for thrash detection
- Terminal vs retryable failure classification
- Full audit log with structured metadata
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """Classification of failure types for repair decisions."""
    # Retryable failures (can attempt repair)
    TEST_FAILURE = "test_failure"
    SCHEMA_MISMATCH = "schema_mismatch"
    MISSING_METHOD = "missing_method"
    IMPORT_VIOLATION = "import_violation"
    SYNTAX_ERROR = "syntax_error"

    # Terminal failures (stop immediately, no repair)
    POLICY_VIOLATION = "policy_violation"
    SECURITY_BLOCK = "security_block"
    BUDGET_EXCEEDED = "budget_exceeded"
    GATEWAY_FAILURE = "gateway_failure"


class AttemptStatus(str, Enum):
    """Status of a single generation attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class FailureFingerprint:
    """
    Fingerprint for detecting repeated identical failures.

    Hash is computed from:
    - Error types (sorted list)
    - Failing test names (sorted list)
    - Fix hint categories (sorted list)

    Enables thrash detection: if same fingerprint appears twice consecutively,
    stop repair loop early.
    """
    error_types: List[str]
    failing_tests: List[str]
    fix_hint_categories: List[str]

    @property
    def hash(self) -> str:
        """Compute deterministic hash from failure components."""
        components = {
            "error_types": sorted(self.error_types),
            "failing_tests": sorted(self.failing_tests),
            "fix_hint_categories": sorted(self.fix_hint_categories),
        }
        content = json.dumps(components, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @classmethod
    def from_validation_report(cls, report: Dict[str, Any]) -> "FailureFingerprint":
        """Create fingerprint from validation report."""
        error_types = []
        failing_tests = []
        fix_hint_categories = []

        # Extract error types from static results
        for static_result in report.get("static_results", []):
            if not static_result.get("passed", True):
                error_types.append(static_result.get("name", "unknown"))

        # Extract failing tests from runtime results
        runtime = report.get("runtime_results")
        if runtime:
            # Parse test names from stderr/stdout if available
            stderr = runtime.get("stderr", "")
            stdout = runtime.get("stdout", "")
            for line in (stderr + "\n" + stdout).split("\n"):
                if "FAIL:" in line or "ERROR:" in line:
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        test_name = parts[1].strip()
                        if test_name:
                            failing_tests.append(test_name)

        # Extract fix hint categories
        for hint in report.get("fix_hints", []):
            category = hint.get("category", "unknown")
            fix_hint_categories.append(category)

        return cls(
            error_types=error_types,
            failing_tests=failing_tests,
            fix_hint_categories=fix_hint_categories
        )


@dataclass
class AttemptRecord:
    """
    Immutable record of a single generation/repair attempt.

    Attributes:
        attempt_number: Sequential attempt number (1-indexed)
        bundle_sha256: Content-addressed artifact bundle hash
        stage: Generation stage (scaffold, implement, tests, repair)
        status: SUCCESS | FAILED | ERROR
        validation_report: Full validation report dict (if validated)
        logs: Captured logs from generation/validation
        failure_fingerprint: Hash for thrash detection (if failed)
        failure_type: Classification for repair decisions (if failed)
        timestamp: ISO timestamp of attempt
        metadata: Additional context (model used, tokens, etc.)
    """
    attempt_number: int
    bundle_sha256: str
    stage: str
    status: AttemptStatus
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")
    validation_report: Optional[Dict[str, Any]] = None
    logs: List[str] = field(default_factory=list)
    failure_fingerprint: Optional[str] = None
    failure_type: Optional[FailureType] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to values
        if isinstance(data.get("status"), Enum):
            data["status"] = data["status"].value
        if isinstance(data.get("failure_type"), Enum):
            data["failure_type"] = data["failure_type"].value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttemptRecord":
        """Create AttemptRecord from dictionary."""
        # Convert string enums back
        if "status" in data:
            data["status"] = AttemptStatus(data["status"])
        if "failure_type" in data and data["failure_type"]:
            data["failure_type"] = FailureType(data["failure_type"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BuildAuditLog:
    """
    Complete audit trail for a module build job.

    Attributes:
        job_id: Unique identifier for build job
        module_id: Module identifier (category/platform)
        attempts: List of all attempt records (immutable)
        final_status: Final outcome (VALIDATED, FAILED, ERROR)
        total_duration_ms: Total time from start to completion
        created_at: ISO timestamp of job start
        completed_at: ISO timestamp of job completion
        metadata: Additional job-level context
    """
    job_id: str
    module_id: str
    attempts: List[AttemptRecord] = field(default_factory=list)
    final_status: str = "PENDING"
    total_duration_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_attempt(self, attempt: AttemptRecord) -> None:
        """
        Add attempt record to audit log.

        Attempts are immutable once added. Never modify existing records.
        """
        self.attempts.append(attempt)

    def get_last_fingerprint(self) -> Optional[str]:
        """Get failure fingerprint from last failed attempt."""
        if not self.attempts:
            return None
        last = self.attempts[-1]
        return last.failure_fingerprint if last.status == AttemptStatus.FAILED else None

    def has_consecutive_identical_failures(self) -> bool:
        """
        Check if last two attempts have identical failure fingerprints.

        Returns True if thrashing detected (same failure twice in a row).
        """
        if len(self.attempts) < 2:
            return False

        last_two = self.attempts[-2:]
        if all(a.status == AttemptStatus.FAILED for a in last_two):
            fp1 = last_two[0].failure_fingerprint
            fp2 = last_two[1].failure_fingerprint
            return fp1 is not None and fp1 == fp2

        return False

    def classify_failure_type(self, validation_report: Dict[str, Any]) -> FailureType:
        """
        Classify failure as retryable or terminal.

        Terminal failures stop repair loop immediately:
        - policy_violation: Security/compliance violations
        - security_block: Forbidden imports, dangerous operations
        - budget_exceeded: Token/cost limits reached
        - gateway_failure: LLM provider errors

        Retryable failures allow repair attempts:
        - test_failure: Unit/integration tests failed
        - schema_mismatch: Output doesn't match contract
        - missing_method: Required methods not implemented
        - import_violation: Forbidden but fixable imports
        - syntax_error: Python syntax errors
        """
        # Check for terminal failures first
        fix_hints = validation_report.get("fix_hints", [])

        for hint in fix_hints:
            category = hint.get("category", "")

            # Terminal: Policy/security violations
            if category in ["policy_violation", "security_block"]:
                return FailureType.POLICY_VIOLATION

            # Terminal: Budget issues (if we add budget tracking later)
            if category == "budget_exceeded":
                return FailureType.BUDGET_EXCEEDED

        # Check for retryable failures
        for hint in fix_hints:
            category = hint.get("category", "")

            if category == "test_failure":
                return FailureType.TEST_FAILURE
            elif category == "schema_error":
                return FailureType.SCHEMA_MISMATCH
            elif category == "missing_method":
                return FailureType.MISSING_METHOD
            elif category == "import_violation":
                return FailureType.IMPORT_VIOLATION
            elif category == "syntax_error":
                return FailureType.SYNTAX_ERROR

        # Default to test failure for unknown cases
        return FailureType.TEST_FAILURE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "module_id": self.module_id,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_status": self.final_status,
            "total_duration_ms": self.total_duration_ms,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildAuditLog":
        """Create BuildAuditLog from dictionary."""
        attempts_data = data.pop("attempts", [])
        log = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        log.attempts = [AttemptRecord.from_dict(a) for a in attempts_data]
        return log

    def save(self, audit_dir: Path) -> Path:
        """
        Save audit log to disk.

        Args:
            audit_dir: Base directory for audit logs

        Returns:
            Path to saved audit file
        """
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / f"{self.job_id}_audit.json"
        audit_file.write_text(json.dumps(self.to_dict(), indent=2))
        return audit_file

    @classmethod
    def load(cls, audit_file: Path) -> "BuildAuditLog":
        """Load audit log from disk."""
        data = json.loads(audit_file.read_text())
        return cls.from_dict(data)


@dataclass
class AuditEvent:
    """
    Single audit event for dev-mode actions.

    Attributes:
        event_id: Unique event identifier
        action: Action type (draft_created, draft_edited, etc.)
        actor: Identity of user who performed the action
        timestamp: ISO timestamp of action
        module_id: Module identifier (if applicable)
        draft_id: Draft identifier (if applicable)
        details: Additional context (file hashes, version refs, etc.)
    """
    event_id: str
    action: str
    actor: str
    timestamp: str
    module_id: Optional[str] = None
    draft_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        """Create AuditEvent from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DevModeAuditLog:
    """
    Audit trail for dev-mode operations.

    Records all draft lifecycle actions with actor identity and artifact hashes:
    - draft_created
    - draft_edited
    - draft_diff_viewed
    - draft_validated
    - draft_promoted
    - draft_discarded
    - version_rollback

    Logs are append-only JSONL format for immutability and streaming.
    """

    def __init__(self, audit_dir: Path):
        """
        Initialize dev-mode audit log.

        Args:
            audit_dir: Directory for audit logs
        """
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.audit_dir / "dev_mode_audit.jsonl"

    def log_action(
        self,
        action: str,
        actor: str,
        module_id: Optional[str] = None,
        draft_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a dev-mode action.

        Args:
            action: Action type
            actor: User identity
            module_id: Module identifier (if applicable)
            draft_id: Draft identifier (if applicable)
            details: Additional context

        Returns:
            event_id
        """
        event_id = hashlib.sha256(
            f"{action}_{actor}_{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        event = AuditEvent(
            event_id=event_id,
            action=action,
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat() + "Z",
            module_id=module_id,
            draft_id=draft_id,
            details=details or {}
        )

        # Append to JSONL file
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        logger.debug(f"Audit event logged: {action} by {actor}")

        return event_id

    def get_events(
        self,
        module_id: Optional[str] = None,
        draft_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """
        Query audit events with filters.

        Args:
            module_id: Filter by module identifier
            draft_id: Filter by draft identifier
            action: Filter by action type
            limit: Maximum number of events to return

        Returns:
            List of AuditEvent
        """
        if not self.audit_file.exists():
            return []

        events = []
        with open(self.audit_file, "r") as f:
            for line in f:
                event = AuditEvent.from_dict(json.loads(line))

                # Apply filters
                if module_id and event.module_id != module_id:
                    continue
                if draft_id and event.draft_id != draft_id:
                    continue
                if action and event.action != action:
                    continue

                events.append(event)

                if len(events) >= limit:
                    break

        return events[-limit:]  # Return most recent
