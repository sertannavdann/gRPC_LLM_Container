from typing import TypedDict
from grpc_reflection.v1alpha import reflection
import grpc
from concurrent import futures

import agent_pb2
import agent_pb2_grpc
import llm_pb2
import llm_pb2_grpc
import chroma_pb2
import chroma_pb2_grpc

from langgraph.graph import StateGraph

# Define the AgentState with necessary fields
class AgentState(TypedDict):
    user_query: str
    context: str
    enriched_query: str
    llm_response: str

SYSTEM_PROMPT = "You are a helpful AI assistant with access to external tools."

def requires_context(query: str) -> bool:
    return len(query.split()) < 10

def vector_retrieve(query: str) -> str:
    channel = grpc.insecure_channel("chromadb_service:50052")
    stub = chroma_pb2_grpc.ChromaServiceStub(channel)
    request = chroma_pb2.QueryRequest(query_text=query, top_k=3)
    response = stub.Query(request)
    return "\n".join(doc.text for doc in response.results)

def llm_generate(prompt: str) -> str:
    channel = grpc.insecure_channel("llm_service:50051")
    stub = llm_pb2_grpc.LLMServiceStub(channel)
    request = llm_pb2.GenerateRequest(prompt=prompt, max_tokens=512, temperature=0.7)
    answer_tokens = []
    try:
        for resp in stub.Generate(request):  # Fix typo: Generate instead of Generage
            if resp.is_final:
                break
            answer_tokens.append(resp.token)
    except grpc.RpcError as e:
        return f"Error: Unable to generate response from LLM service. Details: {e.details()}"
    return "".join(answer_tokens)

# Define node functions
def retrieve_context(state: AgentState) -> dict:
    try:
        context = vector_retrieve(state["user_query"])
    except Exception as e:
        context = f"Error retrieving context: {e}"
    return {"context": context}

def enrich_query(state: AgentState) -> dict:
    if requires_context(state["user_query"]):
        enriched = f"{state['user_query']}\n\nContext:\n{state['context']}"
    else:
        enriched = state["user_query"]
    return {"enriched_query": enriched}

def generate_response(state: AgentState) -> dict:
    system_prompt = SYSTEM_PROMPT
    full_prompt = f"System: {system_prompt}\nUser: {state['enriched_query']}\nAssistant:"
    response = llm_generate(full_prompt)
    return {"llm_response": response}

def process_query(query: str) -> str:
    # Initialize the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes to the workflow
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("enrich_query", enrich_query)
    workflow.add_node("generate_response", generate_response)
    
    # Define the flow
    workflow.set_entry_point("retrieve_context")
    workflow.add_edge("retrieve_context", "enrich_query")
    workflow.add_edge("enrich_query", "generate_response")
    workflow.set_finish_point("generate_response")
    
    # Compile and execute
    app = workflow.compile()
    initial_state = AgentState(
        user_query=query,
        context="",
        enriched_query="",
        llm_response=""
    )
    result = app.invoke(initial_state)
    return result["llm_response"]

class AgentServiceServicer(agent_pb2_grpc.AgentServiceServicer):
    def QueryAgent(self, request, context):
        final_answer = process_query(request.user_query)
        return agent_pb2.AgentReply(final_answer=final_answer)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServiceServicer(), server)

    SERVICE_NAMES = (
        agent_pb2.DESCRIPTOR.services_by_name["AgentService"].full_name,
        llm_pb2.DESCRIPTOR.services_by_name["LLMService"].full_name,
        chroma_pb2.DESCRIPTOR.services_by_name["ChromaService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    server.add_insecure_port("[::]:50054")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()