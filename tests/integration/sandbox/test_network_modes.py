"""
Integration tests for network mode enforcement.

Tests network policy configuration and logging (enforcement is container-level).
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sandbox_service.policy import (
    NetworkPolicy, NetworkMode, ExecutionPolicy,
    ImportPolicy, ResourcePolicy
)
from sandbox_service.runner import SandboxRunner, NetworkViolation


class TestNetworkPolicyConfiguration:
    """Test network policy configuration and domain checking."""

    def test_default_mode_blocks_all_domains(self):
        """Default network policy blocks all domains."""
        policy = NetworkPolicy.default()
        assert policy.mode == NetworkMode.BLOCKED
        assert not policy.is_domain_allowed("api.github.com")
        assert not policy.is_domain_allowed("google.com")

    def test_integration_mode_with_allowlist(self):
        """Integration mode allows only listed domains."""
        policy = NetworkPolicy.integration(["api.github.com", "api.stripe.com"])
        assert policy.mode == NetworkMode.INTEGRATION
        assert policy.is_domain_allowed("api.github.com")
        assert policy.is_domain_allowed("api.stripe.com")
        assert not policy.is_domain_allowed("evil.com")
        assert not policy.is_domain_allowed("google.com")

    def test_blocked_domains_never_allowed(self):
        """Blocked domains (localhost, private IPs) are never allowed."""
        policy = NetworkPolicy.integration([
            "localhost",
            "127.0.0.1",
            "192.168.1.1",
            "api.example.com"
        ])
        # api.example.com should be allowed
        assert policy.is_domain_allowed("api.example.com")
        # But blocked domains should not be allowed even if in allowlist
        assert not policy.is_domain_allowed("localhost")
        assert not policy.is_domain_allowed("127.0.0.1")
        assert not policy.is_domain_allowed("192.168.1.1")


class TestNetworkModeInExecutionPolicy:
    """Test network mode integration with ExecutionPolicy."""

    def test_default_execution_policy_has_blocked_network(self):
        """Default execution policy has network blocked."""
        policy = ExecutionPolicy.default()
        assert policy.network.mode == NetworkMode.BLOCKED

    def test_module_validation_without_domains_blocks_network(self):
        """Module validation without domains has network blocked."""
        policy = ExecutionPolicy.module_validation()
        assert policy.network.mode == NetworkMode.BLOCKED

    def test_module_validation_with_domains_enables_integration(self):
        """Module validation with domains enables integration mode."""
        policy = ExecutionPolicy.module_validation(allowed_domains=["api.example.com"])
        assert policy.network.mode == NetworkMode.INTEGRATION
        assert policy.network.is_domain_allowed("api.example.com")

    def test_integration_test_policy_has_network_allowlist(self):
        """Integration test policy has network with allowlist."""
        policy = ExecutionPolicy.integration_test(["api.github.com", "api.stripe.com"])
        assert policy.network.mode == NetworkMode.INTEGRATION
        assert policy.network.is_domain_allowed("api.github.com")
        assert policy.network.is_domain_allowed("api.stripe.com")


class TestNetworkModeLogging:
    """Test that network mode is logged in execution results."""

    def test_network_mode_in_resource_usage(self):
        """Network mode is included in resource usage metrics."""
        policy = ExecutionPolicy.default()
        runner = SandboxRunner(policy)
        code = """
print("Hello world")
"""
        result = runner.execute(code)
        assert "network_mode" in result.resource_usage
        assert result.resource_usage["network_mode"] == "blocked"

    def test_integration_mode_logged(self):
        """Integration mode is logged in resource usage."""
        policy = ExecutionPolicy.integration_test(["api.example.com"])
        runner = SandboxRunner(policy)
        code = """
print("Test")
"""
        result = runner.execute(code)
        assert result.resource_usage["network_mode"] == "integration"

    def test_network_violations_list_exists(self):
        """Network violations list exists in execution result."""
        policy = ExecutionPolicy.default()
        runner = SandboxRunner(policy)
        code = """
# In production, this would attempt a connection and be logged
print("Code that would try network access")
"""
        result = runner.execute(code)
        # network_violations list should exist (even if empty in this test)
        assert hasattr(result, "network_violations")
        assert isinstance(result.network_violations, list)


class TestNetworkViolationStructure:
    """Test NetworkViolation data structure."""

    def test_network_violation_creation(self):
        """NetworkViolation can be created with required fields."""
        violation = NetworkViolation(
            host="evil.com",
            blocked=True,
            reason="Domain not in allowlist"
        )
        assert violation.host == "evil.com"
        assert violation.blocked == True
        assert violation.reason == "Domain not in allowlist"

    def test_network_violation_in_result_dict(self):
        """NetworkViolation is included in ExecutionResult.to_dict()."""
        from sandbox_service.runner import ExecutionResult
        result = ExecutionResult(exit_code=0)
        result.network_violations = [
            NetworkViolation(host="api.example.com", blocked=False, reason="Allowed"),
            NetworkViolation(host="evil.com", blocked=True, reason="Not in allowlist")
        ]
        result_dict = result.to_dict()
        assert "network_violations" in result_dict
        assert len(result_dict["network_violations"]) == 2
        assert result_dict["network_violations"][0]["host"] == "api.example.com"
        assert result_dict["network_violations"][1]["blocked"] == True


class TestProductionNetworkEnforcement:
    """
    Document production network enforcement approach.

    These tests document the expected production behavior, even though
    the current in-process runner doesn't enforce network restrictions.
    """

    def test_production_blocked_mode_approach(self):
        """
        Document: In production, blocked mode uses container isolation.

        Expected production implementation:
        - Docker/podman run with --network=none
        - All outbound connections fail immediately
        - DNS resolution disabled
        - Connection attempts logged for audit
        """
        policy = ExecutionPolicy.default()
        assert policy.network.mode == NetworkMode.BLOCKED
        # In production: container starts with --network=none
        # Any socket.connect() or urllib/requests call would raise ConnectionError

    def test_production_integration_mode_approach(self):
        """
        Document: In production, integration mode uses iptables/firewall.

        Expected production implementation:
        - Container starts with custom network
        - iptables rules whitelist specific domains
        - DNS filtering to prevent domain bypass
        - All connection attempts logged (allowed and blocked)
        - Blocked attempts return clear error (not timeout)
        """
        policy = ExecutionPolicy.integration_test(["api.github.com"])
        assert policy.network.mode == NetworkMode.INTEGRATION
        assert policy.network.is_domain_allowed("api.github.com")
        assert not policy.network.is_domain_allowed("evil.com")
        # In production: iptables rules like:
        # iptables -A OUTPUT -d api.github.com -j ACCEPT
        # iptables -A OUTPUT -j REJECT --reject-with icmp-host-prohibited

    def test_production_dns_resolution_control(self):
        """
        Document: In production, DNS resolution is controlled.

        Expected production implementation:
        - Custom /etc/resolv.conf in container
        - DNS server that only resolves allowed domains
        - Prevents IP-based domain bypass
        """
        policy = NetworkPolicy.integration(["api.example.com"])
        # In production: DNS server returns NXDOMAIN for non-allowed domains
        # Prevents bypassing domain check by using IP directly

    def test_production_connection_logging(self):
        """
        Document: In production, all connection attempts are logged.

        Expected production implementation:
        - Netfilter logging for blocked connections
        - Application-level logging for allowed connections
        - Audit trail includes: timestamp, destination, protocol, allowed/blocked
        """
        policy = NetworkPolicy.integration(["api.example.com"])
        assert policy.log_attempts == True
        # In production: logs would look like:
        # [2026-02-15T00:30:00Z] ALLOW tcp api.example.com:443 (policy: integration)
        # [2026-02-15T00:30:01Z] BLOCK tcp evil.com:80 (policy: integration, reason: not in allowlist)


class TestConnectionTimeouts:
    """Test connection timeout configuration."""

    def test_network_policy_has_connection_timeout(self):
        """NetworkPolicy includes connection timeout setting."""
        policy = NetworkPolicy.default()
        assert hasattr(policy, "connection_timeout_ms")
        assert policy.connection_timeout_ms > 0

    def test_connection_timeout_configurable(self):
        """Connection timeout can be configured."""
        policy = NetworkPolicy(
            mode=NetworkMode.INTEGRATION,
            allowed_domains={"api.example.com"},
            connection_timeout_ms=10000  # 10 seconds
        )
        assert policy.connection_timeout_ms == 10000

    def test_short_timeout_for_blocked_domains(self):
        """
        In production, blocked domains should fail fast, not timeout.

        Expected: Connection to blocked domain returns error immediately
        (e.g., Connection refused) rather than timing out.
        """
        policy = NetworkPolicy.integration(["api.example.com"])
        # In production: iptables REJECT returns error in <1ms
        # Not: TCP timeout after 30+ seconds
        assert policy.connection_timeout_ms == 5000  # Still have timeout as failsafe
