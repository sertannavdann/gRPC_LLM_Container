"""Unit tests for manifest_schema.json validation."""
import json
import pytest
from jsonschema import validate, ValidationError
from pathlib import Path


@pytest.fixture
def schema():
    """Load the manifest schema."""
    schema_path = Path(__file__).parent.parent.parent.parent / "shared" / "modules" / "manifest_schema.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def valid_manifest():
    """A valid manifest that should pass validation."""
    return {
        "module_id": "weather/openweather",
        "version": "1.0.0",
        "category": "weather",
        "platform": "openweather",
        "entrypoint": "OpenWeatherAdapter",
        "capabilities": ["current_weather", "forecast"]
    }


@pytest.fixture
def full_manifest():
    """A manifest with all optional fields populated."""
    return {
        "module_id": "finance/stripe",
        "version": "2.1.3",
        "category": "finance",
        "platform": "stripe",
        "entrypoint": "StripeAdapter",
        "capabilities": ["transactions", "balance"],
        "description": "Stripe payment and billing integration",
        "auth": {
            "type": "api_key",
            "required_credentials": ["api_key", "webhook_secret"]
        },
        "pagination": {
            "supported": True,
            "type": "cursor",
            "max_page_size": 100
        },
        "rate_limits": {
            "requests_per_minute": 100,
            "requests_per_hour": 5000,
            "burst": 10
        },
        "outputs": {
            "schema_ref": "FinancialTransaction",
            "mime_types": ["application/json"]
        },
        "artifacts": {
            "produces": ["chart", "report"]
        }
    }


class TestManifestSchemaValid:
    """Test that valid manifests pass validation."""

    def test_minimal_valid_manifest(self, schema, valid_manifest):
        """Test that a minimal valid manifest passes."""
        validate(instance=valid_manifest, schema=schema)

    def test_full_valid_manifest(self, schema, full_manifest):
        """Test that a manifest with all optional fields passes."""
        validate(instance=full_manifest, schema=schema)

    def test_version_has_dollar_id(self, schema):
        """Test that schema has a versioned $id for evolution tracking."""
        assert "$id" in schema
        assert "v1.0.0" in schema["$id"]
        assert schema["$id"].startswith("https://")


class TestManifestSchemaMissingRequired:
    """Test that missing required fields are rejected."""

    def test_missing_module_id(self, schema, valid_manifest):
        """Test that missing module_id is rejected."""
        del valid_manifest["module_id"]
        with pytest.raises(ValidationError, match="'module_id' is a required property"):
            validate(instance=valid_manifest, schema=schema)

    def test_missing_version(self, schema, valid_manifest):
        """Test that missing version is rejected."""
        del valid_manifest["version"]
        with pytest.raises(ValidationError, match="'version' is a required property"):
            validate(instance=valid_manifest, schema=schema)

    def test_missing_category(self, schema, valid_manifest):
        """Test that missing category is rejected."""
        del valid_manifest["category"]
        with pytest.raises(ValidationError, match="'category' is a required property"):
            validate(instance=valid_manifest, schema=schema)

    def test_missing_platform(self, schema, valid_manifest):
        """Test that missing platform is rejected."""
        del valid_manifest["platform"]
        with pytest.raises(ValidationError, match="'platform' is a required property"):
            validate(instance=valid_manifest, schema=schema)

    def test_missing_entrypoint(self, schema, valid_manifest):
        """Test that missing entrypoint is rejected."""
        del valid_manifest["entrypoint"]
        with pytest.raises(ValidationError, match="'entrypoint' is a required property"):
            validate(instance=valid_manifest, schema=schema)

    def test_missing_capabilities(self, schema, valid_manifest):
        """Test that missing capabilities is rejected."""
        del valid_manifest["capabilities"]
        with pytest.raises(ValidationError, match="'capabilities' is a required property"):
            validate(instance=valid_manifest, schema=schema)


class TestManifestSchemaUnknownFields:
    """Test that unknown fields are rejected (additionalProperties: false)."""

    def test_unknown_field_rejected(self, schema, valid_manifest):
        """Test that unknown fields are rejected."""
        valid_manifest["unknown_field"] = "should fail"
        with pytest.raises(ValidationError, match="Additional properties are not allowed"):
            validate(instance=valid_manifest, schema=schema)

    def test_typo_in_field_name(self, schema, valid_manifest):
        """Test that a typo in field name causes validation failure."""
        valid_manifest["desciption"] = "typo in description"  # Should be 'description'
        with pytest.raises(ValidationError, match="Additional properties are not allowed"):
            validate(instance=valid_manifest, schema=schema)


class TestManifestSchemaVersionFormat:
    """Test version format enforcement."""

    def test_valid_semver_versions(self, schema, valid_manifest):
        """Test that valid semantic versions pass."""
        valid_versions = ["0.0.1", "1.0.0", "2.5.13", "10.20.30"]
        for version in valid_versions:
            valid_manifest["version"] = version
            validate(instance=valid_manifest, schema=schema)

    def test_invalid_semver_rejected(self, schema, valid_manifest):
        """Test that invalid semantic versions are rejected."""
        invalid_versions = ["1.0", "v1.0.0", "1.0.0-beta", "1.0.0.0", "latest"]
        for version in invalid_versions:
            valid_manifest["version"] = version
            with pytest.raises(ValidationError):
                validate(instance=valid_manifest, schema=schema)


class TestManifestSchemaModuleIdFormat:
    """Test module_id format enforcement."""

    def test_valid_module_ids(self, schema, valid_manifest):
        """Test that valid module_id formats pass."""
        valid_ids = ["weather/openweather", "finance/stripe", "test/hello", "social_media/twitter_v2"]
        for module_id in valid_ids:
            valid_manifest["module_id"] = module_id
            validate(instance=valid_manifest, schema=schema)

    def test_invalid_module_ids(self, schema, valid_manifest):
        """Test that invalid module_id formats are rejected."""
        invalid_ids = ["weather", "weather/", "/openweather", "Weather/OpenWeather", "weather-api/openweather"]
        for module_id in invalid_ids:
            valid_manifest["module_id"] = module_id
            with pytest.raises(ValidationError):
                validate(instance=valid_manifest, schema=schema)


class TestManifestSchemaCapabilities:
    """Test capabilities array validation."""

    def test_empty_capabilities_rejected(self, schema, valid_manifest):
        """Test that empty capabilities array is rejected."""
        valid_manifest["capabilities"] = []
        with pytest.raises(ValidationError, match="should be non-empty"):
            validate(instance=valid_manifest, schema=schema)

    def test_capabilities_with_invalid_chars(self, schema, valid_manifest):
        """Test that capabilities with invalid characters are rejected."""
        valid_manifest["capabilities"] = ["current-weather"]  # Hyphens not allowed
        with pytest.raises(ValidationError):
            validate(instance=valid_manifest, schema=schema)


class TestManifestSchemaAuthField:
    """Test auth field validation."""

    def test_valid_auth_types(self, schema, valid_manifest):
        """Test that valid auth types pass."""
        valid_auth_types = ["none", "api_key", "oauth2", "basic"]
        for auth_type in valid_auth_types:
            valid_manifest["auth"] = {"type": auth_type}
            validate(instance=valid_manifest, schema=schema)

    def test_invalid_auth_type(self, schema, valid_manifest):
        """Test that invalid auth type is rejected."""
        valid_manifest["auth"] = {"type": "jwt"}  # Not in enum
        with pytest.raises(ValidationError):
            validate(instance=valid_manifest, schema=schema)

    def test_auth_with_credentials(self, schema, valid_manifest):
        """Test that auth with credentials passes."""
        valid_manifest["auth"] = {
            "type": "api_key",
            "required_credentials": ["api_key", "secret"]
        }
        validate(instance=valid_manifest, schema=schema)


class TestManifestSchemaDeterminism:
    """Test that schema validation is deterministic."""

    def test_same_manifest_validates_consistently(self, schema, valid_manifest):
        """Test that the same manifest validates the same way multiple times."""
        for _ in range(10):
            validate(instance=valid_manifest, schema=schema)

    def test_invalid_manifest_fails_consistently(self, schema, valid_manifest):
        """Test that an invalid manifest fails consistently."""
        del valid_manifest["module_id"]
        for _ in range(10):
            with pytest.raises(ValidationError):
                validate(instance=valid_manifest, schema=schema)
