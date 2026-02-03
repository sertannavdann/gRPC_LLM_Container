"""
Endpoint Metrics for RL Training Pipeline.

Tracks per-provider statistics for reinforcement learning:
- Success rates
- Latency (rolling average)
- Tool usage frequency
- Cost tracking (USD)

Thread-safe and Prometheus-compatible.
"""
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ProviderStats:
    """Statistics for a single provider."""
    total_requests: int = 0
    successful_requests: int = 0
    total_latency_ms: float = 0.0
    total_cost_usd: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests


class EndpointMetrics:
    """
    Track endpoint and provider metrics for RL training.

    Features:
    - Per-provider success rates and latency
    - Tool frequency tracking
    - Cost accumulation
    - Thread-safe operations
    - Prometheus export format

    Example:
        metrics = EndpointMetrics()
        metrics.record_request("claude", success=True, latency_ms=500.0, cost_usd=0.01)
        metrics.record_tool_call("get_user_context")
        summary = metrics.get_summary()
    """

    def __init__(self):
        """Initialize metrics with empty state."""
        self._lock = threading.RLock()
        self._provider_stats: Dict[str, ProviderStats] = defaultdict(ProviderStats)
        self._tool_frequency: Dict[str, int] = defaultdict(int)
        self._total_requests: int = 0
        self._total_cost_usd: float = 0.0

    def record_request(
        self,
        provider: str,
        success: bool,
        latency_ms: float,
        cost_usd: float = 0.0,
    ) -> None:
        """
        Record a completed request.

        Args:
            provider: Provider name (e.g., "claude", "perplexity", "local")
            success: Whether the request succeeded
            latency_ms: Request latency in milliseconds
            cost_usd: Estimated cost in USD
        """
        with self._lock:
            stats = self._provider_stats[provider]
            stats.total_requests += 1
            stats.total_latency_ms += latency_ms
            stats.total_cost_usd += cost_usd

            if success:
                stats.successful_requests += 1

            self._total_requests += 1
            self._total_cost_usd += cost_usd

            logger.debug(
                f"Recorded request: provider={provider}, success={success}, "
                f"latency={latency_ms:.1f}ms, cost=${cost_usd:.4f}"
            )

    def record_tool_call(self, tool_name: str, count: int = 1) -> None:
        """
        Record tool usage.

        Args:
            tool_name: Name of the tool that was called
            count: Number of times called (default 1)
        """
        with self._lock:
            self._tool_frequency[tool_name] += count

    def record_tool_calls(self, tools: List[str]) -> None:
        """
        Record multiple tool calls.

        Args:
            tools: List of tool names that were called
        """
        with self._lock:
            for tool in tools:
                self._tool_frequency[tool] += 1

    @property
    def success_rate(self) -> Dict[str, float]:
        """Get success rate per provider."""
        with self._lock:
            return {
                provider: stats.success_rate
                for provider, stats in self._provider_stats.items()
            }

    @property
    def avg_latency_ms(self) -> Dict[str, float]:
        """Get average latency per provider."""
        with self._lock:
            return {
                provider: stats.avg_latency_ms
                for provider, stats in self._provider_stats.items()
            }

    @property
    def tool_frequency(self) -> Dict[str, int]:
        """Get tool call frequency."""
        with self._lock:
            return dict(self._tool_frequency)

    @property
    def cost_usd(self) -> Dict[str, float]:
        """Get cost per provider."""
        with self._lock:
            return {
                provider: stats.total_cost_usd
                for provider, stats in self._provider_stats.items()
            }

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all metrics.

        Returns:
            Dictionary with all metric summaries
        """
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_cost_usd": round(self._total_cost_usd, 4),
                "success_rate": self.success_rate,
                "avg_latency_ms": {
                    k: round(v, 2) for k, v in self.avg_latency_ms.items()
                },
                "tool_frequency": self.tool_frequency,
                "cost_usd": {
                    k: round(v, 4) for k, v in self.cost_usd.items()
                },
            }

    def to_prometheus(self) -> List[Dict[str, Any]]:
        """
        Export metrics in Prometheus-compatible format.

        Returns:
            List of metric dictionaries suitable for Prometheus exposition
        """
        metrics = []

        with self._lock:
            # Success rate gauge per provider
            for provider, rate in self.success_rate.items():
                metrics.append({
                    "name": "rl_provider_success_rate",
                    "type": "gauge",
                    "value": rate,
                    "labels": {"provider": provider},
                })

            # Latency gauge per provider
            for provider, latency in self.avg_latency_ms.items():
                metrics.append({
                    "name": "rl_provider_avg_latency_ms",
                    "type": "gauge",
                    "value": latency,
                    "labels": {"provider": provider},
                })

            # Tool frequency counter
            for tool, count in self._tool_frequency.items():
                metrics.append({
                    "name": "rl_tool_calls_total",
                    "type": "counter",
                    "value": count,
                    "labels": {"tool": tool},
                })

            # Cost gauge per provider
            for provider, cost in self.cost_usd.items():
                metrics.append({
                    "name": "rl_provider_cost_usd",
                    "type": "gauge",
                    "value": cost,
                    "labels": {"provider": provider},
                })

            # Total metrics
            metrics.append({
                "name": "rl_total_requests",
                "type": "counter",
                "value": self._total_requests,
                "labels": {},
            })
            metrics.append({
                "name": "rl_total_cost_usd",
                "type": "gauge",
                "value": self._total_cost_usd,
                "labels": {},
            })

        return metrics

    def reset(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self._provider_stats.clear()
            self._tool_frequency.clear()
            self._total_requests = 0
            self._total_cost_usd = 0.0
            logger.info("EndpointMetrics reset")

    def get_provider_stats(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Get stats for a specific provider.

        Args:
            provider: Provider name

        Returns:
            Provider statistics or None if not found
        """
        with self._lock:
            if provider not in self._provider_stats:
                return None

            stats = self._provider_stats[provider]
            return {
                "total_requests": stats.total_requests,
                "successful_requests": stats.successful_requests,
                "success_rate": stats.success_rate,
                "avg_latency_ms": round(stats.avg_latency_ms, 2),
                "total_cost_usd": round(stats.total_cost_usd, 4),
            }

    def get_top_tools(self, limit: int = 10) -> List[tuple]:
        """
        Get most frequently used tools.

        Args:
            limit: Maximum number of tools to return

        Returns:
            List of (tool_name, count) tuples sorted by frequency
        """
        with self._lock:
            sorted_tools = sorted(
                self._tool_frequency.items(),
                key=lambda x: x[1],
                reverse=True
            )
            return sorted_tools[:limit]


# Module-level singleton for global metrics tracking
_global_metrics: Optional[EndpointMetrics] = None


def get_global_metrics() -> EndpointMetrics:
    """
    Get the global EndpointMetrics instance.

    Creates a new instance if one doesn't exist.

    Returns:
        Global EndpointMetrics singleton
    """
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = EndpointMetrics()
    return _global_metrics
