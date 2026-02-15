"""
Run-Unit Calculator — normalized compute cost per tool execution.

Formula: max(cpu_seconds, gpu_seconds) * tier_multiplier + tool_overhead

Pure computation module with no external dependencies beyond logging.
"""
import logging

logger = logging.getLogger(__name__)

TIER_MULTIPLIERS = {
    "standard": 1.0,
    "heavy": 1.5,
    "ultra": 3.0,
}

TOOL_OVERHEADS = {
    "default": 0.1,
    "sandbox_execute": 0.2,
    "build_module": 0.5,
    "validate_module": 0.3,
    "install_module": 0.2,
    "write_module_code": 0.3,
}

_MINIMUM_RUN_UNITS = 0.01


class RunUnitCalculator:
    """Computes normalized run-unit cost for tool executions."""

    def calculate(
        self,
        cpu_seconds: float,
        gpu_seconds: float = 0.0,
        tier: str = "standard",
        tool_name: str = "default",
    ) -> float:
        """
        Calculate run units for a single tool execution.

        Returns float rounded to 4 decimal places, with a minimum floor of 0.01.
        """
        multiplier = TIER_MULTIPLIERS.get(tier)
        if multiplier is None:
            logger.warning(f"Unknown tier '{tier}', defaulting to 1.0 multiplier")
            multiplier = 1.0

        overhead = TOOL_OVERHEADS.get(tool_name, TOOL_OVERHEADS["default"])
        raw = max(cpu_seconds, gpu_seconds) * multiplier + overhead
        return round(max(raw, _MINIMUM_RUN_UNITS), 4)

    def calculate_from_latency(
        self,
        latency_ms: float,
        gpu_seconds: float = 0.0,
        tier: str = "standard",
        tool_name: str = "default",
    ) -> float:
        """Convenience: convert latency_ms to cpu_seconds, then calculate."""
        return self.calculate(
            cpu_seconds=latency_ms / 1000.0,
            gpu_seconds=gpu_seconds,
            tier=tier,
            tool_name=tool_name,
        )

    def estimate_request_cost(
        self,
        tool_calls: list[dict],
        tier: str = "standard",
    ) -> float:
        """
        Sum run units for a list of tool call results.

        Each dict must have at least 'tool_name' and 'latency_ms'.
        """
        total = 0.0
        for call in tool_calls:
            total += self.calculate_from_latency(
                latency_ms=call.get("latency_ms", 0.0),
                gpu_seconds=call.get("gpu_seconds", 0.0),
                tier=tier,
                tool_name=call.get("tool_name", "default"),
            )
        return round(total, 4)
