import llm_pb2_grpc, chroma_pb2_grpc, tool_pb2_grpc, agent_pb2_grpc

SERVICES = {
    "llm": {
        "host": "localhost",
        "port": 50051,
        "stub": llm_pb2_grpc.LLMServiceStub,
        "name": "llm_service",
    },
    "chroma": {
        "host": "localhost",
        "port": 50052,
        "stub": chroma_pb2_grpc.ChromaServiceStub,
        "name": "chroma_service"
    },
    "tool": {
        "host": "localhost", 
        "port": 50053,
        "stub": tool_pb2_grpc.ToolServiceStub,
        "name": "tool_service"
    },
    "agent": {
        "host": "localhost",
        "port": 50054,
        "stub": agent_pb2_grpc.AgentServiceStub,
        "name": "agent_service"
    }
}