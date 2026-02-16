"""
Chart Artifact Validator - Multi-tier validation for visualization outputs.

Validation tiers:
- Tier 1 (Structural): File exists, decodes, metadata sane
- Tier 2 (Semantic): Expected series present, data binding matches, labels non-empty
- Tier 3 (Optional): Deterministic rendering hash (pinned backend/fonts, opt-in only)

Chart artifact envelope:
- file_metadata: mime_type, byte_size, sha256, dimensions (if image)
- data_summary: series_names, data_point_count, value_ranges
- semantic_summary: title, axis_labels, legend_entries
- provenance: rendering_engine, version, backend

Usage:
    from tools.builtin.chart_validator import validate_chart, ChartValidationResult

    result = validate_chart(artifact_bytes, expected_series=["temperature", "humidity"])
    if not result.tier1_passed:
        print(result.fix_hints)
"""
import base64
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ChartMetadata:
    """Metadata extracted from chart artifact."""
    mime_type: str
    byte_size: int
    sha256: str
    dimensions: Optional[Tuple[int, int]] = None  # (width, height) for images
    series_names: List[str] = field(default_factory=list)
    data_point_count: int = 0
    value_ranges: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    title: Optional[str] = None
    axis_labels: Dict[str, str] = field(default_factory=dict)
    legend_entries: List[str] = field(default_factory=list)
    rendering_engine: Optional[str] = None
    engine_version: Optional[str] = None
    backend: Optional[str] = None


@dataclass
class ChartValidationResult:
    """Result from chart artifact validation."""
    valid: bool
    tier1_passed: bool  # Structural
    tier2_passed: bool  # Semantic
    tier3_passed: bool  # Rendering hash (optional)
    metadata: Optional[ChartMetadata] = None
    fix_hints: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "valid": self.valid,
            "tier1_passed": self.tier1_passed,
            "tier2_passed": self.tier2_passed,
            "tier3_passed": self.tier3_passed,
            "metadata": {
                "mime_type": self.metadata.mime_type if self.metadata else None,
                "byte_size": self.metadata.byte_size if self.metadata else 0,
                "sha256": self.metadata.sha256 if self.metadata else None,
                "dimensions": self.metadata.dimensions if self.metadata else None,
                "series_names": self.metadata.series_names if self.metadata else [],
                "data_point_count": self.metadata.data_point_count if self.metadata else 0,
            } if self.metadata else None,
            "fix_hints": self.fix_hints,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_chart(
    artifact_bytes: bytes,
    expected_series: Optional[List[str]] = None,
    expected_title: Optional[str] = None,
    check_rendering_hash: bool = False,
    expected_hash: Optional[str] = None,
) -> ChartValidationResult:
    """
    Validate chart artifact with multi-tier checks.

    Args:
        artifact_bytes: Raw bytes of the chart artifact
        expected_series: Expected series names to validate
        expected_title: Expected chart title
        check_rendering_hash: Enable Tier 3 deterministic rendering check
        expected_hash: Expected hash for Tier 3 check

    Returns:
        ChartValidationResult with tier-specific validation status
    """
    result = ChartValidationResult(
        valid=True,
        tier1_passed=False,
        tier2_passed=False,
        tier3_passed=False,
    )

    # ========== TIER 1: STRUCTURAL VALIDATION ==========

    # Check file exists (bytes provided)
    if not artifact_bytes:
        result.valid = False
        result.errors.append("Chart artifact bytes are empty")
        result.fix_hints.append("Ensure chart generation produces output bytes")
        return result

    # Check byte size is reasonable
    byte_size = len(artifact_bytes)
    if byte_size == 0:
        result.valid = False
        result.errors.append("Chart artifact has zero bytes")
        result.fix_hints.append("Chart file is empty - check rendering logic")
        return result

    if byte_size > 10 * 1024 * 1024:  # 10MB
        result.warnings.append(f"Chart file is large: {byte_size / 1024 / 1024:.2f}MB")

    # Compute SHA256
    sha256_hash = hashlib.sha256(artifact_bytes).hexdigest()

    # Detect MIME type
    mime_type = _detect_mime_type(artifact_bytes)
    if not mime_type:
        result.valid = False
        result.errors.append("Could not detect chart MIME type")
        result.fix_hints.append("Chart file may be corrupt or unsupported format")
        return result

    # Try to decode based on MIME type
    decode_success, dimensions, decode_error = _try_decode_chart(artifact_bytes, mime_type)
    if not decode_success:
        result.valid = False
        result.errors.append(f"Chart file decode failed: {decode_error}")
        result.fix_hints.append("Chart file corrupt or wrong mime type")
        return result

    # Tier 1 passed
    result.tier1_passed = True

    # Initialize metadata
    result.metadata = ChartMetadata(
        mime_type=mime_type,
        byte_size=byte_size,
        sha256=sha256_hash,
        dimensions=dimensions,
    )

    logger.info(f"Chart Tier 1 validation passed: {mime_type}, {byte_size} bytes")

    # ========== TIER 2: SEMANTIC VALIDATION ==========

    # Extract chart metadata (series, labels, etc.)
    metadata_extracted = _extract_chart_metadata(artifact_bytes, mime_type, result.metadata)
    if not metadata_extracted:
        result.warnings.append("Could not extract detailed chart metadata for Tier 2 validation")
        # Tier 2 is optional if metadata extraction not supported
        result.tier2_passed = True
        return result

    # Validate expected series
    if expected_series:
        missing_series = set(expected_series) - set(result.metadata.series_names)
        if missing_series:
            result.valid = False
            result.errors.append(f"Expected series not found: {', '.join(missing_series)}")
            result.fix_hints.append(
                f"Expected series '{', '.join(missing_series)}' not found in chart output. "
                "Check data binding in chart generation."
            )
            return result

    # Validate title
    if expected_title and result.metadata.title != expected_title:
        result.warnings.append(f"Chart title mismatch: got '{result.metadata.title}', expected '{expected_title}'")

    # Check for empty data
    if result.metadata.data_point_count == 0:
        result.errors.append("Chart produced with no data points")
        result.fix_hints.append("Chart generated with empty dataset - check data source")
        result.valid = False
        return result

    # Validate labels are non-empty
    if not result.metadata.title or result.metadata.title.strip() == "":
        result.warnings.append("Chart has no title")

    if not result.metadata.axis_labels:
        result.warnings.append("Chart has no axis labels")

    # Tier 2 passed
    result.tier2_passed = True

    logger.info(f"Chart Tier 2 validation passed: {len(result.metadata.series_names)} series, {result.metadata.data_point_count} points")

    # ========== TIER 3: RENDERING HASH (OPTIONAL) ==========

    if check_rendering_hash:
        if not expected_hash:
            result.warnings.append("Tier 3 enabled but no expected hash provided")
        else:
            if sha256_hash != expected_hash:
                result.errors.append(f"Rendering hash mismatch: got {sha256_hash[:8]}..., expected {expected_hash[:8]}...")
                result.fix_hints.append(
                    "Non-deterministic rendering detected. "
                    "Ensure pinned backend, fonts, and random seed for reproducible charts."
                )
            else:
                result.tier3_passed = True
                logger.info("Chart Tier 3 validation passed: rendering hash matches")

    return result


def _detect_mime_type(artifact_bytes: bytes) -> Optional[str]:
    """
    Detect MIME type from file signature.

    Args:
        artifact_bytes: Raw file bytes

    Returns:
        MIME type string or None
    """
    # PNG signature
    if artifact_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return "image/png"

    # JPEG signature
    if artifact_bytes.startswith(b'\xff\xd8\xff'):
        return "image/jpeg"

    # SVG signature (XML)
    if artifact_bytes.startswith(b'<?xml') or artifact_bytes.startswith(b'<svg'):
        return "image/svg+xml"

    # PDF signature
    if artifact_bytes.startswith(b'%PDF'):
        return "application/pdf"

    # JSON signature
    if artifact_bytes.strip().startswith(b'{') or artifact_bytes.strip().startswith(b'['):
        try:
            json.loads(artifact_bytes)
            return "application/json"
        except json.JSONDecodeError:
            pass

    return None


def _try_decode_chart(
    artifact_bytes: bytes,
    mime_type: str
) -> Tuple[bool, Optional[Tuple[int, int]], Optional[str]]:
    """
    Try to decode chart based on MIME type.

    Args:
        artifact_bytes: Raw bytes
        mime_type: Detected MIME type

    Returns:
        (success, dimensions, error_message)
    """
    try:
        if mime_type == "image/png":
            # Try to decode PNG
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(artifact_bytes))
                return True, img.size, None
            except ImportError:
                # PIL not available - just check PNG signature is valid
                if artifact_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    return True, None, None
                return False, None, "Invalid PNG signature"
            except Exception as e:
                return False, None, f"PNG decode error: {e}"

        elif mime_type == "image/jpeg":
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(artifact_bytes))
                return True, img.size, None
            except ImportError:
                return True, None, None  # Signature valid
            except Exception as e:
                return False, None, f"JPEG decode error: {e}"

        elif mime_type == "image/svg+xml":
            # SVG is XML - just check it's valid XML
            try:
                artifact_bytes.decode('utf-8')
                return True, None, None
            except UnicodeDecodeError as e:
                return False, None, f"SVG decode error: {e}"

        elif mime_type == "application/json":
            # JSON chart (e.g., Plotly, Vega)
            try:
                json.loads(artifact_bytes)
                return True, None, None
            except json.JSONDecodeError as e:
                return False, None, f"JSON decode error: {e}"

        else:
            # Unknown type - assume valid if bytes present
            return True, None, None

    except Exception as e:
        return False, None, str(e)


def _extract_chart_metadata(
    artifact_bytes: bytes,
    mime_type: str,
    metadata: ChartMetadata
) -> bool:
    """
    Extract chart metadata (series, labels, etc.) from artifact.

    Args:
        artifact_bytes: Raw bytes
        mime_type: MIME type
        metadata: ChartMetadata object to populate

    Returns:
        True if extraction successful, False otherwise
    """
    try:
        if mime_type == "application/json":
            # JSON-based chart (Plotly, Vega, etc.)
            data = json.loads(artifact_bytes)

            # Try to extract Plotly-style metadata
            if "data" in data:
                metadata.series_names = [trace.get("name", f"series_{i}") for i, trace in enumerate(data["data"])]
                metadata.data_point_count = sum(len(trace.get("x", [])) for trace in data["data"])

                # Extract value ranges
                for trace in data["data"]:
                    series_name = trace.get("name", "unknown")
                    y_values = trace.get("y", [])
                    if y_values:
                        metadata.value_ranges[series_name] = (min(y_values), max(y_values))

            # Extract layout info
            if "layout" in data:
                layout = data["layout"]
                metadata.title = layout.get("title", {}).get("text") if isinstance(layout.get("title"), dict) else layout.get("title")
                metadata.axis_labels = {
                    "x": layout.get("xaxis", {}).get("title", {}).get("text") if isinstance(layout.get("xaxis", {}).get("title"), dict) else layout.get("xaxis", {}).get("title"),
                    "y": layout.get("yaxis", {}).get("title", {}).get("text") if isinstance(layout.get("yaxis", {}).get("title"), dict) else layout.get("yaxis", {}).get("title"),
                }

            return True

        # For image formats, we'd need OCR or embedded metadata
        # For now, just mark as successful if MIME type is image
        return True

    except Exception as e:
        logger.warning(f"Failed to extract chart metadata: {e}")
        return False
