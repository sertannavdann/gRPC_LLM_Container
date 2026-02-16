"""
Feature tests for chart artifact validation.

Tests verify:
- Tier 1 (Structural): file exists, decodes, metadata sane
- Tier 2 (Semantic): expected series present, data binding matches, labels non-empty
- Tier 3 (Optional): deterministic rendering hash
- Fix hints are actionable
"""
import pytest
import json
import hashlib
from tools.builtin.chart_validator import validate_chart, ChartValidationResult


class TestChartArtifacts:
    """Feature tests for chart artifact validation at each tier."""

    @pytest.fixture
    def valid_png_bytes(self):
        """Valid PNG file signature (minimal)."""
        # PNG signature + minimal IHDR chunk
        return (
            b'\x89PNG\r\n\x1a\n'  # PNG signature
            b'\x00\x00\x00\rIHDR'  # IHDR chunk
            b'\x00\x00\x00\x10'  # Width: 16
            b'\x00\x00\x00\x10'  # Height: 16
            b'\x08\x02\x00\x00\x00'  # Bit depth, color type, etc.
            b'\x90\x91h6'  # CRC
            b'\x00\x00\x00\x00IEND\xaeB`\x82'  # IEND chunk
        )

    @pytest.fixture
    def invalid_png_bytes(self):
        """Invalid PNG (wrong signature)."""
        return b'\x00\x00\x00\x00NOT_A_PNG'

    @pytest.fixture
    def valid_json_chart(self):
        """Valid JSON chart (Plotly-style)."""
        chart_data = {
            "data": [
                {
                    "name": "temperature",
                    "x": [1, 2, 3, 4, 5],
                    "y": [72, 75, 73, 76, 74],
                    "type": "scatter",
                },
                {
                    "name": "humidity",
                    "x": [1, 2, 3, 4, 5],
                    "y": [45, 50, 48, 52, 49],
                    "type": "scatter",
                }
            ],
            "layout": {
                "title": {"text": "Weather Data"},
                "xaxis": {"title": {"text": "Time"}},
                "yaxis": {"title": {"text": "Value"}},
            }
        }
        return json.dumps(chart_data).encode('utf-8')

    @pytest.fixture
    def empty_data_json_chart(self):
        """JSON chart with no data points."""
        chart_data = {
            "data": [
                {
                    "name": "series1",
                    "x": [],
                    "y": [],
                }
            ],
            "layout": {"title": {"text": "Empty Chart"}},
        }
        return json.dumps(chart_data).encode('utf-8')

    def test_tier1_validates_file_exists(self):
        """Verify Tier 1 rejects empty bytes."""
        result = validate_chart(b'')

        assert not result.valid
        assert not result.tier1_passed
        assert "empty" in result.errors[0].lower()
        assert len(result.fix_hints) > 0

    def test_tier1_validates_mime_type(self, valid_png_bytes):
        """Verify Tier 1 detects MIME type correctly."""
        result = validate_chart(valid_png_bytes)

        assert result.tier1_passed
        assert result.metadata is not None
        assert result.metadata.mime_type == "image/png"

    def test_tier1_validates_decode_success(self, valid_png_bytes):
        """Verify Tier 1 decodes file successfully."""
        result = validate_chart(valid_png_bytes)

        assert result.tier1_passed
        assert result.metadata.byte_size > 0
        assert result.metadata.sha256 is not None

    def test_tier1_rejects_corrupt_file(self, invalid_png_bytes):
        """Verify Tier 1 rejects corrupt files."""
        result = validate_chart(invalid_png_bytes)

        assert not result.tier1_passed
        assert "mime type" in result.errors[0].lower() or "decode" in result.errors[0].lower()

    def test_tier1_computes_sha256(self, valid_json_chart):
        """Verify Tier 1 computes SHA256 hash."""
        result = validate_chart(valid_json_chart)

        assert result.tier1_passed
        assert result.metadata.sha256 is not None

        # Verify hash is correct
        expected_hash = hashlib.sha256(valid_json_chart).hexdigest()
        assert result.metadata.sha256 == expected_hash

    def test_tier2_validates_expected_series(self, valid_json_chart):
        """Verify Tier 2 validates expected series are present."""
        result = validate_chart(
            valid_json_chart,
            expected_series=["temperature", "humidity"]
        )

        assert result.tier1_passed
        assert result.tier2_passed
        assert "temperature" in result.metadata.series_names
        assert "humidity" in result.metadata.series_names

    def test_tier2_detects_missing_series(self, valid_json_chart):
        """Verify Tier 2 detects missing series."""
        result = validate_chart(
            valid_json_chart,
            expected_series=["temperature", "humidity", "pressure"]
        )

        assert result.tier1_passed
        assert not result.valid  # Missing series is a failure
        assert "pressure" in result.errors[0]
        assert "not found" in result.fix_hints[0].lower()

    def test_tier2_validates_data_binding(self, valid_json_chart):
        """Verify Tier 2 validates data point count."""
        result = validate_chart(valid_json_chart)

        assert result.tier1_passed
        assert result.tier2_passed
        assert result.metadata.data_point_count > 0

    def test_tier2_detects_empty_data(self, empty_data_json_chart):
        """Verify Tier 2 detects empty data."""
        result = validate_chart(empty_data_json_chart)

        assert result.tier1_passed
        assert not result.tier2_passed
        assert "no data points" in result.errors[0].lower()
        assert "empty dataset" in result.fix_hints[0].lower()

    def test_tier2_validates_labels_present(self, valid_json_chart):
        """Verify Tier 2 checks for labels."""
        result = validate_chart(valid_json_chart)

        assert result.tier1_passed
        assert result.tier2_passed
        assert result.metadata.title == "Weather Data"
        assert "Time" in str(result.metadata.axis_labels.get("x", ""))

    def test_tier2_warns_on_missing_labels(self):
        """Verify Tier 2 warns when labels are missing."""
        chart_data = {
            "data": [{"name": "series1", "x": [1, 2], "y": [3, 4]}],
            "layout": {},  # No title or axis labels
        }
        chart_bytes = json.dumps(chart_data).encode('utf-8')

        result = validate_chart(chart_bytes)

        assert result.tier1_passed
        # Should warn about missing labels
        assert any("title" in w.lower() for w in result.warnings)

    def test_tier3_validates_rendering_hash(self, valid_json_chart):
        """Verify Tier 3 validates deterministic rendering hash."""
        expected_hash = hashlib.sha256(valid_json_chart).hexdigest()

        result = validate_chart(
            valid_json_chart,
            check_rendering_hash=True,
            expected_hash=expected_hash
        )

        assert result.tier1_passed
        assert result.tier2_passed
        assert result.tier3_passed

    def test_tier3_detects_hash_mismatch(self, valid_json_chart):
        """Verify Tier 3 detects non-deterministic rendering."""
        wrong_hash = "0" * 64

        result = validate_chart(
            valid_json_chart,
            check_rendering_hash=True,
            expected_hash=wrong_hash
        )

        assert result.tier1_passed
        assert result.tier2_passed
        assert not result.tier3_passed
        assert "hash mismatch" in result.errors[-1].lower()
        assert "deterministic" in result.fix_hints[-1].lower()

    def test_fix_hints_for_corrupt_file(self):
        """Verify fix hints are actionable for corrupt files."""
        result = validate_chart(b'INVALID_DATA')

        assert not result.valid
        assert len(result.fix_hints) > 0
        # Fix hint should mention corruption or format
        assert any("corrupt" in hint.lower() or "format" in hint.lower() for hint in result.fix_hints)

    def test_fix_hints_for_missing_series(self):
        """Verify fix hints are actionable for missing series."""
        chart_data = {
            "data": [{"name": "actual", "x": [1], "y": [2]}],
            "layout": {},
        }
        chart_bytes = json.dumps(chart_data).encode('utf-8')

        result = validate_chart(
            chart_bytes,
            expected_series=["expected", "missing"]
        )

        assert not result.valid
        assert len(result.fix_hints) > 0
        # Fix hint should mention the missing series
        assert any("expected" in hint or "missing" in hint for hint in result.fix_hints)

    def test_result_to_dict_serialization(self, valid_json_chart):
        """Verify ChartValidationResult can be serialized to dict."""
        result = validate_chart(valid_json_chart)

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "valid" in result_dict
        assert "tier1_passed" in result_dict
        assert "tier2_passed" in result_dict
        assert "metadata" in result_dict
        assert "fix_hints" in result_dict
