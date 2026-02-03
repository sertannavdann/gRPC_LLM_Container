from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np

@dataclass
class RewardConfig:
    """Configuration for reward function weights."""
    alpha_uncertainty: float = 0.5
    beta_tool_complexity: float = 0.3
    gamma_cost_efficiency: float = 0.2
    
def compute_reward(
    task: str,
    responses: List[str],
    tools_used: List[str],
    cost: float,
    config: Optional[RewardConfig] = None
) -> float:
    """
    Compute reward signal for RL training based on:
    R = α·uncertainty + β·tool_complexity + γ·cost_efficiency
    
    Args:
        task: The user query or task description
        responses: List of responses from the model (for self-consistency check)
        tools_used: List of tool names used during execution
        cost: Estimated cost in USD
        config: Optional RewardConfig implementation
        
    Returns:
        Float reward value between 0.0 and 1.0 (approximate)
    """
    if config is None:
        config = RewardConfig()
        
    # 1. Uncertainty Reward (Lower uncertainty = Higher reward)
    # Ideally checking semantic similarity of responses
    # For now, placeholder: if we have self-consistency samples, check identity
    r_uncertainty = _compute_disagreement(responses)
    
    # 2. Tool Complexity Reward (Encourage using appropriate tools)
    # Simple heuristic: using tools is good if task is complex
    r_tool = _compute_tool_score(tools_used)
    
    # 3. Cost Efficiency (Lower cost = Higher reward)
    # Normalize: 1.0 / (1.0 + cost) implies diminishing returns on cost savings
    r_cost = 1.0 / (1.0 + max(0.0, cost))
    
    reward = (
        config.alpha_uncertainty * r_uncertainty +
        config.beta_tool_complexity * r_tool +
        config.gamma_cost_efficiency * r_cost
    )
    
    return reward

def _compute_disagreement(responses: List[str]) -> float:
    """
    Compute disagreement score. 
    1.0 = All agree (perfect consistency)
    0.0 = All disagree
    """
    if not responses:
        return 0.0
    if len(responses) == 1:
        return 1.0
        
    # Placeholder: In a real implementation, use embeddings or semantic similarity
    # Here just checking exact string match for simplicity
    unique_responses = set(responses)
    agreement_ratio = 1.0 / len(unique_responses)
    return agreement_ratio

def _compute_tool_score(tools_used: List[str]) -> float:
    """
    Score based on tool usage.
    """
    if not tools_used:
        # Some tasks validly don't need tools, but in an agent context, 
        # we often prize tool use. Let's return 0.5 neutral.
        return 0.5
        
    # Reward variance/complexity
    # e.g. using multiple different tools is better than spamming one
    unique_tools = len(set(tools_used))
    return min(1.0, unique_tools * 0.3)
