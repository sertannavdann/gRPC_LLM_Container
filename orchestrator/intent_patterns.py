"""
Multi-step intent patterns for tool orchestration.
Prevents premature synthesis when queries require multiple tool calls.

Key Features:
- Destination alias resolution (office/work/home)
- Multi-tool intent detection
- Guardrails for incomplete tool sequences
"""
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# DESTINATION ALIAS RESOLUTION
# =============================================================================

# Canonical destination mappings
DESTINATION_ALIASES: Dict[str, str] = {
    # Office aliases
    "office": "work",
    "the office": "work",
    "workplace": "work",
    "my office": "work",
    "company": "work",
    
    # Home aliases
    "house": "home",
    "my place": "home",
    "apartment": "home",
    "flat": "home",
    
    # Common meeting locations
    "downtown": "downtown",
    "city center": "downtown",
    "city centre": "downtown",
}


def resolve_destination(destination: str) -> str:
    """
    Resolve destination aliases to canonical form.
    
    Args:
        destination: Raw destination string from user/LLM
        
    Returns:
        Canonical destination key
    """
    dest_lower = destination.lower().strip()
    return DESTINATION_ALIASES.get(dest_lower, dest_lower)


def extract_destination_from_query(query: str) -> Optional[str]:
    """
    Extract destination from a query using pattern matching.
    
    Args:
        query: User query
        
    Returns:
        Extracted destination or None
    """
    patterns = [
        r"(?:to|for|at|reach|get to)\s+(?:the\s+)?(\w+(?:\s+\w+)?)",
        r"commute\s+(?:to\s+)?(\w+)",
        r"meeting\s+(?:at|in)\s+(\w+)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query.lower())
        if match:
            raw_dest = match.group(1)
            return resolve_destination(raw_dest)
    
    return None


@dataclass
class IntentPattern:
    """Defines a multi-tool intent pattern."""
    name: str
    keywords: List[str]
    required_tools: List[str]
    missing_prompt_template: str
    requires_destination: bool = False
    clarifying_question: str = ""


# Intent patterns requiring multiple tools
MULTI_TOOL_INTENTS: Dict[str, IntentPattern] = {
    "leave_time": IntentPattern(
        name="leave_time",
        keywords=["leave", "departure", "when should I go", "what time should I leave", "when to leave"],
        required_tools=["get_user_context", "get_commute_time"],
        missing_prompt_template="I have {completed} info. Now I need to call {missing} to calculate the departure time.",
        requires_destination=True,
        clarifying_question="Where would you like to go? (e.g., work, home, or a specific address)"
    ),
    "daily_briefing": IntentPattern(
        name="daily_briefing",
        keywords=["briefing", "daily summary", "what's my day", "today's schedule", "morning update"],
        required_tools=["get_user_context"],
        missing_prompt_template="I need to call {missing} to provide a complete briefing."
    ),
    "commute_with_calendar": IntentPattern(
        name="commute_with_calendar",
        keywords=["get to my meeting", "travel to appointment", "commute to work", "drive to office"],
        required_tools=["get_user_context", "get_commute_time"],
        missing_prompt_template="I have {completed} info. Now calling {missing} to get travel details.",
        requires_destination=True,
        clarifying_question="Which meeting or destination are you asking about?"
    ),
    "meeting_prep": IntentPattern(
        name="meeting_prep",
        keywords=["prepare for meeting", "meeting prep", "get ready for my meeting", "before my meeting"],
        required_tools=["get_user_context"],
        missing_prompt_template="I need to call {missing} to prepare for your meeting."
    ),
    "weather_check": IntentPattern(
        name="weather_check",
        keywords=["weather", "temperature", "forecast", "rain", "snow", "cold outside", "hot outside", "umbrella"],
        required_tools=["get_user_context"],
        missing_prompt_template="I need to call {missing} to get current weather conditions."
    ),
    "weather_commute": IntentPattern(
        name="weather_commute",
        keywords=["should I drive", "dress for commute", "weather for my drive", "road conditions"],
        required_tools=["get_user_context", "get_commute_time"],
        missing_prompt_template="I have {completed} info. Now calling {missing} to combine weather and commute data.",
        requires_destination=True,
        clarifying_question="Where are you heading?"
    ),
    "full_status": IntentPattern(
        name="full_status",
        keywords=["full status", "everything", "complete overview", "what's happening", "status update"],
        required_tools=["get_user_context"],
        missing_prompt_template="I need to call {missing} to get your complete status."
    ),
    "build_module": IntentPattern(
        name="build_module",
        keywords=[
            "build me", "create a", "add integration", "connect to",
            "track my", "set up", "build a", "create an adapter",
            "add a module", "integrate with", "build an integration",
            "make a tracker", "create a tracker",
        ],
        required_tools=["build_module", "validate_module"],
        missing_prompt_template=(
            "Building module: {completed} steps done. "
            "Now calling {missing} to continue the build pipeline."
        ),
    ),
    "manage_modules": IntentPattern(
        name="manage_modules",
        keywords=[
            "my modules", "list modules", "show integrations",
            "what modules", "installed modules", "available modules",
        ],
        required_tools=["list_modules"],
        missing_prompt_template="I need to call {missing} to show your modules."
    ),
}


@dataclass
class IntentAnalysis:
    """Result of intent analysis."""
    intent: Optional[IntentPattern] = None
    destination: Optional[str] = None
    needs_clarification: bool = False
    clarifying_question: str = ""
    completed_tools: Set[str] = field(default_factory=set)
    missing_tools: List[str] = field(default_factory=list)


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


def analyze_intent(
    query: str,
    completed_tools: Optional[Set[str]] = None
) -> IntentAnalysis:
    """
    Comprehensive intent analysis with destination resolution.
    
    Args:
        query: User query
        completed_tools: Set of tools already called
        
    Returns:
        IntentAnalysis with all relevant information
    """
    completed = completed_tools or set()
    analysis = IntentAnalysis(completed_tools=completed)
    
    # Detect intent
    intent = detect_intent(query)
    if intent is None:
        return analysis
    
    analysis.intent = intent
    
    # Get missing tools
    analysis.missing_tools = [t for t in intent.required_tools if t not in completed]
    
    # Check destination requirement
    if intent.requires_destination:
        destination = extract_destination_from_query(query)
        if destination:
            analysis.destination = destination
        else:
            # No destination found - need clarification
            analysis.needs_clarification = True
            analysis.clarifying_question = intent.clarifying_question
    
    return analysis


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
