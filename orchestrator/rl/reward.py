from typing import Dict, List, Optional
import numpy as np

class Agent0RewardFunction:
    """
    Agent0-inspired reward for curriculum generation.
    Incentivizes tasks that challenge executors optimally.
    """
    
    def __init__(self, alpha: float = 0.5, beta: float = 0.3, gamma: float = 0.2):
        self.alpha = alpha  # Weight for uncertainty
        self.beta = beta    # Weight for tool complexity
        self.gamma = gamma  # Weight for cost efficiency
    
    def compute_reward(
        self,
        task: Dict,
        executor_responses: List[str],
        tools_used: List[str],
        cost: float
    ) -> float:
        """
        R_total = α·R_uncertainty + β·R_tool + γ·R_cost
        
        R_uncertainty: Variance in executor responses (self-consistency)
        R_tool: Frequency and complexity of tool usage
        R_cost: Inverse of API cost (prefer efficient solutions)
        """
        # Uncertainty reward (high variance = challenging task)
        R_uncertainty = self._compute_uncertainty(executor_responses)
        
        # Tool complexity reward (more tools = harder curriculum)
        R_tool = self._compute_tool_complexity(tools_used)
        
        # Cost efficiency reward (prefer lower-cost solutions)
        R_cost = 1.0 / (1.0 + max(0.0, cost))  # Normalize
        
        return (
            self.alpha * R_uncertainty +
            self.beta * R_tool +
            self.gamma * R_cost
        )
    
    def _compute_uncertainty(self, responses: List[str]) -> float:
        """
        Measure disagreement between multiple executor attempts.
        Agent0 uses this to detect frontier tasks. [web:159][web:169]
        """
        if len(responses) < 2:
            return 0.0
        
        # Pairwise similarity (simplified)
        # In a real implementation, use embeddings. 
        # Here using Jaccard similarity of sets of words for a lightweight proxy.
        similarities = []
        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                sim = self._text_similarity(responses[i], responses[j])
                similarities.append(sim)
        
        # High disagreement = high reward (frontier task)
        # If all agree (similarity 1.0), uncertainty is 0.0.
        avg_sim = np.mean(similarities) if similarities else 1.0
        return 1.0 - avg_sim
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Simple Jaccard similarity on lowercased words."""
        s1 = set(text1.lower().split())
        s2 = set(text2.lower().split())
        if not s1 and not s2:
            return 1.0
        return len(s1.intersection(s2)) / len(s1.union(s2)) if s1.union(s2) else 0.0

    def _compute_tool_complexity(self, tools_used: List[str]) -> float:
        """
        Reward based on tool diversity and frequency.
        Agent0 tracks tool-call frequency as curriculum signal. [web:159][web:162]
        """
        tool_complexity = {
            'dashboard_finance': 0.6,
            'dashboard_calendar': 0.5,
            'dashboard_health': 0.5,
            'web_search': 0.7,
            'execute_code': 0.9,
            'llm_claude': 0.8,
            'llm_local': 0.4
        }
        
        if not tools_used:
            return 0.0
        
        # Complexity = average tool difficulty + diversity bonus
        avg_complexity = np.mean([
            tool_complexity.get(tool, 0.5) for tool in tools_used
        ])
        diversity_bonus = len(set(tools_used)) / len(tools_used)
        
        # Normalized to be roughly in [0, 1.5] range, capped at 1.0 for reward calc usually
        raw_score = avg_complexity * (1.0 + diversity_bonus * 0.5)
        return min(1.0, raw_score)

# For backward compatibility with init logic
compute_reward = Agent0RewardFunction().compute_reward
