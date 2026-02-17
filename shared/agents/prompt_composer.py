"""
Auto-prompt composition for multi-agent build pipeline.

Merges static agent soul.md identity with dynamic stage context, intent,
constraints, and repair hints to produce composed prompts for LLM Gateway.

Based on academic research:
- Agentic Builder-Tester Pattern §6.2 (auto-prompt construction)
- Blueprint2Code framework (context interpolation)
- Anthropic's building-effective-agents (structured output enforcement)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Module-level cache for loaded souls
_soul_cache: Dict[str, str] = {}


@dataclass
class StageContext:
    """
    Dynamic context for a pipeline stage.

    Captures current execution state, user intent, constraints, and feedback
    to be interpolated into agent prompts.
    """
    stage: str  # "scaffold" | "implement" | "test" | "repair"
    attempt: int
    intent: str
    constraints: Optional[Dict[str, Any]] = None
    prior_artifacts: Optional[Dict[str, Any]] = None
    repair_hints: Optional[List[str]] = None
    policy_profile: Optional[str] = None
    manifest_snapshot: Optional[Dict[str, Any]] = None


def load_soul(agent_role: str) -> str:
    """
    Load agent soul.md identity file.

    Args:
        agent_role: Agent role name ("builder", "tester", "monitor")

    Returns:
        Soul.md file content as string

    Raises:
        FileNotFoundError: If soul file doesn't exist

    Caches loaded souls to avoid repeated disk reads.
    """
    # Check cache first
    if agent_role in _soul_cache:
        logger.debug(f"Soul cache hit: {agent_role}")
        return _soul_cache[agent_role]

    # Construct path relative to repo root
    # Expected location: agents/souls/{agent_role}.soul.md
    soul_path = Path(__file__).parent.parent.parent / "agents" / "souls" / f"{agent_role}.soul.md"

    if not soul_path.exists():
        raise FileNotFoundError(
            f"Soul file not found: {soul_path}. "
            f"Expected agent role '{agent_role}' to have a soul.md file."
        )

    # Read and cache
    with open(soul_path, "r", encoding="utf-8") as f:
        content = f.read()

    _soul_cache[agent_role] = content
    logger.info(f"Loaded soul: {agent_role} from {soul_path}")

    return content


def compose(
    system: str,
    context: StageContext,
    output_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Compose auto-prompt by merging soul.md with stage context.

    Constructs a complete system prompt by combining:
    1. Static agent identity (soul.md)
    2. Current stage name and attempt number
    3. User intent and constraints
    4. Prior artifacts (for implement/test/repair stages)
    5. Repair hints (for repair stage)
    6. Required output schema

    Args:
        system: Agent soul.md content (from load_soul)
        context: StageContext with current execution state
        output_schema: Optional JSON schema for output validation

    Returns:
        Composed prompt string ready for LLM Gateway

    Example:
        >>> soul = load_soul("builder")
        >>> ctx = StageContext(
        ...     stage="scaffold",
        ...     attempt=1,
        ...     intent="Build a weather adapter for OpenWeather API",
        ...     constraints={"max_files": 3}
        ... )
        >>> prompt = compose(soul, ctx)
    """
    parts = [system, "\n---\n"]

    # Stage header
    parts.append(f"\n## Current Stage: {context.stage} (Attempt {context.attempt})\n")

    # Intent
    parts.append(f"\n## Intent\n{context.intent}\n")

    # Constraints (if any)
    if context.constraints:
        parts.append(f"\n## Constraints\n```json\n{json.dumps(context.constraints, indent=2)}\n```\n")

    # Policy profile (if specified)
    if context.policy_profile:
        parts.append(f"\n## Policy Profile\nCurrent policy: `{context.policy_profile}`\n")

    # Prior artifacts (for implement/test/repair stages)
    if context.prior_artifacts:
        parts.append(
            f"\n## Prior Stage Artifacts\n"
            f"```json\n{json.dumps(context.prior_artifacts, indent=2)}\n```\n"
        )

    # Manifest snapshot (if updating existing module)
    if context.manifest_snapshot:
        parts.append(
            f"\n## Current Module Manifest\n"
            f"```json\n{json.dumps(context.manifest_snapshot, indent=2)}\n```\n"
        )

    # Repair hints (repair stage only)
    if context.repair_hints and context.stage == "repair":
        parts.append("\n## Repair Hints\n")
        parts.append("The validator identified the following issues:\n\n")
        for i, hint in enumerate(context.repair_hints, 1):
            parts.append(f"{i}. {hint}\n")
        parts.append("\nFix these issues while preserving correct functionality.\n")

    # Output schema (if specified)
    if output_schema:
        parts.append(
            f"\n## Required Output Schema\n"
            f"Your response MUST be valid JSON matching this schema:\n\n"
            f"```json\n{json.dumps(output_schema, indent=2)}\n```\n"
        )

    composed = "".join(parts)

    logger.debug(
        f"Composed prompt for stage={context.stage}, "
        f"attempt={context.attempt}, length={len(composed)} chars"
    )

    return composed


def clear_soul_cache() -> None:
    """Clear the soul cache. Useful for testing or hot-reload scenarios."""
    global _soul_cache
    _soul_cache.clear()
    logger.info("Soul cache cleared")
