"""
Run Agent - Wrapper to execute the agent workflow for evaluation.
"""
import os
import sys
from typing import Dict, Any
from promptflow.core import tool

# Add paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "promptflow", "flows", "agent_workflow"))

from intent_analyzer import intent_analyzer
from tool_executor import execute_math_solver


@tool
def run_agent(query: str) -> Dict[str, Any]:
    """
    Run the agent workflow and return results for evaluation.
    
    Simplified version that runs intent analysis and basic tool execution.
    """
    result = {
        "query": query,
        "answer": "",
        "tools_used": "",
        "success": True
    }
    
    try:
        # Run intent analysis
        intent = intent_analyzer(query)
        detected_tools = intent.get("detected_tools", [])
        result["tools_used"] = ",".join(detected_tools)
        
        # Execute tools if detected
        if "math_solver" in detected_tools:
            # Extract math expression from query
            import re
            match = re.search(r'[\d\s\+\-\*\/\(\)\.]+', query)
            if match:
                expression = match.group().strip()
                math_result = execute_math_solver(expression)
                if math_result.get("success"):
                    result["answer"] = str(math_result.get("result", ""))
                else:
                    result["answer"] = f"Error: {math_result.get('error')}"
        
        elif "execute_code" in detected_tools:
            result["answer"] = "Code execution requested"
        
        elif not detected_tools:
            result["answer"] = "General conversation - no tools needed"
        
        else:
            result["answer"] = f"Tools detected: {', '.join(detected_tools)}"
            
    except Exception as e:
        result["success"] = False
        result["answer"] = f"Error: {str(e)}"
    
    return result
