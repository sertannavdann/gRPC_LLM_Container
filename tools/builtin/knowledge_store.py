"""
KnowledgeStoreTool - Store documents in ChromaDB.

Split from knowledge_search.py for separation of concerns.
"""
import logging
from typing import Dict, Any, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class KnowledgeStoreTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """Store a document in the knowledge base for later retrieval."""

    name = "store_knowledge"
    description = (
        "Store a document in the knowledge base for later retrieval. "
        "Use when the user wants to save information for future reference."
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
        document_id = kwargs.get("document_id")
        text = kwargs.get("text")
        if not document_id:
            raise ValueError("'document_id' parameter is required")
        if not text:
            raise ValueError("'text' parameter is required")
        return {
            "document_id": document_id,
            "text": text,
            "source": kwargs.get("source", "user"),
        }

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_client()
        if client is None:
            return {
                "status": "error",
                "error": "Knowledge base unavailable -- ChromaDB service not connected",
            }

        try:
            success = client.add_document(
                document_id=request["document_id"],
                text=request["text"],
                metadata={"source": request["source"]},
            )
            if success:
                return {"status": "success", "document_id": request["document_id"]}
            else:
                return {"status": "error", "error": "Failed to store document in ChromaDB"}
        except Exception as e:
            logger.error(f"Knowledge store failed: {e}")
            return {"status": "error", "error": str(e)}

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response


# Backward-compat module-level function
def store_knowledge(document_id: str, text: str, source: str = "user") -> Dict[str, Any]:
    """Legacy wrapper."""
    tool = KnowledgeStoreTool()
    return tool(document_id=document_id, text=text, source=source)
