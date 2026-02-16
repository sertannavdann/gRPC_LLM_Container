"""
Scenario Registry - Curated build patterns for module builder regression.

Each scenario defines:
- NL intent: Natural language description of the integration
- Expected adapter shape: Required methods, capabilities, auth type
- Manifest capabilities: Expected manifest.json structure
- Test suite requirements: Which feature tests must pass
- Known edge cases: Common pitfalls and their solutions
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScenarioDefinition:
    """Definition of a curated adapter scenario."""
    id: str
    name: str
    description: str
    nl_intent: str  # Natural language description
    category: str
    auth_type: str
    capabilities: Dict[str, bool] = field(default_factory=dict)
    required_methods: List[str] = field(default_factory=list)
    test_suites: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    example_platforms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nl_intent": self.nl_intent,
            "category": self.category,
            "auth_type": self.auth_type,
            "capabilities": self.capabilities,
            "required_methods": self.required_methods,
            "test_suites": self.test_suites,
            "edge_cases": self.edge_cases,
            "example_platforms": self.example_platforms,
        }


class ScenarioRegistry:
    """
    Registry of curated adapter scenarios.

    Scenarios provide known-good patterns for builder regression testing.
    """

    def __init__(self):
        self.scenarios: Dict[str, ScenarioDefinition] = {}
        self._load_builtin_scenarios()

    def _load_builtin_scenarios(self):
        """Load built-in scenario definitions."""
        # Import scenario definitions
        from . import rest_api, oauth2_flow, paginated_api, file_parser, rate_limited_api

        self.register(rest_api.SCENARIO)
        self.register(oauth2_flow.SCENARIO)
        self.register(paginated_api.SCENARIO)
        self.register(file_parser.SCENARIO)
        self.register(rate_limited_api.SCENARIO)

    def register(self, scenario: ScenarioDefinition):
        """Register a scenario."""
        self.scenarios[scenario.id] = scenario
        logger.info(f"Registered scenario: {scenario.id}")

    def get(self, scenario_id: str) -> Optional[ScenarioDefinition]:
        """Get scenario by ID."""
        return self.scenarios.get(scenario_id)

    def list_all(self) -> List[ScenarioDefinition]:
        """List all registered scenarios."""
        return list(self.scenarios.values())

    def count(self) -> int:
        """Count registered scenarios."""
        return len(self.scenarios)

    def find_by_auth_type(self, auth_type: str) -> List[ScenarioDefinition]:
        """Find scenarios matching auth type."""
        return [s for s in self.scenarios.values() if s.auth_type == auth_type]

    def find_by_capability(self, capability: str) -> List[ScenarioDefinition]:
        """Find scenarios with a specific capability."""
        return [s for s in self.scenarios.values() if s.capabilities.get(capability, False)]


# Global registry instance
_registry = None


def get_scenario_registry() -> ScenarioRegistry:
    """Get the global scenario registry instance."""
    global _registry
    if _registry is None:
        _registry = ScenarioRegistry()
    return _registry


def get_scenario(scenario_id: str) -> Optional[ScenarioDefinition]:
    """Get a scenario by ID (convenience function)."""
    return get_scenario_registry().get(scenario_id)


def list_scenarios() -> List[ScenarioDefinition]:
    """List all scenarios (convenience function)."""
    return get_scenario_registry().list_all()
