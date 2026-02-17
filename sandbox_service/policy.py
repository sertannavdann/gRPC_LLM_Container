"""
Sandbox policy system for NEXUS module validation.

Provides configurable execution profiles with:
- NetworkPolicy: deny-by-default egress with strict allowlists
- ImportPolicy: category-based import allowlists + forbidden check
- ResourcePolicy: timeout, memory, process limits
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Set, List, Dict, Optional
import re

from shared.modules.security_policy import FORBIDDEN_IMPORTS


class NetworkMode(str, Enum):
    """Network access modes for sandbox execution."""
    BLOCKED = "blocked"  # No external network (default)
    INTEGRATION = "integration"  # Strict domain allowlist only


class ImportCategory(str, Enum):
    """Categories of allowed imports for module building."""
    STANDARD_LIB = "standard_lib"
    HTTP_CLIENTS = "http_clients"
    TESTING = "testing"
    DATA_PROCESSING = "data_processing"


# Import allowlists by category
IMPORT_ALLOWLISTS: Dict[ImportCategory, Set[str]] = {
    ImportCategory.STANDARD_LIB: {
        "math", "random", "datetime", "json", "re", "collections",
        "itertools", "functools", "operator", "string", "decimal",
        "fractions", "statistics", "typing", "dataclasses", "enum",
        "hashlib", "asyncio", "pathlib", "os", "sys", "time"
    },
    ImportCategory.HTTP_CLIENTS: {
        "httpx", "aiohttp", "requests"
    },
    ImportCategory.TESTING: {
        "pytest", "unittest", "unittest.mock"
    },
    ImportCategory.DATA_PROCESSING: {
        "csv", "pydantic"
    }
}

# Blocked domains (always denied even in integration mode)
BLOCKED_DOMAINS: Set[str] = {
    "localhost",
    "127.0.0.1",
    "::1",
    "169.254.0.0/16",  # Link-local
    "10.0.0.0/8",      # Private
    "172.16.0.0/12",   # Private
    "192.168.0.0/16",  # Private
}


@dataclass
class NetworkPolicy:
    """
    Network access policy for sandbox execution.

    Attributes:
        mode: NetworkMode (BLOCKED or INTEGRATION)
        allowed_domains: Set of allowed domains (only for integration mode)
        connection_timeout_ms: Maximum time for connection attempts
        log_attempts: Whether to log all connection attempts
    """
    mode: NetworkMode = NetworkMode.BLOCKED
    allowed_domains: Set[str] = field(default_factory=set)
    connection_timeout_ms: int = 5000
    log_attempts: bool = True

    def is_domain_allowed(self, domain: str) -> bool:
        """
        Check if a domain is allowed under this policy.

        Args:
            domain: Domain to check (e.g., "api.github.com")

        Returns:
            True if domain is allowed, False otherwise
        """
        # Blocked domains are never allowed
        if self._is_blocked_domain(domain):
            return False

        # In blocked mode, nothing is allowed
        if self.mode == NetworkMode.BLOCKED:
            return False

        # In integration mode, check allowlist
        return domain in self.allowed_domains

    def _is_blocked_domain(self, domain: str) -> bool:
        """Check if domain is in the blocked list."""
        # Direct match
        if domain in BLOCKED_DOMAINS:
            return True

        # Check for private IP ranges
        if domain.startswith("127.") or domain.startswith("0."):
            return True
        if domain.startswith("10."):
            return True
        if domain.startswith("192.168."):
            return True
        # 172.16.0.0 - 172.31.255.255
        if domain.startswith("172."):
            try:
                second_octet = int(domain.split(".")[1])
                if 16 <= second_octet <= 31:
                    return True
            except (ValueError, IndexError):
                pass

        # Check for localhost variants
        if "localhost" in domain.lower():
            return True

        return False

    @classmethod
    def default(cls) -> 'NetworkPolicy':
        """Create default policy (blocked)."""
        return cls(mode=NetworkMode.BLOCKED)

    @classmethod
    def integration(cls, allowed_domains: List[str]) -> 'NetworkPolicy':
        """Create integration policy with allowlist."""
        return cls(
            mode=NetworkMode.INTEGRATION,
            allowed_domains=set(allowed_domains)
        )


@dataclass
class ImportPolicy:
    """
    Import restriction policy for sandbox execution.

    Attributes:
        allowed_categories: Set of ImportCategory to enable
        custom_allowed: Additional allowed imports beyond categories
        enforce_forbidden: Whether to check forbidden imports
    """
    allowed_categories: Set[ImportCategory] = field(default_factory=set)
    custom_allowed: Set[str] = field(default_factory=set)
    enforce_forbidden: bool = True

    def get_allowed_imports(self) -> Set[str]:
        """
        Get combined set of allowed imports.

        Returns:
            Set of allowed import module names
        """
        allowed = set()

        # Add category imports
        for category in self.allowed_categories:
            allowed.update(IMPORT_ALLOWLISTS.get(category, set()))

        # Add custom allowed
        allowed.update(self.custom_allowed)

        return allowed

    def is_import_allowed(self, import_name: str) -> bool:
        """
        Check if an import is allowed under this policy.

        Args:
            import_name: Import name to check (e.g., "httpx", "os.system")

        Returns:
            True if import is allowed, False otherwise
        """
        # Check forbidden list first
        if self.enforce_forbidden and import_name in FORBIDDEN_IMPORTS:
            return False

        # Check against allowed set
        allowed = self.get_allowed_imports()

        # Direct match
        if import_name in allowed:
            return True

        # Check for submodule match (e.g., "unittest.mock" matches "unittest")
        base_module = import_name.split('.')[0]
        if base_module in allowed:
            return True

        return False

    @classmethod
    def minimal(cls) -> 'ImportPolicy':
        """Create minimal policy (standard lib only)."""
        return cls(allowed_categories={ImportCategory.STANDARD_LIB})

    @classmethod
    def module_validation(cls) -> 'ImportPolicy':
        """Create policy for module validation (includes HTTP, testing, data)."""
        return cls(allowed_categories={
            ImportCategory.STANDARD_LIB,
            ImportCategory.HTTP_CLIENTS,
            ImportCategory.TESTING,
            ImportCategory.DATA_PROCESSING
        })


@dataclass
class ResourcePolicy:
    """
    Resource limits for sandbox execution.

    Attributes:
        timeout_seconds: Maximum execution time (default 30s, max 60s)
        memory_mb: Maximum memory usage (default 256MB, max 512MB)
        max_processes: Maximum number of processes (default 4)
    """
    timeout_seconds: int = 30
    memory_mb: int = 256
    max_processes: int = 4

    def __post_init__(self):
        """Validate and clamp resource limits."""
        # Clamp timeout
        if self.timeout_seconds < 1:
            self.timeout_seconds = 1
        elif self.timeout_seconds > 60:
            self.timeout_seconds = 60

        # Clamp memory
        if self.memory_mb < 64:
            self.memory_mb = 64
        elif self.memory_mb > 512:
            self.memory_mb = 512

        # Clamp processes
        if self.max_processes < 1:
            self.max_processes = 1
        elif self.max_processes > 8:
            self.max_processes = 8

    @classmethod
    def default(cls) -> 'ResourcePolicy':
        """Create default resource policy."""
        return cls(timeout_seconds=30, memory_mb=256, max_processes=4)

    @classmethod
    def extended(cls) -> 'ResourcePolicy':
        """Create extended resource policy for complex operations."""
        return cls(timeout_seconds=60, memory_mb=512, max_processes=4)


@dataclass
class ExecutionPolicy:
    """
    Combined execution policy profile.

    Bundles network, import, and resource policies into a single profile.
    """
    network: NetworkPolicy
    imports: ImportPolicy
    resources: ResourcePolicy
    name: str = "custom"

    @classmethod
    def default(cls) -> 'ExecutionPolicy':
        """Create default policy (minimal, blocked network)."""
        return cls(
            network=NetworkPolicy.default(),
            imports=ImportPolicy.minimal(),
            resources=ResourcePolicy.default(),
            name="default"
        )

    @classmethod
    def module_validation(cls, allowed_domains: Optional[List[str]] = None) -> 'ExecutionPolicy':
        """
        Create policy for module validation.

        Includes HTTP clients, testing frameworks, data processing.
        Network is blocked by default unless domains provided.
        """
        if allowed_domains:
            network = NetworkPolicy.integration(allowed_domains)
        else:
            network = NetworkPolicy.default()

        return cls(
            network=network,
            imports=ImportPolicy.module_validation(),
            resources=ResourcePolicy.extended(),
            name="module_validation"
        )

    @classmethod
    def integration_test(cls, allowed_domains: List[str]) -> 'ExecutionPolicy':
        """Create policy for integration testing with external APIs."""
        return cls(
            network=NetworkPolicy.integration(allowed_domains),
            imports=ImportPolicy.module_validation(),
            resources=ResourcePolicy.extended(),
            name="integration_test"
        )

    def merge(self, other: 'ExecutionPolicy') -> 'ExecutionPolicy':
        """
        Merge two policies, taking the more permissive settings.

        Args:
            other: Policy to merge with

        Returns:
            New ExecutionPolicy with merged settings
        """
        # Merge network (integration wins over blocked)
        if other.network.mode == NetworkMode.INTEGRATION:
            merged_network = NetworkPolicy(
                mode=NetworkMode.INTEGRATION,
                allowed_domains=self.network.allowed_domains | other.network.allowed_domains,
                connection_timeout_ms=max(
                    self.network.connection_timeout_ms,
                    other.network.connection_timeout_ms
                ),
                log_attempts=self.network.log_attempts or other.network.log_attempts
            )
        else:
            merged_network = self.network

        # Merge imports (union of allowed)
        merged_imports = ImportPolicy(
            allowed_categories=self.imports.allowed_categories | other.imports.allowed_categories,
            custom_allowed=self.imports.custom_allowed | other.imports.custom_allowed,
            enforce_forbidden=self.imports.enforce_forbidden and other.imports.enforce_forbidden
        )

        # Merge resources (take higher limits)
        merged_resources = ResourcePolicy(
            timeout_seconds=max(self.resources.timeout_seconds, other.resources.timeout_seconds),
            memory_mb=max(self.resources.memory_mb, other.resources.memory_mb),
            max_processes=max(self.resources.max_processes, other.resources.max_processes)
        )

        return ExecutionPolicy(
            network=merged_network,
            imports=merged_imports,
            resources=merged_resources,
            name=f"{self.name}+{other.name}"
        )
