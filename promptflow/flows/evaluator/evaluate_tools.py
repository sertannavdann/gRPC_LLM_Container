"""
Evaluate Tools - Check if correct tools were selected.
"""
from typing import Dict, Any
from promptflow.core import tool


@tool
def evaluate_tools(actual_tools: str, expected_tools: str) -> Dict[str, Any]:
    """
    Evaluate tool selection accuracy.
    
    Args:
        actual_tools: Comma-separated list of actually selected tools
        expected_tools: Comma-separated list of expected tools
        
    Returns:
        Evaluation results with accuracy score
    """
    # Parse tool lists
    actual_set = set(t.strip().lower() for t in actual_tools.split(",") if t.strip())
    expected_set = set(t.strip().lower() for t in expected_tools.split(",") if t.strip())
    
    # Handle empty expected (no tools needed)
    if not expected_set:
        accuracy = "1.0" if not actual_set else "0.0"
        return {
            "accuracy": accuracy,
            "details": f"Expected no tools, got: {actual_set or 'none'}",
            "correct": accuracy == "1.0"
        }
    
    # Calculate intersection
    correct_tools = actual_set & expected_set
    
    # Precision: what fraction of selected tools were correct
    precision = len(correct_tools) / len(actual_set) if actual_set else 0.0
    
    # Recall: what fraction of expected tools were selected
    recall = len(correct_tools) / len(expected_set) if expected_set else 0.0
    
    # F1 score
    if precision + recall > 0:
        f1 = 2 * (precision * recall) / (precision + recall)
    else:
        f1 = 0.0
    
    return {
        "accuracy": f"{f1:.2f}",
        "precision": f"{precision:.2f}",
        "recall": f"{recall:.2f}",
        "details": f"Expected: {expected_set}, Got: {actual_set}, Correct: {correct_tools}",
        "correct": f1 >= 0.5
    }
