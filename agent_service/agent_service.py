import grpc
import agent_pb2
import agent_pb2_grpc
import llm_pb2, llm_pb2_grpc
import chroma_pb2, chroma_pb2_grpc
import tool_pb2, tool_pb2_grpc
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

SYSTEM_PROMPT = "You are a helpful AI assistant with access to external tools."

# (Simplified dummy processing for demonstration)
def process_query(query):
    state = {"messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=query)]}
    state["messages"].append(AIMessage(content="The capital of France is Paris."))
    return state["messages"][-1].content

class AgentServiceServicer(agent_pb2_grpc.AgentServiceServicer):
    def QueryAgent(self, request, context):
        answer = process_query(request.user_query)
        return agent_pb2.AgentReply(final_answer=answer)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServiceServicer(), server)
    server.add_insecure_port("[::]:50054")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
