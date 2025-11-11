"""
Quick test for tool calling implementation.
Run this after starting the services to verify tool calling works.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from orchestrator.orchestrator_service import LLMEngineWrapper
from shared.clients.llm_client import LLMClient
from langchain_core.messages import HumanMessage
import json

def test_tool_calling_parsing():
    """Test that the wrapper can parse tool calls from JSON responses."""
    
    # Create a mock wrapper (we'll test parsing directly)
    llm_client = LLMClient(host="localhost", port=50051)
    wrapper = LLMEngineWrapper(llm_client)
    
    print("=" * 60)
    print("Testing Tool Calling Implementation")
    print("=" * 60)
    
    # Test 1: Parse a tool call response
    print("\n1. Testing tool call parsing...")
    tool_response = '{"type": "tool_call", "tool": "math_solver", "arguments": {"expression": "15*23"}}'
    result = wrapper._parse_tool_response(tool_response)
    
    assert "tool_calls" in result, "Missing tool_calls in result"
    assert len(result["tool_calls"]) == 1, f"Expected 1 tool call, got {len(result['tool_calls'])}"
    assert result["tool_calls"][0]["function"]["name"] == "math_solver", "Wrong tool name"
    assert result["tool_calls"][0]["function"]["arguments"]["expression"] == "15*23", "Wrong arguments"
    print("✓ Tool call parsing works!")
    print(f"  Parsed: {result['tool_calls'][0]['function']['name']}({result['tool_calls'][0]['function']['arguments']})")
    
    # Test 2: Parse a direct answer
    print("\n2. Testing direct answer parsing...")
    answer_response = '{"type": "answer", "content": "Hello! How can I help you?"}'
    result = wrapper._parse_tool_response(answer_response)
    
    assert result["content"] == "Hello! How can I help you?", "Wrong content"
    assert len(result["tool_calls"]) == 0, "Should have no tool calls"
    print("✓ Direct answer parsing works!")
    print(f"  Content: {result['content'][:50]}...")
    
    # Test 3: Test tool description formatting
    print("\n3. Testing tool description formatting...")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "math_solver",
                "description": "Solve mathematical expressions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"}
                    }
                }
            }
        }
    ]
    
    desc = wrapper._format_tools_description(tools)
    assert "web_search" in desc, "Missing web_search in description"
    assert "math_solver" in desc, "Missing math_solver in description"
    print("✓ Tool description formatting works!")
    print(f"  Generated description ({len(desc)} chars):")
    print(f"  {desc[:100]}...")
    
    # Test 4: Test message formatting with tools
    print("\n4. Testing message formatting with tool results...")
    from langchain_core.messages import ToolMessage, AIMessage
    
    messages = [
        HumanMessage(content="Calculate 2+2"),
        AIMessage(
            content="",
            additional_kwargs={
                "tool_calls": [{
                    "function": {"name": "math_solver", "arguments": {"expression": "2+2"}}
                }]
            }
        ),
        ToolMessage(content="Result: 4", tool_call_id="call_123", name="math_solver")
    ]
    
    formatted = wrapper._format_messages_with_tools(messages)
    assert "Calculate 2+2" in formatted, "Missing user query"
    assert "math_solver" in formatted, "Missing tool name"
    assert "Result: 4" in formatted, "Missing tool result"
    print("✓ Message formatting with tools works!")
    print(f"  Formatted conversation:\n{formatted}")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nTool calling implementation is ready!")
    print("\nNext steps:")
    print("1. Start services: docker compose up -d")
    print("2. Test end-to-end with actual LLM queries")
    print("3. Check logs: docker compose logs -f orchestrator")

if __name__ == "__main__":
    try:
        test_tool_calling_parsing()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
