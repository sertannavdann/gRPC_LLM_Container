"""
RL Metrics and Reward Module for Agent0/ToolOrchestra.

This module provides:
- EndpointMetrics: Track per-provider success rates, latency, tool usage, costs
- RewardConfig: Configuration for reward function weights
- compute_reward: Calculate reward signal for RL training

Usage:
    from orchestrator.rl import EndpointMetrics, compute_reward, RewardConfig

    # Create metrics tracker
    metrics = EndpointMetrics()
    metrics.record_request("perplexity", success=True, latency_ms=150.0, cost_usd=0.002)

    # Compute reward
    reward = compute_reward(
        responses=["answer1", "answer2", "answer3"],
        tools_used=["get_user_context", "get_commute_time"],
        cost_usd=0.005
    )
"""
from .metrics import EndpointMetrics
from .reward import compute_reward, RewardConfig

__all__ = [
    "EndpointMetrics",
    "compute_reward",
    "RewardConfig",
]
