"""
Context Retriever Node - Retrieves relevant context from ChromaDB.

Connects to the chroma_service via gRPC to fetch embeddings-based context.
"""
import grpc
import os
import sys
from typing import Dict, Any
from promptflow.core import tool

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

try:
    from shared.generated import chroma_pb2, chroma_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False


def get_chroma_client():
    """Get gRPC client for ChromaDB service."""
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = os.environ.get("CHROMA_PORT", "50052")
    channel = grpc.insecure_channel(f"{host}:{port}")
    return chroma_pb2_grpc.ChromaServiceStub(channel)


@tool
def context_retriever(query: str, intent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve relevant context from the knowledge base.
    
    Args:
        query: User query
        intent: Intent analysis from previous step
        
    Returns:
        Dictionary with retrieved context
    """
    result = {
        "context": "",
        "sources": [],
        "num_results": 0,
        "retrieval_method": "none"
    }
    
    # Skip retrieval for pure computation queries
    detected_tools = intent.get("detected_tools", [])
    if detected_tools and all(t in ["math_solver", "execute_code"] for t in detected_tools):
        result["retrieval_method"] = "skipped_computation"
        return result
    
    if not GRPC_AVAILABLE:
        result["context"] = "Knowledge base unavailable - gRPC not configured"
        result["retrieval_method"] = "error"
        return result
    
    try:
        client = get_chroma_client()
        
        # Query ChromaDB for similar documents
        request = chroma_pb2.QueryRequest(
            query_text=query,
            n_results=5,
            collection_name="knowledge_base"
        )
        
        response = client.Query(request, timeout=10)
        
        if response.documents:
            result["context"] = "\n\n".join(response.documents)
            result["sources"] = list(response.metadata) if response.metadata else []
            result["num_results"] = len(response.documents)
            result["retrieval_method"] = "chroma_embedding"
        else:
            result["retrieval_method"] = "no_results"
            
    except grpc.RpcError as e:
        result["context"] = f"ChromaDB query failed: {e.code()}"
        result["retrieval_method"] = "error"
    except Exception as e:
        result["context"] = f"Context retrieval error: {str(e)}"
        result["retrieval_method"] = "error"
    
    return result
