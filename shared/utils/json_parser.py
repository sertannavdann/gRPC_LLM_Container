"""
JSON extraction utility for LLM tool-calling responses.
Handles various response formats from LLMs.
"""
import re
import json
from typing import Optional, Dict, Any, List, Union
import logging

logger = logging.getLogger(__name__)


def _normalize_json_booleans(text: str) -> str:
    """
    Normalize Python-style booleans to JSON-style.

    LLMs sometimes return True/False/None instead of true/false/null.
    This function fixes those before JSON parsing.
    """
    # Replace Python booleans with JSON booleans (careful not to replace within strings)
    # Use word boundaries to avoid replacing partial matches
    text = re.sub(r'\bTrue\b', 'true', text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b', 'null', text)
    return text


def extract_tool_json(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Extract tool JSON from LLM responses.

    Handles:
    - Markdown code blocks: ```json {...} ```
    - Mixed JSON + prose: "Here's my answer: {...} and that's why"
    - Nested JSON objects
    - Trailing whitespace/newlines
    - Multiple JSON objects (returns first valid one)

    Args:
        response_text: Raw LLM response text

    Returns:
        Extracted JSON dict or None if no valid JSON found
    """
    if not response_text:
        return None

    # Strategy 1: Try markdown code block extraction
    json_from_block = _extract_from_code_block(response_text)
    if json_from_block:
        return json_from_block

    # Strategy 2: Try to find JSON object pattern
    json_from_pattern = _extract_json_object(response_text)
    if json_from_pattern:
        return json_from_pattern

    # Strategy 3: Try direct parse (entire response is JSON)
    try:
        # Normalize Python-style booleans before parsing
        normalized = _normalize_json_booleans(response_text.strip())
        return json.loads(normalized)
    except json.JSONDecodeError:
        pass

    logger.debug(f"No valid JSON found in response: {response_text[:200]}...")
    return None


def _extract_from_code_block(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from markdown code blocks."""
    # Match ```json ... ``` or ``` ... ```
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                # Normalize Python-style booleans before parsing
                normalized = _normalize_json_booleans(match.strip())
                parsed = json.loads(normalized)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return None


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object using brace matching."""
    # Find potential JSON start positions
    start_positions = [i for i, c in enumerate(text) if c == '{']

    for start in start_positions:
        # Try to extract balanced JSON
        result = _extract_balanced_json(text, start)
        if result:
            try:
                # Normalize Python-style booleans before parsing
                normalized = _normalize_json_booleans(result)
                parsed = json.loads(normalized)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return None


def _extract_balanced_json(text: str, start: int) -> Optional[str]:
    """Extract balanced JSON string starting at given position."""
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == '\\' and in_string:
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]

    return None


def extract_tool_calls(response_text: str) -> List[Dict[str, Any]]:
    """
    Extract multiple tool calls from response.

    Returns:
        List of tool call dicts with 'name' and 'arguments' keys
    """
    result = extract_tool_json(response_text)
    if not result:
        return []

    # Handle single tool call
    if 'name' in result and 'arguments' in result:
        return [result]

    # Handle tool_calls array format
    if 'tool_calls' in result:
        return result['tool_calls']

    # Handle nested tool_call
    if 'tool_call' in result:
        return [result['tool_call']]

    return []


def safe_parse_arguments(arguments: Union[str, Dict]) -> Dict[str, Any]:
    """
    Safely parse tool arguments which may be string or dict.

    Args:
        arguments: Either a JSON string or already-parsed dict

    Returns:
        Parsed arguments dict, empty dict on failure
    """
    if isinstance(arguments, dict):
        return arguments

    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse arguments string: {arguments[:100]}")
            return {}

    return {}
