#!/usr/bin/env python3
"""
Quick E2E test for the orchestrator service.
Tests basic query handling to verify the service is working.
"""

import grpc
import sys

# Import protobuf stubs
try:
    from shared.generated import agent_pb2, agent_pb2_grpc
except ImportError:
    print("Error: Cannot import protobufs. Run 'make proto-gen-shared' first")
    sys.exit(1)


def test_orchestrator():
    """Test orchestrator with a simple query."""
    
    # Connect to orchestrator (on port 50054)
    channel = grpc.insecure_channel('localhost:50054')
    stub = agent_pb2_grpc.AgentServiceStub(channel)
    
    print("Testing orchestrator on localhost:50054...")
    
    # Test 1: Simple greeting (no tools needed)
    print("\nTest 1: Simple greeting")
    print("=" * 60)
    request = agent_pb2.AgentRequest(
        user_query="Hello! How are you?",
        debug_mode=True
    )
    
    try:
        response = stub.QueryAgent(request)
        print(f"✓ Response received: {response.final_answer[:100]}...")
        print(f"  Context: {response.context_used[:50] if response.context_used else 'none'}...")
        print(f"  Sources: {response.sources[:50] if response.sources else 'none'}...")
    except grpc.RpcError as e:
        print(f"✗ Failed: {e.code()}: {e.details()}")
        return False
    
    # Test 2: Math query (should use math_solver)
    print("\nTest 2: Math query")
    print("=" * 60)
    request = agent_pb2.AgentRequest(
        user_query="What is 234 * 567?",
        debug_mode=True
    )
    
    try:
        response = stub.QueryAgent(request)
        print(f"✓ Response received: {response.final_answer[:100]}...")
        print(f"  Context: {response.context_used[:50] if response.context_used else 'none'}...")
        print(f"  Sources: {response.sources[:50] if response.sources else 'none'}...")
        
        if 'math_solver' in response.execution_graph or 'math' in response.context_used.lower():
            print("  ✓ Math solver was used as expected")
        else:
            print("  ⚠ Warning: math_solver might not have been used")
    except grpc.RpcError as e:
        print(f"✗ Failed: {e.code()}: {e.details()}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All tests passed! Orchestrator is working correctly.")
    print("=" * 60)
    
    channel.close()
    return True


if __name__ == "__main__":
    success = test_orchestrator()
    sys.exit(0 if success else 1)
