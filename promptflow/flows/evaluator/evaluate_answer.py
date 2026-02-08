"""
Evaluate Answer - Check if answer contains expected content.
"""
from typing import Dict, Any
from promptflow.core import tool


@tool
def evaluate_answer(actual_answer: str, expected_contains: str) -> Dict[str, Any]:
    """
    Evaluate if the answer contains expected content.
    
    Args:
        actual_answer: The actual answer produced
        expected_contains: Expected substring or comma-separated substrings
        
    Returns:
        Evaluation results
    """
    if not expected_contains or not expected_contains.strip():
        return {
            "accuracy": "1.0",
            "details": "No expected content specified",
            "correct": True
        }
    
    actual_lower = actual_answer.lower()
    expected_items = [e.strip().lower() for e in expected_contains.split(",") if e.strip()]
    
    found = []
    missing = []
    
    for item in expected_items:
        if item in actual_lower:
            found.append(item)
        else:
            missing.append(item)
    
    accuracy = len(found) / len(expected_items) if expected_items else 1.0
    
    return {
        "accuracy": f"{accuracy:.2f}",
        "details": f"Found: {found}, Missing: {missing}",
        "correct": accuracy >= 0.5,
        "actual_answer": actual_answer[:200] + "..." if len(actual_answer) > 200 else actual_answer
    }
