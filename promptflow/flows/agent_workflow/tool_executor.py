"""
Tool Executor Node - Executes selected tools via gRPC services.

Connects to sandbox_service for code execution and other tool services.
"""
import grpc
import json
import os
import sys
from typing import Dict, Any, List
from promptflow.core import tool

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

try:
    from shared.generated import sandbox_pb2, sandbox_pb2_grpc
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False


def execute_math_solver(expression: str) -> Dict[str, Any]:
    """Execute a math expression safely."""
    try:
        # Safe eval for basic math
        allowed_chars = set('0123456789+-*/.() ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return {"success": True, "result": str(result)}
        else:
            return {"success": False, "error": "Invalid characters in expression"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
    """Execute code via sandbox service."""
    if not SANDBOX_AVAILABLE:
        return {"success": False, "error": "Sandbox service not available"}
    
    try:
        host = os.environ.get("SANDBOX_HOST", "localhost")
        port = os.environ.get("SANDBOX_PORT", "50057")
        channel = grpc.insecure_channel(f"{host}:{port}")
        stub = sandbox_pb2_grpc.SandboxServiceStub(channel)
        
        request = sandbox_pb2.ExecuteRequest(
            code=code,
            language=language,
            timeout_seconds=30
        )
        
        response = stub.Execute(request, timeout=35)
        
        return {
            "success": response.success,
            "stdout": response.stdout,
            "stderr": response.stderr,
            "exit_code": response.exit_code
        }
    except grpc.RpcError as e:
        return {"success": False, "error": f"gRPC error: {e.code()}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_web_search(query: str) -> Dict[str, Any]:
    """Execute web search (placeholder - needs SERPER_API_KEY)."""
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return {"success": False, "error": "SERPER_API_KEY not configured"}
    
    # Placeholder - actual implementation would call Serper API
    return {
        "success": True,
        "results": f"Web search results for: {query}",
        "note": "Implement actual Serper API call"
    }


TOOL_EXECUTORS = {
    "math_solver": lambda args: execute_math_solver(args.get("expression", "")),
    "execute_code": lambda args: execute_code(args.get("code", ""), args.get("language", "python")),
    "web_search": lambda args: execute_web_search(args.get("query", "")),
}


@tool
def tool_executor(tool_selection: str, query: str, max_iterations: int = 5) -> Dict[str, Any]:
    """
    Execute selected tools and collect results.
    
    Args:
        tool_selection: JSON string from tool_selector LLM
        query: Original user query
        max_iterations: Maximum tool execution iterations
        
    Returns:
        Dictionary with tool execution results
    """
    result = {
        "results": [],
        "tools_called": [],
        "total_iterations": 0,
        "success": True
    }
    
    try:
        selection = json.loads(tool_selection)
    except json.JSONDecodeError:
        result["success"] = False
        result["error"] = "Failed to parse tool selection JSON"
        return result
    
    if not selection.get("requires_tool", False):
        result["results"].append({
            "type": "no_tool",
            "message": "No tools required for this query"
        })
        return result
    
    # Handle clarification needed
    if selection.get("clarification_question"):
        result["results"].append({
            "type": "clarification",
            "question": selection["clarification_question"]
        })
        return result
    
    # Execute each tool
    tools = selection.get("tools", [])
    for i, tool_spec in enumerate(tools[:max_iterations]):
        tool_name = tool_spec.get("name")
        tool_args = tool_spec.get("arguments", {})
        
        result["total_iterations"] += 1
        result["tools_called"].append(tool_name)
        
        if tool_name in TOOL_EXECUTORS:
            try:
                tool_result = TOOL_EXECUTORS[tool_name](tool_args)
                result["results"].append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "output": tool_result
                })
            except Exception as e:
                result["results"].append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "error": str(e)
                })
        else:
            result["results"].append({
                "tool": tool_name,
                "arguments": tool_args,
                "error": f"Unknown tool: {tool_name}"
            })
    
    result["tools_called"] = ", ".join(result["tools_called"]) if result["tools_called"] else "none"
    return result
