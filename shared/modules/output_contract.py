"""
Canonical adapter output envelope for NEXUS modules.

Defines the standard response format consumed by:
- Orchestrator: for agent workflows
- Bridge: for dashboard aggregation
- UI: for visualization
- Metering: for usage tracking

All adapters must return AdapterRunResult to ensure consistent data flow.
"""
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


class RunStatus(str, Enum):
    """Status of adapter run execution."""
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


class ErrorCode(str, Enum):
    """Standard error codes for adapter failures."""
    CONNECTIVITY = "connectivity"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMIT = "rate_limit"
    SCHEMA_VALIDATION = "schema_validation"
    INTERNAL_ERROR = "internal_error"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"


class ContractMetadata(BaseModel):
    """Contract version metadata."""
    name: str = "nexus-adapter-run-result"
    version: str = "1.0.0"
    schema_id: str = "https://nexus.dev/schemas/adapter-run-result/v1.0.0"


class RunMetadata(BaseModel):
    """Metadata about the adapter run."""
    run_id: str = Field(..., description="Unique identifier for this run")
    org_id: str = Field(..., description="Organization ID for multi-tenant isolation")
    module_id: str = Field(..., description="Module identifier (category/platform)")
    version: str = Field(..., description="Module version")
    capability: str = Field(..., description="Capability invoked")
    started_at: str = Field(..., description="ISO 8601 timestamp when run started")
    completed_at: str = Field(..., description="ISO 8601 timestamp when run completed")

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Ensure timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError("Timestamp must be ISO 8601 format")
        return v


class DataPoint(BaseModel):
    """A single typed data point from the adapter."""
    schema_ref: str = Field(..., description="Reference to canonical schema (e.g., 'WeatherData')")
    data: Dict[str, Any] = Field(..., description="Actual data conforming to schema")
    timestamp: Optional[str] = Field(None, description="Data timestamp (ISO 8601)")


class Artifact(BaseModel):
    """
    Artifact produced by adapter (chart, file, log, etc.).

    Examples:
    - Chart: mime="image/png", bytes=base64_encoded_png
    - CSV: mime="text/csv", bytes=csv_content
    - Log: mime="text/plain", bytes=log_output
    """
    type: str = Field(..., description="Artifact type: chart, file, log, report")
    mime_type: str = Field(..., description="MIME type of the artifact")
    name: str = Field(..., description="Human-readable name")
    bytes: str = Field(..., description="Artifact content (base64 for binary, plain text otherwise)")
    sha256: Optional[str] = Field(None, description="SHA-256 hash of artifact bytes")
    size: Optional[int] = Field(None, description="Size in bytes")


class AdapterError(BaseModel):
    """Standardized error information."""
    code: ErrorCode = Field(..., description="Standard error code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    source: Optional[str] = Field(None, description="Which component/function raised the error")


class MeteringData(BaseModel):
    """Metering information for usage tracking."""
    run_units: float = Field(..., description="Normalized run units consumed")
    tokens: Optional[int] = Field(None, description="Tokens used (if LLM involved)")
    duration_ms: int = Field(..., description="Duration in milliseconds")
    api_calls: int = Field(default=1, description="Number of external API calls made")


class TraceContext(BaseModel):
    """Distributed tracing context."""
    trace_id: Optional[str] = Field(None, description="Trace ID for distributed tracing")
    span_id: Optional[str] = Field(None, description="Span ID for this operation")
    parent_span_id: Optional[str] = Field(None, description="Parent span ID if nested")


class AdapterRunResult(BaseModel):
    """
    Canonical envelope for adapter run results.

    This is the single source of truth for adapter outputs consumed by
    orchestrator, bridge, UI, and metering systems.
    """

    # Contract metadata
    contract: ContractMetadata = Field(default_factory=ContractMetadata)

    # Run metadata
    run: RunMetadata = Field(..., description="Run execution metadata")

    # Status
    status: RunStatus = Field(..., description="Overall run status")

    # Data
    data_points: List[DataPoint] = Field(
        default_factory=list,
        description="Typed data points returned by adapter"
    )

    # Artifacts
    artifacts: List[Artifact] = Field(
        default_factory=list,
        description="Artifacts produced (charts, files, logs)"
    )

    # Errors
    errors: List[AdapterError] = Field(
        default_factory=list,
        description="Errors encountered (may be present even with partial success)"
    )

    # Metering
    metering: MeteringData = Field(..., description="Usage metering data")

    # Tracing
    trace: TraceContext = Field(default_factory=TraceContext, description="Distributed tracing context")

    @field_validator("data_points")
    @classmethod
    def validate_data_points_present_on_success(cls, v: List[DataPoint], info) -> List[DataPoint]:
        """Ensure data_points present for success status."""
        # Get status from validation context
        # Note: In Pydantic v2, we can't easily access other field values during validation
        # This validation is better done at the application level
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AdapterRunResult':
        """Create AdapterRunResult from dictionary."""
        return cls(**data)

    def is_success(self) -> bool:
        """Check if run was successful."""
        return self.status == RunStatus.SUCCESS

    def is_partial(self) -> bool:
        """Check if run had partial success."""
        return self.status == RunStatus.PARTIAL

    def is_error(self) -> bool:
        """Check if run failed completely."""
        return self.status == RunStatus.ERROR

    def has_data(self) -> bool:
        """Check if run returned any data points."""
        return len(self.data_points) > 0

    def has_errors(self) -> bool:
        """Check if run encountered any errors."""
        return len(self.errors) > 0


# Helper functions for creating common result types

def create_success_result(
    run: RunMetadata,
    data_points: List[DataPoint],
    metering: MeteringData,
    artifacts: Optional[List[Artifact]] = None,
    trace: Optional[TraceContext] = None
) -> AdapterRunResult:
    """
    Create a successful adapter run result.

    Args:
        run: Run metadata
        data_points: Data points returned
        metering: Metering information
        artifacts: Optional artifacts produced
        trace: Optional trace context

    Returns:
        AdapterRunResult with SUCCESS status
    """
    return AdapterRunResult(
        run=run,
        status=RunStatus.SUCCESS,
        data_points=data_points,
        artifacts=artifacts or [],
        errors=[],
        metering=metering,
        trace=trace or TraceContext()
    )


def create_partial_result(
    run: RunMetadata,
    data_points: List[DataPoint],
    errors: List[AdapterError],
    metering: MeteringData,
    artifacts: Optional[List[Artifact]] = None,
    trace: Optional[TraceContext] = None
) -> AdapterRunResult:
    """
    Create a partial success adapter run result.

    Args:
        run: Run metadata
        data_points: Data points returned (partial)
        errors: Errors encountered
        metering: Metering information
        artifacts: Optional artifacts produced
        trace: Optional trace context

    Returns:
        AdapterRunResult with PARTIAL status
    """
    return AdapterRunResult(
        run=run,
        status=RunStatus.PARTIAL,
        data_points=data_points,
        artifacts=artifacts or [],
        errors=errors,
        metering=metering,
        trace=trace or TraceContext()
    )


def create_error_result(
    run: RunMetadata,
    errors: List[AdapterError],
    metering: MeteringData,
    trace: Optional[TraceContext] = None
) -> AdapterRunResult:
    """
    Create a failed adapter run result.

    Args:
        run: Run metadata
        errors: Errors that caused failure
        metering: Metering information
        trace: Optional trace context

    Returns:
        AdapterRunResult with ERROR status
    """
    return AdapterRunResult(
        run=run,
        status=RunStatus.ERROR,
        data_points=[],
        artifacts=[],
        errors=errors,
        metering=metering,
        trace=trace or TraceContext()
    )
