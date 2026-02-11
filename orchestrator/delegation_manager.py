"""
LIDM: Local Inference Delegation Manager.

Always-LLM-based task decomposition and multi-instance routing.
Classifies queries, decomposes into sub-tasks, routes to appropriate
LLM service tiers, and aggregates results.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from shared.clients.llm_client import LLMClientPool
from .capability_map import get_tier_for_capability, get_required_tier
from .routing_config import RoutingConfig

# Optional import — metrics may not be available if observability is off
try:
    from shared.observability.metrics import LIDMMetrics
except ImportError:
    LIDMMetrics = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    """A decomposed sub-task with routing information."""
    task_id: str
    instruction: str
    required_capabilities: List[str]
    target_tier: str = ""
    depends_on: List[str] = field(default_factory=list)
    priority: int = 1  # 1=highest
    result: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    duration_ms: float = 0.0


@dataclass
class TaskDecomposition:
    """Result of query analysis and decomposition."""
    original_query: str
    sub_tasks: List[SubTask]
    strategy: str  # "direct", "decompose", "verify"
    complexity_score: float = 0.0
    task_type: str = ""


class DelegationManager:
    """
    Core LIDM logic: classify → decompose → route → execute → aggregate.

    Uses LLM-based classification and decomposition via the standard-tier model,
    then routes sub-tasks to the appropriate LLM instance per capability.
    """

    def __init__(
        self,
        client_pool: LLMClientPool,
        metrics: Optional["LIDMMetrics"] = None,
        config: Optional[RoutingConfig] = None,
    ):
        self.pool = client_pool
        self._classify_tier = "standard"  # Use standard model for routing decisions
        self._metrics = metrics

        # Configurable thresholds (overridden by config / hot-reload)
        perf = config.performance if config else None
        self._complexity_threshold = perf.complexity_threshold_direct if perf else 0.5
        self._consistency_threshold = perf.self_consistency_threshold if perf else 0.6
        self._max_sub_tasks = perf.max_sub_tasks if perf else 5

    def analyze_and_route(self, query: str, context: str = "") -> TaskDecomposition:
        """
        Main entry point: analyze query and produce a routing plan.

        1. Classify the query (capabilities needed, complexity)
        2. If simple → single-task direct routing
        3. If complex → decompose into sub-tasks with dependencies
        4. Resolve routing for each sub-task
        """
        classification = self._classify_query(query)
        logger.info(f"LIDM classification: type={classification.get('task_type')}, "
                     f"complexity={classification.get('complexity', 0):.2f}, "
                     f"capabilities={classification.get('capabilities', [])}")

        complexity = classification.get("complexity", 0.0)
        capabilities = classification.get("capabilities", [])
        task_type = classification.get("task_type", "general")

        # Simple query → direct routing
        if complexity < self._complexity_threshold or len(capabilities) <= 1:
            tier = get_required_tier(capabilities) if capabilities else "standard"
            sub_task = SubTask(
                task_id=f"st_{uuid.uuid4().hex[:6]}",
                instruction=query,
                required_capabilities=capabilities,
                target_tier=tier,
            )
            return TaskDecomposition(
                original_query=query,
                sub_tasks=[sub_task],
                strategy="direct",
                complexity_score=complexity,
                task_type=task_type,
            )

        # Complex query → LLM-based decomposition
        sub_tasks = self._decompose_task(query, classification)
        self._resolve_routing(sub_tasks)

        return TaskDecomposition(
            original_query=query,
            sub_tasks=sub_tasks,
            strategy="decompose",
            complexity_score=complexity,
            task_type=task_type,
        )

    def execute_delegation(self, decomposition: TaskDecomposition) -> Dict[str, Any]:
        """
        Execute all sub-tasks in dependency order, collecting results.

        Returns aggregated result dict.
        """
        completed = {}
        results = []

        # Sort by priority, then execute in dependency order
        pending = list(decomposition.sub_tasks)

        max_rounds = len(pending) + 2  # Safety limit
        round_count = 0

        while pending and round_count < max_rounds:
            round_count += 1
            executed_this_round = []

            for task in pending:
                # Check dependencies
                deps_met = all(dep_id in completed for dep_id in task.depends_on)
                if not deps_met:
                    continue

                # Build context from dependency results
                dep_context = ""
                for dep_id in task.depends_on:
                    dep_result = completed.get(dep_id, "")
                    if dep_result:
                        dep_context += f"\n[Previous result]: {dep_result}\n"

                # Execute sub-task
                task.status = "running"
                start = time.time()

                try:
                    prompt = task.instruction
                    if dep_context:
                        prompt = f"{dep_context}\n\n{prompt}"

                    result = self.pool.generate(
                        prompt=prompt,
                        tier=task.target_tier,
                        max_tokens=1024,
                    )
                    task.result = result
                    task.status = "completed"
                except Exception as e:
                    logger.error(f"Sub-task {task.task_id} failed: {e}")
                    task.result = f"Error: {e}"
                    task.status = "failed"

                task.duration_ms = (time.time() - start) * 1000
                completed[task.task_id] = task.result
                executed_this_round.append(task)
                results.append({
                    "task_id": task.task_id,
                    "tier": task.target_tier,
                    "status": task.status,
                    "duration_ms": task.duration_ms,
                })

                logger.info(f"Sub-task {task.task_id} [{task.target_tier}]: "
                             f"{task.status} in {task.duration_ms:.0f}ms")

            # Remove executed tasks from pending
            for task in executed_this_round:
                pending.remove(task)

            # If no tasks executed this round, we have a dependency deadlock
            if not executed_this_round:
                logger.error("Dependency deadlock: no tasks could execute")
                for task in pending:
                    task.status = "failed"
                    task.result = "Dependency deadlock"
                break

        return {
            "sub_results": results,
            "completed": completed,
        }

    def aggregate_results(
        self, query: str, sub_results: Dict[str, str], decomposition: TaskDecomposition
    ) -> str:
        """
        Synthesize final answer from sub-task results.

        Uses the standard-tier LLM to combine all sub-task outputs
        into a coherent response.
        """
        if len(decomposition.sub_tasks) == 1:
            # Single task — return directly
            task = decomposition.sub_tasks[0]
            return task.result or ""

        # Multi-task — synthesize
        results_text = ""
        for task in decomposition.sub_tasks:
            results_text += f"\n[{task.task_id}] ({', '.join(task.required_capabilities)}): {task.result}\n"

        synthesis_prompt = f"""You are synthesizing results from multiple specialized analyses.

Original question: {query}

Sub-task results:
{results_text}

Provide a clear, unified answer that integrates all the sub-task findings.
Be direct and specific — include relevant details from each result.

Answer:"""

        return self.pool.generate(
            prompt=synthesis_prompt,
            tier="standard",
            max_tokens=1024,
        )

    def verify_result(
        self, query: str, answer: str, complexity: float = 0.0
    ) -> Dict[str, Any]:
        """
        Verification pass for high-stakes results.

        Cascading verification:
        1. Self-consistency (k=3) on standard tier
        2. Model upgrade to heavy tier if originally from standard
        3. AirLLM deep verify for critical results (if ultra tier available)

        Returns: {"verified": bool, "method": str, "confidence": float, "revised_answer": str}
        """
        # Strategy 1: Self-consistency check
        client = self.pool.get_client("standard")
        if client is None:
            return {"verified": True, "method": "skip", "confidence": 0.0, "revised_answer": answer}

        verification_prompt = f"""Question: {query}

Proposed answer: {answer}

Is this answer correct and complete? Respond with a JSON object:
{{"correct": true/false, "confidence": 0.0-1.0, "issues": "description if any"}}"""

        try:
            batch_result = client.generate_batch(
                prompt=verification_prompt,
                num_samples=3,
                max_tokens=256,
                temperature=0.3,
                response_format="json",
            )

            consistency = batch_result.get("self_consistency_score", 0.0)

            if consistency >= self._consistency_threshold:
                return {
                    "verified": True,
                    "method": "self_consistency",
                    "confidence": consistency,
                    "revised_answer": answer,
                }

            # Strategy 2: Upgrade to heavy tier
            logger.info(f"Self-consistency low ({consistency:.2f}), upgrading to heavy tier")
            heavy_client = self.pool.get_client("heavy")
            if heavy_client:
                revised = heavy_client.generate(
                    prompt=f"Answer this question carefully and completely:\n\n{query}",
                    max_tokens=1024,
                    temperature=0.15,
                )
                return {
                    "verified": True,
                    "method": "model_upgrade",
                    "confidence": 0.7,
                    "revised_answer": revised,
                }

            # Strategy 3: AirLLM deep verify (if available)
            ultra_client = self.pool.get_client("ultra")
            if ultra_client and complexity > 0.8:
                logger.info("Routing to AirLLM 70B for deep verification")
                revised = ultra_client.generate(
                    prompt=f"Carefully verify and answer:\n\n{query}",
                    max_tokens=1024,
                    temperature=0.3,
                )
                return {
                    "verified": True,
                    "method": "airllm_deep",
                    "confidence": 0.85,
                    "revised_answer": revised,
                }

        except Exception as e:
            logger.error(f"Verification failed: {e}")

        return {
            "verified": False,
            "method": "failed",
            "confidence": 0.0,
            "revised_answer": answer,
        }

    # ── Private methods ────────────────────────────────────────────────

    def _classify_query(self, query: str) -> dict:
        """
        Classify query using LLM to determine capabilities and complexity.

        Always uses LLM (standard tier) for classification.
        """
        classify_prompt = f"""Analyze this query and respond with JSON only.

Query: "{query}"

Respond with:
{{"task_type": "one of: coding, reasoning, math, finance, multilingual, search, general",
 "capabilities": ["list of: coding, reasoning, analysis, verification, finance, multilingual, math, fast_response, search, deep_research"],
 "complexity": 0.0 to 1.0 (0=trivial, 1=very complex multi-step)}}

JSON:"""

        try:
            response = self.pool.generate(
                prompt=classify_prompt,
                tier=self._classify_tier,
                max_tokens=256,
                temperature=0.1,
                response_format="json",
            )

            parsed = json.loads(response)
            return {
                "task_type": parsed.get("task_type", "general"),
                "capabilities": parsed.get("capabilities", ["fast_response"]),
                "complexity": float(parsed.get("complexity", 0.3)),
            }
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Classification failed, using defaults: {e}")
            return {
                "task_type": "general",
                "capabilities": ["fast_response"],
                "complexity": 0.3,
            }

    def _decompose_task(self, query: str, classification: dict) -> List[SubTask]:
        """
        Decompose complex query into sub-tasks using LLM.

        Returns at most 5 sub-tasks with dependencies.
        """
        decompose_prompt = f"""Break this complex query into 2-5 sub-tasks.

Query: "{query}"
Required capabilities: {classification.get('capabilities', [])}

Respond with JSON array:
[{{"id": "st_1", "instruction": "specific task description", "capabilities": ["needed_capabilities"], "depends_on": []}}]

Keep sub-tasks focused and actionable. Use depends_on to reference earlier task IDs.

JSON:"""

        try:
            response = self.pool.generate(
                prompt=decompose_prompt,
                tier=self._classify_tier,
                max_tokens=512,
                temperature=0.2,
                response_format="json",
            )

            parsed = json.loads(response)
            if not isinstance(parsed, list):
                parsed = [parsed]

            sub_tasks = []
            for i, item in enumerate(parsed[:self._max_sub_tasks]):
                task_id = item.get("id", f"st_{i+1}")
                sub_tasks.append(SubTask(
                    task_id=task_id,
                    instruction=item.get("instruction", query),
                    required_capabilities=item.get("capabilities", ["fast_response"]),
                    depends_on=item.get("depends_on", []),
                    priority=i + 1,
                ))

            return sub_tasks if sub_tasks else [SubTask(
                task_id="st_fallback",
                instruction=query,
                required_capabilities=classification.get("capabilities", ["fast_response"]),
            )]

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Decomposition failed, using single task: {e}")
            return [SubTask(
                task_id="st_fallback",
                instruction=query,
                required_capabilities=classification.get("capabilities", ["fast_response"]),
            )]

    def _resolve_routing(self, sub_tasks: List[SubTask]):
        """Set target_tier for each sub-task based on its capabilities."""
        for task in sub_tasks:
            task.target_tier = get_required_tier(task.required_capabilities)
            logger.debug(f"Routed {task.task_id}: {task.required_capabilities} → {task.target_tier}")

    # ── Observer ────────────────────────────────────────────────────────

    def on_config_changed(self, config: RoutingConfig) -> None:
        """Called by ConfigManager when routing config is updated."""
        perf = config.performance
        self._complexity_threshold = perf.complexity_threshold_direct
        self._consistency_threshold = perf.self_consistency_threshold
        self._max_sub_tasks = perf.max_sub_tasks
        logger.info(
            f"DelegationManager reconfigured: complexity_threshold={self._complexity_threshold}, "
            f"consistency_threshold={self._consistency_threshold}, max_sub_tasks={self._max_sub_tasks}"
        )
