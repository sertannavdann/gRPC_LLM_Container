"""
Intent Analyzer Node - Analyzes user query to determine intent and required tools.

This mirrors the orchestrator's intent_patterns.py logic.
"""
import re
import json
from typing import Dict, Any, List
from promptflow.core import tool

# Tool definitions matching the orchestrator
AVAILABLE_TOOLS = {
    "math_solver": {
        "description": "Evaluate mathematical expressions and calculations",
        "patterns": [r'\d+\s*[\+\-\*\/\^]\s*\d+', r'calculate', r'compute', r'what is \d+'],
        "arguments": {"expression": "string"}
    },
    "execute_code": {
        "description": "Execute Python code in a sandboxed environment",
        "patterns": [r'execute', r'run.*code', r'python', r'```python'],
        "arguments": {"code": "string", "language": "string"}
    },
    "web_search": {
        "description": "Search the web for information",
        "patterns": [r'search', r'find.*web', r'google', r'look up'],
        "arguments": {"query": "string"}
    },
    "load_web_page": {
        "description": "Load and extract content from a web page",
        "patterns": [r'load.*page', r'fetch.*url', r'https?://'],
        "arguments": {"url": "string"}
    },
    "search_knowledge": {
        "description": "Search the knowledge base for relevant information",
        "patterns": [r'knowledge', r'database', r'stored', r'remember'],
        "arguments": {"query": "string"}
    },
    "get_calendar_events": {
        "description": "Get calendar events for a date range",
        "patterns": [r'calendar', r'schedule', r'meeting', r'appointment'],
        "arguments": {"start_date": "string", "end_date": "string"}
    },
    "get_commute_time": {
        "description": "Get commute time between locations",
        "patterns": [r'commute', r'drive', r'travel time', r'how long.*get to'],
        "arguments": {"origin": "string", "destination": "string"}
    }
}

# Multi-tool intent patterns
MULTI_TOOL_INTENTS = {
    "daily_commute": {
        "patterns": [r"what time.*leave", r"when.*leave.*work"],
        "required_tools": ["get_calendar_events", "get_commute_time"],
        "description": "Determine departure time based on calendar and traffic"
    },
    "daily_briefing": {
        "patterns": [r"daily briefing", r"morning update", r"what.*today"],
        "required_tools": ["get_calendar_events", "web_search"],
        "description": "Comprehensive daily overview"
    }
}


def detect_patterns(query: str, patterns: List[str]) -> bool:
    """Check if query matches any pattern."""
    query_lower = query.lower()
    for pattern in patterns:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return True
    return False


@tool
def intent_analyzer(query: str) -> Dict[str, Any]:
    """
    Analyze query to determine intent and required tools.
    
    Args:
        query: User input query
        
    Returns:
        Dictionary with intent analysis results
    """
    result = {
        "query": query,
        "detected_tools": [],
        "multi_tool_intent": None,
        "requires_clarification": False,
        "clarification_needed": [],
        "available_tools": list(AVAILABLE_TOOLS.keys()),
        "confidence": 0.0
    }
    
    # Check for multi-tool intents first
    for intent_name, intent_config in MULTI_TOOL_INTENTS.items():
        if detect_patterns(query, intent_config["patterns"]):
            result["multi_tool_intent"] = intent_name
            result["detected_tools"] = intent_config["required_tools"]
            result["confidence"] = 0.9
            
            # Check if destination is specified for commute
            if intent_name == "daily_commute":
                if not re.search(r'to\s+\w+|work|office|home', query, re.IGNORECASE):
                    result["requires_clarification"] = True
                    result["clarification_needed"].append("destination")
            
            return result
    
    # Check individual tool patterns
    for tool_name, tool_config in AVAILABLE_TOOLS.items():
        if detect_patterns(query, tool_config["patterns"]):
            result["detected_tools"].append(tool_name)
    
    # Calculate confidence based on pattern matches
    if result["detected_tools"]:
        result["confidence"] = min(0.8, 0.4 + 0.2 * len(result["detected_tools"]))
    else:
        # No specific tool detected - general conversation
        result["confidence"] = 0.5
    
    return result
