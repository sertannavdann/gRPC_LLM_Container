"""
Tests for adapter output schema contract.

Verifies that:
- Adapters produce AdapterRunResult envelope
- Required fields are present (contract, run, status, data_points)
- Error codes use standardized values
- Timestamps are valid ISO 8601 format
- Metering data is included
"""
import pytest
from datetime import datetime
from pydantic import ValidationError


class TestOutputSchemaContract:
    """Contract tests for AdapterRunResult output envelope."""

    def test_required_fields_present_in_schema(self):
        """Verify AdapterRunResult has all required fields."""
        from shared.modules.output_contract import AdapterRunResult

        # Get model fields
        fields = AdapterRunResult.model_fields
        required_fields = ["contract", "run", "status", "data_points", "metering"]

        for field in required_fields:
            assert field in fields, f"Missing required field: {field}"

    def test_creates_success_result_with_minimal_data(self):
        """Verify successful result can be created with minimal required data."""
        from shared.modules.output_contract import (
            create_success_result,
            RunMetadata,
            MeteringData,
            DataPoint,
        )

        run = RunMetadata(
            run_id="test-run-1",
            org_id="test-org",
            module_id="test/platform",
            version="1.0.0",
            capability="read",
            started_at="2026-02-15T10:00:00Z",
            completed_at="2026-02-15T10:00:05Z",
        )

        metering = MeteringData(
            run_units=1.0,
            duration_ms=5000,
        )

        data_points = [
            DataPoint(
                schema_ref="TestSchema",
                data={"test": "value"}
            )
        ]

        result = create_success_result(
            run=run,
            data_points=data_points,
            metering=metering,
        )

        assert result.is_success()
        assert len(result.data_points) == 1
        assert not result.has_errors()

    def test_creates_error_result_with_standard_error_code(self):
        """Verify error result uses standardized error codes."""
        from shared.modules.output_contract import (
            create_error_result,
            RunMetadata,
            MeteringData,
            AdapterError,
            ErrorCode,
        )

        run = RunMetadata(
            run_id="test-run-2",
            org_id="test-org",
            module_id="test/platform",
            version="1.0.0",
            capability="read",
            started_at="2026-02-15T10:00:00Z",
            completed_at="2026-02-15T10:00:01Z",
        )

        metering = MeteringData(
            run_units=0.1,
            duration_ms=1000,
        )

        errors = [
            AdapterError(
                code=ErrorCode.AUTHENTICATION,
                message="Invalid API key",
                detail="API key expired",
                source="fetch_raw",
            )
        ]

        result = create_error_result(
            run=run,
            errors=errors,
            metering=metering,
        )

        assert result.is_error()
        assert result.has_errors()
        assert len(result.errors) == 1
        assert result.errors[0].code == ErrorCode.AUTHENTICATION

    def test_creates_partial_result_with_data_and_errors(self):
        """Verify partial result can contain both data and errors."""
        from shared.modules.output_contract import (
            create_partial_result,
            RunMetadata,
            MeteringData,
            DataPoint,
            AdapterError,
            ErrorCode,
        )

        run = RunMetadata(
            run_id="test-run-3",
            org_id="test-org",
            module_id="test/platform",
            version="1.0.0",
            capability="read",
            started_at="2026-02-15T10:00:00Z",
            completed_at="2026-02-15T10:00:03Z",
        )

        metering = MeteringData(
            run_units=0.5,
            duration_ms=3000,
        )

        data_points = [
            DataPoint(schema_ref="TestSchema", data={"id": 1}),
        ]

        errors = [
            AdapterError(
                code=ErrorCode.RATE_LIMIT,
                message="Rate limit exceeded for batch 2",
            )
        ]

        result = create_partial_result(
            run=run,
            data_points=data_points,
            errors=errors,
            metering=metering,
        )

        assert result.is_partial()
        assert result.has_data()
        assert result.has_errors()

    def test_validates_iso8601_timestamps(self):
        """Verify timestamps must be valid ISO 8601 format."""
        from shared.modules.output_contract import RunMetadata

        # Valid timestamps
        valid_timestamps = [
            "2026-02-15T10:00:00Z",
            "2026-02-15T10:00:00+00:00",
            "2026-02-15T10:00:00.123456Z",
        ]

        for ts in valid_timestamps:
            run = RunMetadata(
                run_id="test",
                org_id="org",
                module_id="test/platform",
                version="1.0.0",
                capability="read",
                started_at=ts,
                completed_at=ts,
            )
            assert run.started_at == ts

        # Invalid timestamps should raise validation error
        with pytest.raises(ValidationError):
            RunMetadata(
                run_id="test",
                org_id="org",
                module_id="test/platform",
                version="1.0.0",
                capability="read",
                started_at="not-a-timestamp",
                completed_at="2026-02-15T10:00:00Z",
            )

    def test_error_code_enum_values(self):
        """Verify ErrorCode enum contains expected standard codes."""
        from shared.modules.output_contract import ErrorCode

        expected_codes = [
            "CONNECTIVITY",
            "AUTHENTICATION",
            "AUTHORIZATION",
            "RATE_LIMIT",
            "SCHEMA_VALIDATION",
            "INTERNAL_ERROR",
            "TIMEOUT",
            "NOT_FOUND",
            "INVALID_INPUT",
        ]

        enum_values = [e.name for e in ErrorCode]

        for code in expected_codes:
            assert code in enum_values, f"Missing standard error code: {code}"

    def test_run_status_enum_values(self):
        """Verify RunStatus enum contains expected values."""
        from shared.modules.output_contract import RunStatus

        assert RunStatus.SUCCESS.value == "success"
        assert RunStatus.PARTIAL.value == "partial"
        assert RunStatus.ERROR.value == "error"

    def test_contract_metadata_fields(self):
        """Verify contract metadata contains required identification fields."""
        from shared.modules.output_contract import ContractMetadata

        metadata = ContractMetadata()

        assert metadata.name == "nexus-adapter-run-result"
        assert metadata.version == "1.0.0"
        assert "nexus.dev/schemas" in metadata.schema_id

    def test_metering_data_required_fields(self):
        """Verify MeteringData contains required metering fields."""
        from shared.modules.output_contract import MeteringData

        metering = MeteringData(
            run_units=2.5,
            duration_ms=5000,
        )

        assert metering.run_units == 2.5
        assert metering.duration_ms == 5000
        assert metering.api_calls == 1  # default value

    def test_data_point_schema_reference(self):
        """Verify DataPoint references canonical schemas."""
        from shared.modules.output_contract import DataPoint

        data_point = DataPoint(
            schema_ref="WeatherData",
            data={
                "temperature": 72.5,
                "condition": "sunny",
            },
            timestamp="2026-02-15T10:00:00Z",
        )

        assert data_point.schema_ref == "WeatherData"
        assert data_point.data["temperature"] == 72.5

    def test_result_to_dict_serialization(self):
        """Verify AdapterRunResult can be serialized to dict."""
        from shared.modules.output_contract import (
            create_success_result,
            RunMetadata,
            MeteringData,
            DataPoint,
        )

        run = RunMetadata(
            run_id="test-serial",
            org_id="org",
            module_id="test/platform",
            version="1.0.0",
            capability="read",
            started_at="2026-02-15T10:00:00Z",
            completed_at="2026-02-15T10:00:01Z",
        )

        metering = MeteringData(run_units=1.0, duration_ms=1000)
        data_points = [DataPoint(schema_ref="Test", data={"key": "value"})]

        result = create_success_result(run, data_points, metering)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["status"] == "success"
        assert "run" in result_dict
        assert "metering" in result_dict

    def test_artifact_envelope_structure(self):
        """Verify Artifact envelope has required fields for charts/files."""
        from shared.modules.output_contract import Artifact

        artifact = Artifact(
            type="chart",
            mime_type="image/png",
            name="temperature_chart.png",
            bytes="base64encodeddata==",
            sha256="abc123",
            size=1024,
        )

        assert artifact.type == "chart"
        assert artifact.mime_type == "image/png"
        assert artifact.sha256 == "abc123"
        assert artifact.size == 1024
