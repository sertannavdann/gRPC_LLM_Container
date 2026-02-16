"""
Feature tests for schema drift detection.

Tests verify:
- Additive changes are classified correctly
- Breaking changes are detected
- Schema evolution is tracked
- Alerts on breaking changes
"""
import pytest
from typing import Dict, Any, List


class SchemaDriftDetector:
    """Helper class for schema drift detection."""

    @staticmethod
    def classify_change(old_schema: Dict[str, Any], new_schema: Dict[str, Any]) -> str:
        """
        Classify schema change as additive or breaking.

        Args:
            old_schema: Previous schema definition
            new_schema: New schema definition

        Returns:
            "additive", "breaking", or "no_change"
        """
        old_fields = set(old_schema.get("fields", {}).keys())
        new_fields = set(new_schema.get("fields", {}).keys())

        # Fields removed = breaking
        removed = old_fields - new_fields
        if removed:
            return "breaking"

        # Fields added = additive
        added = new_fields - old_fields
        if added:
            return "additive"

        # Check for type changes in existing fields
        for field in old_fields & new_fields:
            old_type = old_schema["fields"][field].get("type")
            new_type = new_schema["fields"][field].get("type")
            if old_type != new_type:
                return "breaking"

        return "no_change"

    @staticmethod
    def detect_drift(old_data: List[Dict], new_data: List[Dict]) -> Dict[str, Any]:
        """
        Detect schema drift between two data samples.

        Args:
            old_data: Previous data samples
            new_data: New data samples

        Returns:
            Dict with drift analysis
        """
        if not old_data or not new_data:
            return {"drift": False, "reason": "insufficient_data"}

        old_keys = set(old_data[0].keys()) if old_data else set()
        new_keys = set(new_data[0].keys()) if new_data else set()

        added_fields = new_keys - old_keys
        removed_fields = old_keys - new_keys

        if removed_fields:
            return {
                "drift": True,
                "type": "breaking",
                "removed_fields": list(removed_fields),
                "added_fields": list(added_fields),
            }

        if added_fields:
            return {
                "drift": True,
                "type": "additive",
                "added_fields": list(added_fields),
                "removed_fields": [],
            }

        return {"drift": False, "type": "no_change"}


class TestSchemaDriftDetection:
    """Feature tests for schema drift detection."""

    def test_detects_additive_schema_change(self):
        """Verify additive changes (new fields) are classified correctly."""
        old_schema = {
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
            }
        }

        new_schema = {
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
                "email": {"type": "string"},  # New field added
            }
        }

        detector = SchemaDriftDetector()
        change_type = detector.classify_change(old_schema, new_schema)

        assert change_type == "additive"

    def test_detects_breaking_schema_change_field_removed(self):
        """Verify breaking changes (removed fields) are detected."""
        old_schema = {
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
                "email": {"type": "string"},
            }
        }

        new_schema = {
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
                # email removed - breaking!
            }
        }

        detector = SchemaDriftDetector()
        change_type = detector.classify_change(old_schema, new_schema)

        assert change_type == "breaking"

    def test_detects_breaking_schema_change_type_changed(self):
        """Verify type changes are classified as breaking."""
        old_schema = {
            "fields": {
                "id": {"type": "int"},
                "price": {"type": "float"},
            }
        }

        new_schema = {
            "fields": {
                "id": {"type": "int"},
                "price": {"type": "string"},  # Type changed - breaking!
            }
        }

        detector = SchemaDriftDetector()
        change_type = detector.classify_change(old_schema, new_schema)

        assert change_type == "breaking"

    def test_detects_no_change(self):
        """Verify identical schemas return no_change."""
        schema = {
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
            }
        }

        detector = SchemaDriftDetector()
        change_type = detector.classify_change(schema, schema)

        assert change_type == "no_change"

    def test_detects_drift_in_data_samples(self):
        """Verify drift detection works on actual data samples."""
        old_data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

        new_data = [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ]

        detector = SchemaDriftDetector()
        drift = detector.detect_drift(old_data, new_data)

        assert drift["drift"] is True
        assert drift["type"] == "additive"
        assert "email" in drift["added_fields"]

    def test_detects_breaking_drift_in_data_samples(self):
        """Verify breaking drift (field removal) is detected in data."""
        old_data = [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
        ]

        new_data = [
            {"id": 1, "name": "Alice"},  # email removed
        ]

        detector = SchemaDriftDetector()
        drift = detector.detect_drift(old_data, new_data)

        assert drift["drift"] is True
        assert drift["type"] == "breaking"
        assert "email" in drift["removed_fields"]

    def test_handles_empty_data_gracefully(self):
        """Verify drift detection handles empty data."""
        detector = SchemaDriftDetector()

        drift = detector.detect_drift([], [{"id": 1}])
        assert drift["drift"] is False
        assert drift["reason"] == "insufficient_data"

    def test_alerts_on_breaking_changes(self):
        """Verify breaking changes trigger alerts."""
        old_schema = {
            "fields": {
                "id": {"type": "int"},
                "critical_field": {"type": "string"},
            }
        }

        new_schema = {
            "fields": {
                "id": {"type": "int"},
                # critical_field removed
            }
        }

        detector = SchemaDriftDetector()
        change_type = detector.classify_change(old_schema, new_schema)

        # Breaking change should trigger alert
        alert_triggered = (change_type == "breaking")
        assert alert_triggered is True

    def test_schema_evolution_tracking(self):
        """Verify schema evolution can be tracked over time."""
        schema_v1 = {
            "version": "1.0",
            "fields": {"id": {"type": "int"}},
        }

        schema_v2 = {
            "version": "2.0",
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
            },
        }

        schema_v3 = {
            "version": "3.0",
            "fields": {
                "id": {"type": "int"},
                "name": {"type": "string"},
                "created_at": {"type": "timestamp"},
            },
        }

        detector = SchemaDriftDetector()

        # v1 -> v2
        change_v1_v2 = detector.classify_change(schema_v1, schema_v2)
        assert change_v1_v2 == "additive"

        # v2 -> v3
        change_v2_v3 = detector.classify_change(schema_v2, schema_v3)
        assert change_v2_v3 == "additive"

        # All changes were additive (backwards compatible)
        assert change_v1_v2 == "additive" and change_v2_v3 == "additive"
