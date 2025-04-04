# agent_service.py
from typing import TypedDict, Optional
from grpc_reflection.v1alpha import reflection
import grpc
from concurrent import futures
import time
import logging

import agent_pb2
import agent_pb2_grpc
import llm_pb2
import llm_pb2_grpc
import chroma_pb2
import chroma_pb2_grpc
import tool_pb2
import tool_pb2_grpc

from langgraph.graph import StateGraph, END

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_service")

class AgentState(TypedDict):
    user_query: str
    vector_context: str
    external_context: str
    enriched_query: str
    llm_response: str
    current_step: str
    error: Optional[str]

SYSTEM_PROMPT = """You are an AI assistant with access to real-time information. 
Use this context to answer the question:
{context}
"""

def create_grpc_channel(service_name: str, port: int) -> grpc.Channel:
    """Reusable gRPC channel factory with connection pooling"""
    return grpc.insecure_channel(f"{service_name}:{port}")

class AgentOrchestrator:
    def __init__(self):
        # Initialize gRPC channels
        self.tool_channel = create_grpc_channel("tool_service", 50053)
        self.llm_channel = create_grpc_channel("llm_service", 50051)
        self.chroma_channel = create_grpc_channel("chromadb_service", 50052)
        
        # Initialize stubs with retry policies
        self.tool_stub = tool_pb2_grpc.ToolServiceStub(self.tool_channel)
        self.llm_stub = llm_pb2_grpc.LLMServiceStub(self.llm_channel)
        self.chroma_stub = chroma_pb2_grpc.ChromaServiceStub(self.chroma_channel)

    def requires_external_data(self, query: str) -> bool:
        """Determine if real-time data needed"""
        triggers = ["current", "latest", "recent", "today's"]
        return any(trigger in query.lower() for trigger in triggers)

    def retrieve_vector_context(self, state: AgentState) -> dict:
        try:
            response = self.chroma_stub.Query(
                chroma_pb2.QueryRequest(
                    query_text=state["user_query"], top_k=3
                )
            )
            logger.debug(f"Vector Context Retrieved: {state['vector_context'][:200]}...")
            return {"vector_context": "\n".join(doc.text for doc in response.results)}
        except grpc.RpcError as e:
            logger.error(f"Vector retrieval failed: {e.details()}")
            return {"error": f"Vector DB error: {e.details()}"}

    def gather_external_data(self, state: AgentState) -> dict:
        try:
            # First try web search
            search_response = self.tool_stub.CallTool(
                tool_pb2.ToolRequest(
                    tool_name="web_search",
                    params={"query": state["user_query"], "max_results": "3"}
                )
            )
            
            if search_response.success:
                logger.debug(f"Web Search: External Context Sources: {state['external_context'][:200]}...")
                return {"external_context": search_response.output}
            
            # Fallback to direct scraping
            scrape_response = self.tool_stub.CallTool(
                tool_pb2.ToolRequest(
                    tool_name="web_scrape",
                    params={"url": self.find_relevant_source(state["user_query"])}
                )
            )
            logger.debug(f"Web Scrape: External Context Sources: {state['external_context'][:200]}...")
            return {"external_context": scrape_response.output[:5000]}
        except grpc.RpcError as e:
            logger.error(f"Tool service error: {e.details()}")
            return {"error": f"Tool service error: {e.details()}"}

    def construct_prompt(self, state: AgentState) -> dict:
        context_sections = [
            f"ctx_int:\n{state['vector_context']}",
            f"ctx_ext:\n{state['external_context']}"
        ]
        full_context = "\n\n".join(context_sections)
        logger.info("Final Prompt:\n%s", state["enriched_query"])
        return {"enriched_query": SYSTEM_PROMPT.format(context=full_context) + state["user_query"]}

    def generate_response(self, state: AgentState) -> dict:
        try:
            answer = []
            for resp in self.llm_stub.Generate(
                llm_pb2.GenerateRequest(prompt=state["enriched_query"], max_tokens=512)
            ):
                if resp.is_final:
                    break
                answer.append(resp.token)
            logger.info(
                f"LLM Response: {''.join(answer)[:200]}..."
                f" (length: {len(answer)})"
            )
            return {"llm_response": "".join(answer)}
        except grpc.RpcError as e:
            logger.error(f"LLM service error: {e.details()}")
            return {"error": f"LLM service error: {e.details()}"}

def create_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)
    orchestrator = AgentOrchestrator()
    
    # Define nodes
    workflow.add_node("retrieve_vector", orchestrator.retrieve_vector_context)
    workflow.add_node("gather_external", orchestrator.gather_external_data)
    workflow.add_node("construct_prompt", orchestrator.construct_prompt)
    workflow.add_node("generate_response", orchestrator.generate_response)
    
    # Conditional edges
    workflow.add_conditional_edges(
        "retrieve_vector",
        lambda state: "gather_external" if orchestrator.requires_external_data(state["user_query"]) else "construct_prompt"
    )
    
    # Normal edges
    workflow.add_edge("gather_external", "construct_prompt")
    workflow.add_edge("construct_prompt", "generate_response")
    workflow.set_entry_point("retrieve_vector")
    workflow.set_finish_point("generate_response")
    
    return workflow

class AgentServiceServicer(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        self.workflow = create_workflow().compile()
        self.request_counter = 0  # Simple metric tracking
        
    def QueryAgent(self, request, context):
        self.request_counter += 1
        start_time = time.time()
        
        try:
            result = self.workflow.invoke({
                "user_query": request.user_query,
                "vector_context": "",
                "external_context": "",
                "enriched_query": "",
                "llm_response": "",
                "current_step": "start",
                "error": None
            })
            
            latency = time.time() - start_time
            logger.info(f"Request {self.request_counter} completed in {latency:.2f}s")
            
            return agent_pb2.AgentReply(
                final_answer=result["llm_response"],
                context_used=result["vector_context"][:1000],
                sources=result["external_context"][:1000]
            )
        except Exception as e:
            logger.error(f"Workflow failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return agent_pb2.AgentReply(final_answer=f"System error: {str(e)}")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServiceServicer(), server)
    
    # Reflection setup
    services = tuple(
        pb.DESCRIPTOR.services_by_name[service].full_name 
        for pb, service in [
            (agent_pb2, "AgentService"),
            (llm_pb2, "LLMService"),
            (chroma_pb2, "ChromaService"),
            (tool_pb2, "ToolService")
        ]
    ) + (reflection.SERVICE_NAME,)
    
    reflection.enable_server_reflection(services, server)
    server.add_insecure_port("[::]:50054")
    server.start()
    logger.info("Agent Service running on port 50054")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()