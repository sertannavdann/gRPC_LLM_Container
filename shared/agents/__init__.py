"""
Agent identity and prompt composition utilities.

Provides soul.md loading, auto-prompt composition, and stage context management
for the multi-agent build pipeline.
"""

from .prompt_composer import compose, load_soul, StageContext

__all__ = ["compose", "load_soul", "StageContext"]
