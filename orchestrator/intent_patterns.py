"""
Multi-step intent patterns for tool orchestration.
Prevents premature synthesis when queries require multiple tool calls.
"""
from typing import Dict, List, Set, Optional
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class IntentPattern:
    """Defines a multi-tool intent pattern."""
    name: str
    keywords: List[str]
    required_tools: List[str]
    missing_prompt_template: str


# Intent patterns requiring multiple tools
MULTI_TOOL_INTENTS: Dict[str, IntentPattern] = {
    "leave_time": IntentPattern(
        name="leave_time",
        keywords=["leave", "departure", "when should I go", "what time should I leave", "when to leave"],
        required_tools=["get_user_context", "get_commute_time"],
        missing_prompt_template="I have {completed} info. Now I need to call {missing} to calculate the departure time."
    ),
    "daily_briefing": IntentPattern(
        name="daily_briefing",
        keywords=["briefing", "daily summary", "what's my day", "today's schedule", "morning update"],
        required_tools=["get_user_context"],
        missing_prompt_template="I need to call {missing} to provide a complete briefing."
    ),
    "commute_with_calendar": IntentPattern(
        name="commute_with_calendar",
        keywords=["get to my meeting", "travel to appointment", "commute to work"],
        required_tools=["get_user_context", "get_commute_time"],
        missing_prompt_template="I have {completed} info. Now calling {missing} to get travel details."
    ),
}


def detect_intent(query: str) -> Optional[IntentPattern]:
    """
    Detect if query matches a multi-tool intent pattern.

    Args:
        query: User's input query

    Returns:
        Matched IntentPattern or None
    """
    query_lower = query.lower()

    for intent_name, pattern in MULTI_TOOL_INTENTS.items():
        for keyword in pattern.keywords:
            if keyword.lower() in query_lower:
                logger.debug(f"Detected intent '{intent_name}' from keyword '{keyword}'")
                return pattern

    return None


def get_missing_tools(
    intent: IntentPattern,
    completed_tools: Set[str]
) -> List[str]:
    """
    Get tools that still need to be called for this intent.

    Args:
        intent: The detected intent pattern
        completed_tools: Set of tool names already called

    Returns:
        List of missing tool names
    """
    return [t for t in intent.required_tools if t not in completed_tools]


def should_continue_tool_loop(
    query: str,
    completed_tools: Set[str]
) -> Optional[str]:
    """
    Check if the tool loop should continue based on intent.

    Args:
        query: Original user query
        completed_tools: Tools already called in this session

    Returns:
        Prompt to continue tool calling, or None if complete
    """
    intent = detect_intent(query)

    if intent is None:
        return None

    missing = get_missing_tools(intent, completed_tools)

    if not missing:
        return None

    completed_str = ", ".join(completed_tools) if completed_tools else "no"
    missing_str = ", ".join(missing)

    continuation_prompt = intent.missing_prompt_template.format(
        completed=completed_str,
        missing=missing_str
    )

    logger.info(f"Intent '{intent.name}' requires more tools: {missing}")
    return continuation_prompt


def get_intent_system_prompt(query: str) -> Optional[str]:
    """
    Get additional system prompt context for multi-tool intents.

    Use this to inject context before LLM generates tool calls.

    Args:
        query: User query

    Returns:
        System prompt addition or None
    """
    intent = detect_intent(query)

    if intent is None:
        return None

    tool_list = ", ".join(intent.required_tools)
    return f"This query likely requires calling these tools in sequence: {tool_list}. Do not provide a final answer until all required tools have been called."
