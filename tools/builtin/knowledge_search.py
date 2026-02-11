"""
Knowledge Base Tool - Search and store documents in ChromaDB.

Provides RAG (Retrieval-Augmented Generation) capabilities by connecting
to the chroma_service for semantic document search and storage.
"""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Lazy-initialized ChromaDB client
_client = None


def _get_client():
    """Get or create ChromaDB client (lazy initialization)."""
    global _client
    if _client is None:
        try:
            from shared.clients.chroma_client import ChromaClient
            _client = ChromaClient()
            logger.info("ChromaDB client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            return None
    return _client


def search_knowledge(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Search the knowledge base for relevant documents.

    Use this tool when the user asks about previously stored information,
    wants to search notes or documents, or needs context from the knowledge base.

    Args:
        query (str): Natural language search query
        top_k (int): Number of results to return (1-20, default: 5)

    Returns:
        Dict with status key:
            - status: "success" or "error"
            - results: List of matching documents with text, metadata, and score
            - count: Number of results found
            - query: Original search query
    """
    client = _get_client()
    if client is None:
        return {
            "status": "error",
            "error": "Knowledge base unavailable — ChromaDB service not connected",
            "results": [],
            "count": 0,
        }

    try:
        top_k = max(1, min(top_k, 20))
        results = client.query(query_text=query, top_k=top_k)

        return {
            "status": "success",
            "results": results,
            "count": len(results),
            "query": query,
        }
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "results": [],
            "count": 0,
        }


def store_knowledge(document_id: str, text: str, source: str = "user") -> Dict[str, Any]:
    """
    Store a document in the knowledge base for later retrieval.

    Use this tool when the user wants to save information, notes, or
    documents for future reference.

    Args:
        document_id (str): Unique identifier for the document
        text (str): The document text content to store
        source (str): Source label (e.g., "user", "web", "file") (default: "user")

    Returns:
        Dict with status key:
            - status: "success" or "error"
            - document_id: ID of the stored document
    """
    client = _get_client()
    if client is None:
        return {
            "status": "error",
            "error": "Knowledge base unavailable — ChromaDB service not connected",
        }

    try:
        success = client.add_document(
            document_id=document_id,
            text=text,
            metadata={"source": source},
        )

        if success:
            return {
                "status": "success",
                "document_id": document_id,
            }
        else:
            return {
                "status": "error",
                "error": "Failed to store document in ChromaDB",
            }
    except Exception as e:
        logger.error(f"Knowledge store failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
