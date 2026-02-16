"""Unit tests for output_contract.py - canonical adapter output envelope."""
import pytest
import json
from datetime import datetime, timezone
from pydantic import ValidationError
from shared.modules.output_contract import (
    AdapterRunResult,
    RunMetadata,
    RunStatus,
    ErrorCode,
    DataPoint,
    Artifact,
    AdapterError,
    MeteringData,
    TraceContext,
    ContractMetadata,
    create_success_result,
    create_partial_result,
    create_error_result
)


@pytest.fixture
def sample_run_metadata():
    """Sample run metadata."""
    return RunMetadata(
        run_id="run-123",
        org_id="org-456",
        module_id="weather/openweather",
        version="1.0.0",
        capability="current_weather",
        started_at="2026-02-15T12:00:00Z",
        completed_at="2026-02-15T12:00:05Z"
    )


@pytest.fixture
def sample_metering():
    """Sample metering data."""
    return MeteringData(
        run_units=1.0,
        tokens=None,
        duration_ms=5000,
        api_calls=1
    )


@pytest.fixture
def sample_data_point():
    """Sample data point."""
    return DataPoint(
        schema_ref="WeatherData",
        data={"temperature": 72, "humidity": 65},
        timestamp="2026-02-15T12:00:00Z"
    )


class TestContractMetadata:
    """Tests for ContractMetadata."""

    def test_default_metadata(self):
        """Test that default metadata is correct."""
        metadata = ContractMetadata()
        assert metadata.name == "nexus-adapter-run-result"
        assert metadata.version == "1.0.0"
        assert "v1.0.0" in metadata.schema_id


class TestRunMetadata:
    """Tests for RunMetadata."""

    def test_valid_run_metadata(self, sample_run_metadata):
        """Test that valid run metadata is accepted."""
        assert sample_run_metadata.run_id == "run-123"
        assert sample_run_metadata.org_id == "org-456"
        assert sample_run_metadata.module_id == "weather/openweather"

    def test_invalid_timestamp_rejected(self):
        """Test that invalid timestamps are rejected."""
        with pytest.raises(ValidationError, match="Timestamp must be ISO 8601"):
            RunMetadata(
                run_id="run-123",
                org_id="org-456",
                module_id="weather/openweather",
                version="1.0.0",
                capability="current_weather",
                started_at="invalid-timestamp",
                completed_at="2026-02-15T12:00:05Z"
            )

    def test_valid_iso8601_timestamps(self):
        """Test that various ISO 8601 formats are accepted."""
        valid_timestamps = [
            "2026-02-15T12:00:00Z",
            "2026-02-15T12:00:00+00:00",
            "2026-02-15T12:00:00.000Z",
        ]

        for ts in valid_timestamps:
            metadata = RunMetadata(
                run_id="run-123",
                org_id="org-456",
                module_id="weather/openweather",
                version="1.0.0",
                capability="test",
                started_at=ts,
                completed_at=ts
            )
            assert metadata.started_at == ts


class TestDataPoint:
    """Tests for DataPoint."""

    def test_valid_data_point(self, sample_data_point):
        """Test that valid data point is accepted."""
        assert sample_data_point.schema_ref == "WeatherData"
        assert sample_data_point.data["temperature"] == 72

    def test_data_point_without_timestamp(self):
        """Test that timestamp is optional."""
        dp = DataPoint(
            schema_ref="WeatherData",
            data={"temperature": 72}
        )
        assert dp.timestamp is None


class TestArtifact:
    """Tests for Artifact."""

    def test_valid_artifact(self):
        """Test that valid artifact is accepted."""
        artifact = Artifact(
            type="chart",
            mime_type="image/png",
            name="Temperature Chart",
            bytes="base64encodeddata",
            sha256="abc123",
            size=1024
        )
        assert artifact.type == "chart"
        assert artifact.mime_type == "image/png"

    def test_artifact_without_optional_fields(self):
        """Test that optional fields are not required."""
        artifact = Artifact(
            type="log",
            mime_type="text/plain",
            name="Debug Log",
            bytes="log content"
        )
        assert artifact.sha256 is None
        assert artifact.size is None


class TestAdapterError:
    """Tests for AdapterError."""

    def test_valid_error(self):
        """Test that valid error is accepted."""
        error = AdapterError(
            code=ErrorCode.CONNECTIVITY,
            message="Failed to connect to API",
            detail="Connection timeout after 30s",
            source="fetch_raw"
        )
        assert error.code == ErrorCode.CONNECTIVITY
        assert "timeout" in error.detail

    def test_error_codes_available(self):
        """Test that all standard error codes are available."""
        codes = [
            ErrorCode.CONNECTIVITY,
            ErrorCode.AUTHENTICATION,
            ErrorCode.AUTHORIZATION,
            ErrorCode.RATE_LIMIT,
            ErrorCode.SCHEMA_VALIDATION,
            ErrorCode.INTERNAL_ERROR,
            ErrorCode.TIMEOUT,
            ErrorCode.NOT_FOUND,
            ErrorCode.INVALID_INPUT
        ]
        assert len(codes) == 9


class TestMeteringData:
    """Tests for MeteringData."""

    def test_valid_metering(self, sample_metering):
        """Test that valid metering data is accepted."""
        assert sample_metering.run_units == 1.0
        assert sample_metering.duration_ms == 5000

    def test_metering_with_tokens(self):
        """Test metering data with LLM tokens."""
        metering = MeteringData(
            run_units=2.5,
            tokens=1500,
            duration_ms=10000,
            api_calls=3
        )
        assert metering.tokens == 1500


class TestTraceContext:
    """Tests for TraceContext."""

    def test_trace_context_optional(self):
        """Test that trace context fields are optional."""
        trace = TraceContext()
        assert trace.trace_id is None
        assert trace.span_id is None

    def test_trace_context_with_ids(self):
        """Test trace context with IDs."""
        trace = TraceContext(
            trace_id="trace-123",
            span_id="span-456",
            parent_span_id="span-789"
        )
        assert trace.trace_id == "trace-123"
        assert trace.span_id == "span-456"


class TestAdapterRunResult:
    """Tests for AdapterRunResult envelope."""

    def test_success_result(self, sample_run_metadata, sample_data_point, sample_metering):
        """Test creating a success result."""
        result = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.SUCCESS,
            data_points=[sample_data_point],
            metering=sample_metering
        )

        assert result.status == RunStatus.SUCCESS
        assert len(result.data_points) == 1
        assert len(result.errors) == 0
        assert result.is_success()
        assert not result.is_error()
        assert result.has_data()

    def test_partial_result(self, sample_run_metadata, sample_data_point, sample_metering):
        """Test creating a partial result."""
        error = AdapterError(
            code=ErrorCode.RATE_LIMIT,
            message="Rate limit exceeded for some requests"
        )

        result = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.PARTIAL,
            data_points=[sample_data_point],
            errors=[error],
            metering=sample_metering
        )

        assert result.status == RunStatus.PARTIAL
        assert result.is_partial()
        assert result.has_data()
        assert result.has_errors()

    def test_error_result(self, sample_run_metadata, sample_metering):
        """Test creating an error result."""
        error = AdapterError(
            code=ErrorCode.AUTHENTICATION,
            message="Invalid API key"
        )

        result = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.ERROR,
            errors=[error],
            metering=sample_metering
        )

        assert result.status == RunStatus.ERROR
        assert result.is_error()
        assert not result.has_data()
        assert result.has_errors()

    def test_serialization_round_trip(self, sample_run_metadata, sample_data_point, sample_metering):
        """Test that AdapterRunResult can be serialized and deserialized."""
        original = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.SUCCESS,
            data_points=[sample_data_point],
            metering=sample_metering
        )

        # Serialize
        data = original.to_dict()
        json_str = json.dumps(data)

        # Deserialize
        restored_data = json.loads(json_str)
        restored = AdapterRunResult.from_dict(restored_data)

        assert restored.run.run_id == original.run.run_id
        assert restored.status == original.status
        assert len(restored.data_points) == len(original.data_points)

    def test_contract_metadata_included(self, sample_run_metadata, sample_metering):
        """Test that contract metadata is automatically included."""
        result = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.SUCCESS,
            metering=sample_metering
        )

        assert result.contract.name == "nexus-adapter-run-result"
        assert result.contract.version == "1.0.0"

    def test_result_with_artifacts(self, sample_run_metadata, sample_data_point, sample_metering):
        """Test result with artifacts."""
        artifact = Artifact(
            type="chart",
            mime_type="image/png",
            name="Chart",
            bytes="data"
        )

        result = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.SUCCESS,
            data_points=[sample_data_point],
            artifacts=[artifact],
            metering=sample_metering
        )

        assert len(result.artifacts) == 1
        assert result.artifacts[0].type == "chart"

    def test_result_with_trace_context(self, sample_run_metadata, sample_metering):
        """Test result with tracing information."""
        trace = TraceContext(
            trace_id="trace-123",
            span_id="span-456"
        )

        result = AdapterRunResult(
            run=sample_run_metadata,
            status=RunStatus.SUCCESS,
            metering=sample_metering,
            trace=trace
        )

        assert result.trace.trace_id == "trace-123"
        assert result.trace.span_id == "span-456"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_success_result(self, sample_run_metadata, sample_data_point, sample_metering):
        """Test create_success_result helper."""
        result = create_success_result(
            run=sample_run_metadata,
            data_points=[sample_data_point],
            metering=sample_metering
        )

        assert result.status == RunStatus.SUCCESS
        assert len(result.data_points) == 1
        assert len(result.errors) == 0

    def test_create_partial_result(self, sample_run_metadata, sample_data_point, sample_metering):
        """Test create_partial_result helper."""
        error = AdapterError(
            code=ErrorCode.RATE_LIMIT,
            message="Rate limit hit"
        )

        result = create_partial_result(
            run=sample_run_metadata,
            data_points=[sample_data_point],
            errors=[error],
            metering=sample_metering
        )

        assert result.status == RunStatus.PARTIAL
        assert len(result.data_points) == 1
        assert len(result.errors) == 1

    def test_create_error_result(self, sample_run_metadata, sample_metering):
        """Test create_error_result helper."""
        error = AdapterError(
            code=ErrorCode.CONNECTIVITY,
            message="Network error"
        )

        result = create_error_result(
            run=sample_run_metadata,
            errors=[error],
            metering=sample_metering
        )

        assert result.status == RunStatus.ERROR
        assert len(result.data_points) == 0
        assert len(result.errors) == 1


class TestRealWorldScenarios:
    """Tests for real-world adapter scenarios."""

    def test_weather_adapter_success(self):
        """Test a realistic weather adapter success response."""
        run = RunMetadata(
            run_id="run-weather-001",
            org_id="org-test",
            module_id="weather/openweather",
            version="1.0.0",
            capability="current_weather",
            started_at="2026-02-15T12:00:00Z",
            completed_at="2026-02-15T12:00:02Z"
        )

        data_point = DataPoint(
            schema_ref="WeatherData",
            data={
                "temperature": 72.5,
                "humidity": 65,
                "conditions": "Partly Cloudy",
                "wind_speed": 8.5
            },
            timestamp="2026-02-15T12:00:00Z"
        )

        metering = MeteringData(
            run_units=0.5,
            duration_ms=2000,
            api_calls=1
        )

        result = create_success_result(
            run=run,
            data_points=[data_point],
            metering=metering
        )

        assert result.is_success()
        assert result.run.module_id == "weather/openweather"
        assert result.data_points[0].data["temperature"] == 72.5

    def test_finance_adapter_partial(self):
        """Test a realistic finance adapter partial response."""
        run = RunMetadata(
            run_id="run-finance-001",
            org_id="org-test",
            module_id="finance/plaid",
            version="2.0.0",
            capability="transactions",
            started_at="2026-02-15T12:00:00Z",
            completed_at="2026-02-15T12:00:10Z"
        )

        # Got some transactions but hit rate limit
        data_points = [
            DataPoint(
                schema_ref="FinancialTransaction",
                data={"amount": 25.50, "merchant": "Coffee Shop"},
                timestamp="2026-02-14T08:30:00Z"
            ),
            DataPoint(
                schema_ref="FinancialTransaction",
                data={"amount": 120.00, "merchant": "Grocery Store"},
                timestamp="2026-02-14T14:15:00Z"
            )
        ]

        errors = [
            AdapterError(
                code=ErrorCode.RATE_LIMIT,
                message="Rate limit exceeded, partial data returned",
                detail="Retrieved 2 of 50 transactions"
            )
        ]

        metering = MeteringData(
            run_units=1.5,
            duration_ms=10000,
            api_calls=3
        )

        result = create_partial_result(
            run=run,
            data_points=data_points,
            errors=errors,
            metering=metering
        )

        assert result.is_partial()
        assert len(result.data_points) == 2
        assert result.errors[0].code == ErrorCode.RATE_LIMIT

    def test_calendar_adapter_auth_error(self):
        """Test a realistic calendar adapter authentication error."""
        run = RunMetadata(
            run_id="run-calendar-001",
            org_id="org-test",
            module_id="calendar/google",
            version="1.0.0",
            capability="list_events",
            started_at="2026-02-15T12:00:00Z",
            completed_at="2026-02-15T12:00:01Z"
        )

        errors = [
            AdapterError(
                code=ErrorCode.AUTHENTICATION,
                message="OAuth2 token expired",
                detail="Refresh token is invalid or revoked",
                source="fetch_raw"
            )
        ]

        metering = MeteringData(
            run_units=0.1,
            duration_ms=1000,
            api_calls=1
        )

        result = create_error_result(
            run=run,
            errors=errors,
            metering=metering
        )

        assert result.is_error()
        assert result.errors[0].code == ErrorCode.AUTHENTICATION
        assert not result.has_data()
