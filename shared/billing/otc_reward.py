"""
OTC Reward Function — Phase 2 Run-Unit Metering Bridge

Maps (tool_calls, run_units, success) → scalar reward per OTC-GRPO formulation.
This module provides the reward computation for Optimal Tool Calls (OTC) policy learning,
bridging Phase 2 run-unit metering to tool-call optimization signals.

Zero external dependencies (stdlib only).
"""
import math
from dataclasses import dataclass
from typing import TypedDict


class RewardComponents(TypedDict):
    """Return type for compute_composite_reward."""
    r_correctness: float
    r_tool: float
    r_cost: float
    r_composite: float


@dataclass(frozen=True)
class OTCRewardConfig:
    """Configuration for OTC reward computation."""
    alpha: float = 1.0        # tool-reward scaling factor
    beta: float = 0.1         # run-unit cost penalty weight
    smooth_c: float = 2.0     # OTC decay constant (larger = more tolerant of extra calls)
    ru_baseline: float = 1.0  # baseline run-units for normalization (median from Phase 2)


def otc_tool_reward(m: int, n: float, c: float = 2.0) -> float:
    """
    OTC-GRPO tool reward function.

    Args:
        m: actual tool calls this trajectory
        n: estimated optimal tool calls for (intent_class, module_set)
        c: smooth constant controlling decay rate

    Returns:
        r_tool in [0, 1]. Peak at m == n; decays on both sides.
    """
    if m == 0 and n == 0:
        return 1.0
    if n == 0:
        return math.cos((m * math.pi) / (2 * m + c))
    # harmonic mean mapping f(m,n) → [0, 2n]
    f_mn = (2 * n * m) / (m + n) if (m + n) > 0 else 0.0
    return math.sin((f_mn * math.pi) / (2 * n))


def compute_composite_reward(
    tool_calls: int,
    run_units: float,
    success: bool,
    optimal_n: float,
    cfg: OTCRewardConfig = OTCRewardConfig(),
) -> RewardComponents:
    """
    Full reward computation for one trajectory.

    Returns dict with individual components + composite scalar.
    Maps directly to reward_events table columns.

    Args:
        tool_calls: actual tool calls made
        run_units: metered run units consumed
        success: whether contract tests passed
        optimal_n: estimated optimal tool call count
        cfg: reward configuration

    Returns:
        RewardComponents dict with r_correctness, r_tool, r_cost, r_composite
    """
    r_correctness = 1.0 if success else 0.0
    r_tool = otc_tool_reward(tool_calls, optimal_n, cfg.smooth_c)
    r_cost = min(run_units / cfg.ru_baseline, 5.0) / 5.0  # normalize to [0,1], cap at 5x baseline
    r_composite = cfg.alpha * r_tool * r_correctness - cfg.beta * r_cost

    return {
        "r_correctness": r_correctness,
        "r_tool": round(r_tool, 6),
        "r_cost": round(r_cost, 6),
        "r_composite": round(r_composite, 6),
    }
