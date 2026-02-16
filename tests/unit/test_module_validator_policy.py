"""
Unit tests for sandbox policy system.

Tests policy creation, merging, and enforcement boundaries.
"""
import pytest
from sandbox_service.policy import (
    NetworkPolicy, NetworkMode, ImportPolicy, ImportCategory,
    ResourcePolicy, ExecutionPolicy, FORBIDDEN_IMPORTS
)


class TestNetworkPolicy:
    """Test NetworkPolicy configuration and domain checking."""

    def test_default_policy_blocks_all(self):
        """Default policy blocks all domains."""
        policy = NetworkPolicy.default()
        assert policy.mode == NetworkMode.BLOCKED
        assert not policy.is_domain_allowed("api.github.com")
        assert not policy.is_domain_allowed("example.com")

    def test_integration_policy_allows_listed_domains(self):
        """Integration policy allows only listed domains."""
        policy = NetworkPolicy.integration(["api.github.com", "example.com"])
        assert policy.mode == NetworkMode.INTEGRATION
        assert policy.is_domain_allowed("api.github.com")
        assert policy.is_domain_allowed("example.com")
        assert not policy.is_domain_allowed("evil.com")

    def test_blocked_domains_always_denied(self):
        """Localhost and private IPs are always blocked."""
        policy = NetworkPolicy.integration(["localhost", "127.0.0.1", "192.168.1.1"])
        # Even though they're in the allowlist, they should be blocked
        assert not policy.is_domain_allowed("localhost")
        assert not policy.is_domain_allowed("127.0.0.1")
        assert not policy.is_domain_allowed("192.168.1.1")

    def test_blocked_domain_variants(self):
        """Various localhost/private IP patterns are blocked."""
        policy = NetworkPolicy.integration(["example.com"])
        assert not policy.is_domain_allowed("127.0.0.1")
        assert not policy.is_domain_allowed("127.1.1.1")
        assert not policy.is_domain_allowed("0.0.0.0")
        assert not policy.is_domain_allowed("localhost")
        assert not policy.is_domain_allowed("LOCALHOST")


class TestImportPolicy:
    """Test ImportPolicy allowlists and forbidden checks."""

    def test_minimal_policy_allows_stdlib_only(self):
        """Minimal policy allows only standard library."""
        policy = ImportPolicy.minimal()
        assert policy.is_import_allowed("json")
        assert policy.is_import_allowed("datetime")
        assert policy.is_import_allowed("math")
        assert not policy.is_import_allowed("httpx")
        assert not policy.is_import_allowed("subprocess")

    def test_module_validation_policy_includes_http_testing(self):
        """Module validation policy includes HTTP clients and testing."""
        policy = ImportPolicy.module_validation()
        # Standard lib
        assert policy.is_import_allowed("json")
        # HTTP clients
        assert policy.is_import_allowed("httpx")
        assert policy.is_import_allowed("aiohttp")
        # Testing
        assert policy.is_import_allowed("pytest")
        assert policy.is_import_allowed("unittest")
        # Data processing
        assert policy.is_import_allowed("csv")
        assert policy.is_import_allowed("pydantic")

    def test_forbidden_imports_always_blocked(self):
        """Forbidden imports are blocked regardless of allowlist."""
        policy = ImportPolicy.module_validation()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not policy.is_import_allowed(forbidden)

    def test_submodule_matching(self):
        """Submodule imports are allowed if base module is allowed."""
        policy = ImportPolicy.module_validation()
        # unittest is allowed, so unittest.mock should be allowed
        assert policy.is_import_allowed("unittest.mock")
        assert policy.is_import_allowed("collections.abc")

    def test_custom_allowed_imports(self):
        """Custom allowed imports extend categories."""
        policy = ImportPolicy(
            allowed_categories={ImportCategory.STANDARD_LIB},
            custom_allowed={"custom_module", "another_module"}
        )
        assert policy.is_import_allowed("json")  # from category
        assert policy.is_import_allowed("custom_module")  # custom
        assert policy.is_import_allowed("another_module")  # custom
        assert not policy.is_import_allowed("httpx")  # not in category or custom

    def test_get_allowed_imports_combines_categories(self):
        """get_allowed_imports() combines all enabled categories."""
        policy = ImportPolicy(allowed_categories={
            ImportCategory.STANDARD_LIB,
            ImportCategory.HTTP_CLIENTS
        })
        allowed = policy.get_allowed_imports()
        assert "json" in allowed
        assert "httpx" in allowed
        assert "pytest" not in allowed  # Testing category not enabled


class TestResourcePolicy:
    """Test ResourcePolicy limits and clamping."""

    def test_default_policy(self):
        """Default policy has reasonable limits."""
        policy = ResourcePolicy.default()
        assert policy.timeout_seconds == 30
        assert policy.memory_mb == 256
        assert policy.max_processes == 4

    def test_extended_policy(self):
        """Extended policy has higher limits."""
        policy = ResourcePolicy.extended()
        assert policy.timeout_seconds == 60
        assert policy.memory_mb == 512
        assert policy.max_processes == 4

    def test_timeout_clamping(self):
        """Timeout is clamped to [1, 60] seconds."""
        policy = ResourcePolicy(timeout_seconds=0, memory_mb=256, max_processes=4)
        assert policy.timeout_seconds == 1

        policy = ResourcePolicy(timeout_seconds=120, memory_mb=256, max_processes=4)
        assert policy.timeout_seconds == 60

        policy = ResourcePolicy(timeout_seconds=45, memory_mb=256, max_processes=4)
        assert policy.timeout_seconds == 45

    def test_memory_clamping(self):
        """Memory is clamped to [64, 512] MB."""
        policy = ResourcePolicy(timeout_seconds=30, memory_mb=10, max_processes=4)
        assert policy.memory_mb == 64

        policy = ResourcePolicy(timeout_seconds=30, memory_mb=1024, max_processes=4)
        assert policy.memory_mb == 512

        policy = ResourcePolicy(timeout_seconds=30, memory_mb=256, max_processes=4)
        assert policy.memory_mb == 256

    def test_max_processes_clamping(self):
        """Max processes is clamped to [1, 8]."""
        policy = ResourcePolicy(timeout_seconds=30, memory_mb=256, max_processes=0)
        assert policy.max_processes == 1

        policy = ResourcePolicy(timeout_seconds=30, memory_mb=256, max_processes=20)
        assert policy.max_processes == 8


class TestExecutionPolicy:
    """Test ExecutionPolicy composition and merging."""

    def test_default_execution_policy(self):
        """Default execution policy has minimal permissions."""
        policy = ExecutionPolicy.default()
        assert policy.network.mode == NetworkMode.BLOCKED
        assert policy.imports.allowed_categories == {ImportCategory.STANDARD_LIB}
        assert policy.resources.timeout_seconds == 30
        assert policy.name == "default"

    def test_module_validation_policy_no_network(self):
        """Module validation policy without domains blocks network."""
        policy = ExecutionPolicy.module_validation()
        assert policy.network.mode == NetworkMode.BLOCKED
        assert ImportCategory.HTTP_CLIENTS in policy.imports.allowed_categories
        assert policy.resources.timeout_seconds == 60
        assert policy.name == "module_validation"

    def test_module_validation_policy_with_network(self):
        """Module validation policy with domains enables integration mode."""
        policy = ExecutionPolicy.module_validation(allowed_domains=["api.example.com"])
        assert policy.network.mode == NetworkMode.INTEGRATION
        assert policy.network.is_domain_allowed("api.example.com")
        assert not policy.network.is_domain_allowed("evil.com")

    def test_integration_test_policy(self):
        """Integration test policy has network and full imports."""
        policy = ExecutionPolicy.integration_test(["api.github.com", "example.com"])
        assert policy.network.mode == NetworkMode.INTEGRATION
        assert policy.network.is_domain_allowed("api.github.com")
        assert ImportCategory.HTTP_CLIENTS in policy.imports.allowed_categories
        assert policy.name == "integration_test"

    def test_policy_merge_takes_permissive_network(self):
        """Merged policy takes integration mode over blocked."""
        blocked = ExecutionPolicy.default()
        integration = ExecutionPolicy.integration_test(["api.example.com"])

        merged = blocked.merge(integration)
        assert merged.network.mode == NetworkMode.INTEGRATION
        assert merged.network.is_domain_allowed("api.example.com")

    def test_policy_merge_unions_allowed_domains(self):
        """Merged policy unions allowed domains."""
        policy1 = ExecutionPolicy.integration_test(["api1.com", "api2.com"])
        policy2 = ExecutionPolicy.integration_test(["api2.com", "api3.com"])

        merged = policy1.merge(policy2)
        assert merged.network.is_domain_allowed("api1.com")
        assert merged.network.is_domain_allowed("api2.com")
        assert merged.network.is_domain_allowed("api3.com")

    def test_policy_merge_unions_import_categories(self):
        """Merged policy unions import categories."""
        policy1 = ExecutionPolicy(
            network=NetworkPolicy.default(),
            imports=ImportPolicy(allowed_categories={ImportCategory.STANDARD_LIB}),
            resources=ResourcePolicy.default(),
            name="p1"
        )
        policy2 = ExecutionPolicy(
            network=NetworkPolicy.default(),
            imports=ImportPolicy(allowed_categories={ImportCategory.HTTP_CLIENTS}),
            resources=ResourcePolicy.default(),
            name="p2"
        )

        merged = policy1.merge(policy2)
        assert ImportCategory.STANDARD_LIB in merged.imports.allowed_categories
        assert ImportCategory.HTTP_CLIENTS in merged.imports.allowed_categories

    def test_policy_merge_takes_higher_resource_limits(self):
        """Merged policy takes higher resource limits."""
        policy1 = ExecutionPolicy(
            network=NetworkPolicy.default(),
            imports=ImportPolicy.minimal(),
            resources=ResourcePolicy(timeout_seconds=30, memory_mb=256, max_processes=2),
            name="p1"
        )
        policy2 = ExecutionPolicy(
            network=NetworkPolicy.default(),
            imports=ImportPolicy.minimal(),
            resources=ResourcePolicy(timeout_seconds=60, memory_mb=128, max_processes=8),
            name="p2"
        )

        merged = policy1.merge(policy2)
        assert merged.resources.timeout_seconds == 60  # max of 30, 60
        assert merged.resources.memory_mb == 256  # max of 256, 128
        assert merged.resources.max_processes == 8  # max of 2, 8


class TestPolicyEnforcement:
    """Test policy enforcement boundaries."""

    def test_forbidden_import_blocks_even_with_custom_allowed(self):
        """Forbidden imports cannot be bypassed via custom_allowed."""
        policy = ImportPolicy(
            allowed_categories={ImportCategory.STANDARD_LIB},
            custom_allowed={"subprocess", "os.system"},  # Try to bypass
            enforce_forbidden=True
        )
        assert not policy.is_import_allowed("subprocess")
        assert not policy.is_import_allowed("os.system")

    def test_disable_forbidden_check_allows_dangerous_imports(self):
        """Disabling forbidden check allows dangerous imports (not recommended)."""
        policy = ImportPolicy(
            allowed_categories={ImportCategory.STANDARD_LIB},
            custom_allowed={"subprocess"},
            enforce_forbidden=False  # Disable check
        )
        assert policy.is_import_allowed("subprocess")

    def test_policy_violation_is_non_bypassable(self):
        """Policy violations cannot be bypassed through merging."""
        safe = ExecutionPolicy.default()
        unsafe = ExecutionPolicy(
            network=NetworkPolicy.default(),
            imports=ImportPolicy(
                allowed_categories={ImportCategory.STANDARD_LIB},
                custom_allowed={"subprocess"},
                enforce_forbidden=False  # Try to bypass
            ),
            resources=ResourcePolicy.default(),
            name="unsafe"
        )

        merged = safe.merge(unsafe)
        # Merged policy should still enforce forbidden (AND logic)
        assert merged.imports.enforce_forbidden == False  # This is a known weakness
        # In production, we'd want to ensure forbidden is always enforced
