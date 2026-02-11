"""
LIDM: Worker adapter interface for future-proofing.

Provides a Protocol-based interface so the DelegationManager can
switch from direct LLM-service routing to dedicated worker containers
without code changes — just a config swap.
"""

import logging
from typing import Protocol, Dict, Any, Optional

from shared.clients.llm_client import LLMClientPool

logger = logging.getLogger(__name__)


class WorkerAdapter(Protocol):
    """Protocol for task execution adapters."""

    def execute(self, task_id: str, instruction: str, context: str = "") -> Dict[str, Any]:
        """
        Execute a sub-task and return results.

        Args:
            task_id: Unique task identifier
            instruction: The task instruction/prompt
            context: Optional context from dependent tasks

        Returns:
            Dict with at least {"result": str, "status": str}
        """
        ...


class LLMServiceAdapter:
    """
    Routes tasks to LLM service instances via gRPC.

    This is the current default adapter — routes through LLMClientPool
    to one of the multi-instance LLM services.
    """

    def __init__(self, client_pool: LLMClientPool):
        self.pool = client_pool

    def execute(
        self, task_id: str, instruction: str, context: str = "",
        tier: str = "standard", max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """Execute task via LLM service."""
        prompt = instruction
        if context:
            prompt = f"{context}\n\n{instruction}"

        try:
            result = self.pool.generate(
                prompt=prompt,
                tier=tier,
                max_tokens=max_tokens,
            )
            return {"result": result, "status": "completed", "tier": tier}
        except Exception as e:
            logger.error(f"LLMServiceAdapter failed for {task_id}: {e}")
            return {"result": f"Error: {e}", "status": "failed", "tier": tier}


class RemoteWorkerAdapter:
    """
    Future: Routes tasks to dedicated worker containers using worker.proto.

    Not yet implemented — placeholder for when cluster hardware becomes
    available and dedicated worker containers are deployed.
    """

    def __init__(self, worker_endpoints: Optional[Dict[str, str]] = None):
        self.endpoints = worker_endpoints or {}
        if self.endpoints:
            logger.info(f"RemoteWorkerAdapter configured with {len(self.endpoints)} workers")
        else:
            logger.info("RemoteWorkerAdapter initialized (no workers configured)")

    def execute(
        self, task_id: str, instruction: str, context: str = "",
        capability: str = "general",
    ) -> Dict[str, Any]:
        """Execute task via remote worker container."""
        if not self.endpoints:
            return {
                "result": "No remote workers available",
                "status": "failed",
                "capability": capability,
            }

        # Future: Use worker.proto gRPC client to delegate
        # endpoint = self.endpoints.get(capability, self.endpoints.get("general"))
        # worker_client = WorkerClient(endpoint)
        # return worker_client.execute(task_id, instruction, context)

        return {
            "result": "Remote worker execution not yet implemented",
            "status": "not_implemented",
            "capability": capability,
        }
