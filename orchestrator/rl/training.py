import asyncio
import torch
from typing import List, Dict, Tuple, Any

from .curriculum_agent import CurriculumAgent
from .reward import Agent0RewardFunction

class Agent0TrainingLoop:
    """
    Implements co-evolution between curriculum and executor agents.
    """
    
    def __init__(
        self,
        curriculum_agent: CurriculumAgent,
        executor_pool: Dict[str, Any],
        reward_fn: Agent0RewardFunction
    ):
        self.curriculum_agent = curriculum_agent
        self.executor_pool = executor_pool
        self.reward_fn = reward_fn
        self.optimizer = torch.optim.Adam(curriculum_agent.parameters(), lr=1e-4)
        
        # Mock endpoint stats if not provided/integrated elsewhere
        self.endpoint_stats = {name: {'success_rate': 0.5} for name in curriculum_agent.executors}
    
    def get_endpoint_stats(self) -> Dict:
        return self.endpoint_stats

    async def train_step(self, batch_tasks: List[str], user_context: Dict):
        """
        One training iteration:
        1. Curriculum proposes executor assignments
        2. Executors attempt tasks
        3. Compute rewards based on uncertainty + tool use + cost
        4. Update curriculum policy via GRPO
        """
        trajectories = []
        
        for task in batch_tasks:
            # Curriculum selects executor
            executor_name, confidence = self.curriculum_agent.select_executor(
                task, user_context, self.get_endpoint_stats()
            )
            
            # Execute with selected endpoint
            executor = self.executor_pool.get(executor_name)
            if not executor:
                # Fallback or skip if executor not found
                continue
                
            responses, tools_used, cost = await self._execute_task(
                executor, task, user_context
            )
            
            # Compute reward
            # Construct a task dict wrapper if needed by reward_fn signature
            task_dict = {"query": task}
            reward = self.reward_fn.compute_reward(
                task_dict, responses, tools_used, cost
            )
            
            trajectories.append({
                'executor': executor_name,
                'reward': reward,
                'confidence': confidence
            })
        
        if not trajectories:
            return 0.0

        # GRPO: Group-relative advantage
        rewards = torch.tensor([t['reward'] for t in trajectories])
        mean_reward = rewards.mean()
        advantages = rewards - mean_reward  # Normalize within batch
        
        # Policy gradient update (clamp confidence to avoid log(0) -> -inf)
        confidences = torch.tensor(
            [t['confidence'] for t in trajectories], dtype=rewards.dtype
        )
        confidences = torch.clamp(confidences, min=1e-8)
        loss = -(torch.log(confidences) * advantages).sum()
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        return mean_reward.item()
    
    async def _execute_task(
        self,
        executor,
        task: str,
        user_context: Dict
    ) -> Tuple[List[str], List[str], float]:
        """
        Execute task with given executor, track tools and cost.
        """
        # Run executor multiple times for self-consistency
        responses = []
        all_tools_used = []
        total_cost = 0.0
        
        # Mock implementation for now, assuming executor has .execute
        # In real integration, this calls the gRPC service or internal tool method
        for _ in range(3):  # Self-consistency samples
            try:
                # This assumes executor is an object with an async execute method
                # If it's just a string name, we need a real client wrapper here.
                # For this implementation step, we assume executor_pool contains client objects.
                if hasattr(executor, 'execute'):
                    result = await executor.execute(task, user_context)
                else:
                    # Mock result for string-only executors in early dev
                    result = {
                        'response': f"Executed {task} via {executor}",
                        'tools_used': ['web_search'],
                        'cost': 0.001
                    }
                
                responses.append(result.get('response', ''))
                all_tools_used.extend(result.get('tools_used', []))
                total_cost += result.get('cost', 0.0)
            except Exception as e:
                responses.append(f"Error: {e}")
                
        return responses, all_tools_used, total_cost / 3
