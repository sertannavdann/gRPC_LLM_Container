"""
Cross-feature integration test: Feature test gating.

Verifies that manifest capabilities correctly drive test suite selection,
and chart validation integrates with the artifact envelope.

Components integrated:
- tools/builtin/feature_test_harness.py (select_suites)
- tools/builtin/chart_validator.py (validate_chart)
- shared/modules/output_contract.py (AdapterRunResult, Artifact)
"""
import hashlib
import json
import pytest
from pathlib import Path

from tools.builtin.feature_test_harness import select_suites, FEATURE_SUITES
from tools.builtin.chart_validator import validate_chart, ChartValidationResult
from shared.modules.output_contract import AdapterRunResult, Artifact


class TestFeatureTestGating:

    def test_manifest_auth_type_selects_correct_suites(self):
        """auth_type='api_key' selects auth_api_key; 'oauth2' selects oauth_refresh."""
        manifest_api_key = {
            "auth_type": "api_key",
            "capabilities": {},
        }
        suites = select_suites(manifest_api_key)
        names = [s.name for s in suites]
        assert "auth_api_key" in names
        assert "oauth_refresh" not in names

        manifest_oauth = {
            "auth_type": "oauth2",
            "capabilities": {},
        }
        suites = select_suites(manifest_oauth)
        names = [s.name for s in suites]
        assert "oauth_refresh" in names
        assert "auth_api_key" not in names

    def test_capability_flags_select_additional_suites(self):
        """pagination and rate_limited capabilities add corresponding suites."""
        manifest = {
            "auth_type": "none",
            "capabilities": {
                "pagination": True,
                "rate_limited": True,
            },
        }
        suites = select_suites(manifest)
        names = [s.name for s in suites]
        assert "pagination_cursor" in names
        assert "rate_limit_429" in names

        # Without capabilities: neither selected
        manifest_empty = {
            "auth_type": "none",
            "capabilities": {},
        }
        suites = select_suites(manifest_empty)
        names = [s.name for s in suites]
        assert "pagination_cursor" not in names
        assert "rate_limit_429" not in names

    def test_schema_drift_always_included(self):
        """schema_drift suite selected regardless of manifest capabilities."""
        manifest = {
            "auth_type": "none",
            "capabilities": {},
        }
        suites = select_suites(manifest)
        names = [s.name for s in suites]
        assert "schema_drift" in names
        assert len(suites) == 1  # Only schema_drift

    def test_chart_validation_with_artifact_envelope(self):
        """Chart bytes validated and artifact SHA matches AdapterRunResult."""
        # Minimal valid PNG (8-byte signature + minimal IHDR)
        png_sig = b'\x89PNG\r\n\x1a\n'
        # Full minimal 1x1 PNG
        import struct
        import zlib

        # Build a minimal valid PNG
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr_chunk = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

        # IDAT with minimal image data
        raw_data = zlib.compress(b'\x00\x00\x00\x00')
        idat_crc = zlib.crc32(b'IDAT' + raw_data) & 0xffffffff
        idat_chunk = struct.pack('>I', len(raw_data)) + b'IDAT' + raw_data + struct.pack('>I', idat_crc)

        # IEND
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend_chunk = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)

        png_bytes = png_sig + ihdr_chunk + idat_chunk + iend_chunk

        chart_result = validate_chart(png_bytes)
        assert chart_result.tier1_passed is True

        # Build artifact envelope
        chart_sha = hashlib.sha256(png_bytes).hexdigest()
        artifact = Artifact(
            type="chart",
            mime_type="image/png",
            name="temperature_chart",
            bytes="base64_encoded_data",
            sha256=chart_sha,
            size=len(png_bytes),
        )

        # SHA from chart validator matches artifact envelope
        assert chart_result.metadata is not None
        assert chart_result.metadata.sha256 == artifact.sha256

    def test_chart_artifacts_dashboard_serving_endpoints_exist(self):
        """Dashboard exposes module chart list/get routes."""
        assert callable(validate_chart)

        repo_root = Path(__file__).resolve().parents[3]
        dashboard_source = (repo_root / "dashboard_service" / "main.py").read_text()

        assert "@app.get(\"/modules/{category}/{platform}/charts\"" in dashboard_source
        assert "@app.get(\"/modules/{category}/{platform}/charts/{chart_name}\"" in dashboard_source

    def test_json_chart_metadata_extraction(self):
        """Plotly-style JSON chart has series names and data points extracted."""
        plotly_chart = {
            "data": [
                {
                    "name": "temperature",
                    "x": ["Mon", "Tue", "Wed"],
                    "y": [22, 25, 20],
                    "type": "scatter",
                },
                {
                    "name": "humidity",
                    "x": ["Mon", "Tue", "Wed"],
                    "y": [60, 55, 70],
                    "type": "bar",
                },
            ],
            "layout": {
                "title": "Weather Data",
                "xaxis": {"title": "Day"},
                "yaxis": {"title": "Value"},
            },
        }

        chart_bytes = json.dumps(plotly_chart).encode()
        result = validate_chart(
            chart_bytes,
            expected_series=["temperature", "humidity"],
        )

        assert result.tier1_passed is True
        assert result.tier2_passed is True
        assert result.metadata is not None
        assert "temperature" in result.metadata.series_names
        assert "humidity" in result.metadata.series_names
        assert result.metadata.data_point_count == 6  # 3 + 3
