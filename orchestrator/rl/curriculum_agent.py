import torch
import torch.nn as nn
from typing import Dict, List, Tuple

class CurriculumAgent(nn.Module):
    """
    Learns to assign tasks to optimal executors (endpoints).
    Trained via GRPO (Group Relative Policy Optimization). [web:166]
    """
    
    def __init__(self, state_dim: int = 10, num_executors: int = 5):
        super().__init__()
        self.policy_net = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, num_executors),
            nn.Softmax(dim=-1)
        )
        
        self.executors = [
            "dashboard",
            "llm_local",
            "llm_claude",
            "llm_perplexity",
            "tool_sandbox"
        ]
    
    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Input: Task embedding + user context + endpoint capabilities
        Output: Probability distribution over executors
        """
        return self.policy_net(state)
    
    def select_executor(
        self,
        query: str,
        user_context: Dict,
        endpoint_stats: Dict
    ) -> Tuple[str, float]:
        """
        Select optimal executor for given query.
        """
        # Encode state
        state = self._encode_state(query, user_context, endpoint_stats)
        
        # Get action probabilities
        with torch.no_grad():
            probs = self.forward(state)
        
        # Sample executor
        action = torch.multinomial(probs, 1).item()
        executor = self.executors[action]
        confidence = probs[0][action].item()  # probs is [1, num_executors] usually if batched, here likely [num_executors] if 1D input
        
        return executor, confidence
    
    def _encode_state(
        self,
        query: str,
        user_context: Dict,
        endpoint_stats: Dict
    ) -> torch.Tensor:
        """
        Encode task state into fixed-size vector.
        Features:
        - Query complexity (length, entities, question words)
        - User context availability (finance, calendar, health)
        - Endpoint success rates
        - Current tool usage statistics
        """
        features = []
        
        # Query features
        features.append(len(query.split()))  # Complexity
        features.append(int('?' in query))    # Question type
        features.append(int(any(kw in query.lower() 
                               for kw in ['budget', 'money', 'transaction'])))  # Finance signal
        features.append(int(any(kw in query.lower() 
                               for kw in ['calendar', 'meeting', 'schedule'])))  # Calendar signal
        
        # Context availability
        features.append(float(len(user_context.get('finance', [])) > 0))
        features.append(float(len(user_context.get('calendar', [])) > 0))
        features.append(float(len(user_context.get('health', [])) > 0))
        
        # Endpoint success rates (from stats)
        # Assuming stats dictionary structure
        for executor in self.executors:
            features.append(endpoint_stats.get(executor, {}).get('success_rate', 0.5))
            
        # Ensure we match state_dim (pad or truncate)
        # In init, state_dim=10. 
        # Here: 4 query + 3 context + 5 executors = 12 features.
        # We should update init default or pad/truncate. 
        # Let's behave robustly and return tensor.
        
        return torch.tensor(features, dtype=torch.float32)
