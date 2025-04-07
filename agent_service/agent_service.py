from typing import TypedDict, Optional
from grpc_reflection.v1alpha import reflection
import grpc
from concurrent import futures
import time
import logging

import agent_pb2
import agent_pb2_grpc

from shared.clients.llm_client import LLMClient
from shared.clients.chroma_client import ChromaClient
from shared.clients.tool_client import ToolClient

from langgraph.graph import StateGraph, END

from grpc_health.v1 import health, health_pb2_grpc
from grpc_health.v1 import health_pb2

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


class HealthServicer(health.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )
    
class AgentOrchestrator:
    def __init__(self):
        self.llm = LLMClient()
        self.chroma = ChromaClient()
        self.tools = ToolClient()
        
    def requires_external_data(self, query: str) -> bool:
        triggers = ["current", "latest", "recent", "today's"]
        return any(trigger in query.lower() for trigger in triggers)

    def retrieve_vector_context(self, state: AgentState) -> dict:
        try:
            results = self.chroma.query(state["user_query"], top_k=3)
            context = "\n".join(doc['text'] for doc in results)
            logger.debug(f"Vector Context: {context[:200]}...")
            return {"vector_context": context}
        except Exception as e:
            logger.error(f"Vector retrieval failed: {str(e)}")
            return {"error": f"Vector DB error: {str(e)}"}

    def gather_external_data(self, state: AgentState) -> dict:
        try:
            if self.requires_external_data(state["user_query"]):
                search_results = self.tools.web_search(state["user_query"])
                logger.debug(f"External Context: {search_results[:200]}...")
                return {"external_context": search_results}
            return {"external_context": ""}
        except Exception as e:
            logger.error(f"Tool service error: {str(e)}")
            return {"error": f"Tool error: {str(e)}"}

    def construct_prompt(self, state: AgentState) -> dict:
        context_sections = [
            f"Vector Context:\n{state['vector_context']}",
            f"External Context:\n{state['external_context']}"
        ]
        full_context = "\n\n".join(context_sections)
        prompt = SYSTEM_PROMPT.format(context=full_context) + state["user_query"]
        logger.info("Constructed Prompt:\n%s", prompt[:500] + "...")
        return {"enriched_query": prompt}

    def generate_response(self, state: AgentState) -> dict:
        try:
            response = self.llm.generate(state["enriched_query"], max_tokens=512)
            logger.info(f"LLM Response: {response[:200]}... (length: {len(response)})")
            return {"llm_response": response}
        except Exception as e:
            logger.error(f"LLM generation failed: {str(e)}")
            return {"error": f"LLM error: {str(e)}"}

def create_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)
    orchestrator = AgentOrchestrator()
    
    workflow.add_node("retrieve_vector", orchestrator.retrieve_vector_context)
    workflow.add_node("gather_external", orchestrator.gather_external_data)
    workflow.add_node("construct_prompt", orchestrator.construct_prompt)
    workflow.add_node("generate_response", orchestrator.generate_response)
    
    workflow.add_conditional_edges(
        "retrieve_vector",
        lambda state: "gather_external" if orchestrator.requires_external_data(state["user_query"]) else "construct_prompt"
    )
    
    workflow.add_edge("gather_external", "construct_prompt")
    workflow.add_edge("construct_prompt", "generate_response")
    workflow.set_entry_point("retrieve_vector")
    workflow.set_finish_point("generate_response")
    
    return workflow

class AgentServiceServicer(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        self.workflow = create_workflow().compile()
        self.request_counter = 0

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
                final_answer=result.get("llm_response", "No response generated"),
                context_used=result.get("vector_context", "")[:1000],
                sources=result.get("external_context", "")[:1000]
            )
        except Exception as e:
            logger.error(f"Workflow failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return agent_pb2.AgentReply(final_answer=f"System error: {str(e)}")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add your main service
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServiceServicer(), server)
    
    # Add health service
    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    
    # Enable reflection
    from grpc_reflection.v1alpha import reflection
    SERVICE_NAMES = (
        agent_pb2.DESCRIPTOR.services_by_name['AgentService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    server.add_insecure_port('[::]:50054')
    server.start()
    server.wait_for_termination()
    
if __name__ == "__main__":
    serve()