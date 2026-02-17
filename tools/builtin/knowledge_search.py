"""
KnowledgeSearchTool - Search documents in ChromaDB.

Provides RAG (Retrieval-Augmented Generation) capabilities by connecting
to the chroma_service for semantic document search.
"""
import logging
from typing import Dict, Any, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class KnowledgeSearchTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """Search the knowledge base for relevant documents."""

    name = "search_knowledge"
    description = (
        "Search the knowledge base for relevant documents. "
        "Use when the user asks about previously stored information."
    )
    version = "2.0.0"

    def __init__(self, chroma_client=None):
        self._client = chroma_client

    def _get_client(self):
        """Get or create ChromaDB client (lazy initialization)."""
        if self._client is None:
            try:
                from shared.clients.chroma_client import ChromaClient
                self._client = ChromaClient()
                logger.info("ChromaDB client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB client: {e}")
                return None
        return self._client

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            raise ValueError("'query' parameter is required")
        top_k = kwargs.get("top_k", 5)
        return {"query": query, "top_k": max(1, min(int(top_k), 20))}

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_client()
        if client is None:
            return {
                "status": "error",
                "error": "Knowledge base unavailable -- ChromaDB service not connected",
                "results": [],
                "count": 0,
            }

        try:
            results = client.query(query_text=request["query"], top_k=request["top_k"])
            return {
                "status": "success",
                "results": results,
                "count": len(results),
                "query": request["query"],
            }
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            return {"status": "error", "error": str(e), "results": [], "count": 0}

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response


# Backward-compat module-level function
def search_knowledge(query: str, top_k: int = 5) -> Dict[str, Any]:
    """Legacy wrapper."""
    tool = KnowledgeSearchTool()
    return tool(query=query, top_k=top_k)
