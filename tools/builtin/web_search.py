"""
Web search tool using Serper API.

Provides web search capabilities with structured results following
Google ADK patterns. Requires SERPER_API_KEY environment variable.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def web_search(query: str, num_results: int = 10, search_type: str = "search") -> Dict[str, Any]:
    """
    Search the web using Serper API.
    
    Performs web searches and returns structured results with titles,
    links, snippets, and relevance information. Free tier available
    at serper.dev with 2,500 queries/month.
    
    Args:
        query (str): Search query string
        num_results (int): Maximum number of results to return (1-100, default: 10)
        search_type (str): Type of search - "search", "news", "images" (default: "search")
    
    Returns:
        Dict with status key:
            - status: "success" or "error"
            - results: List of search results with title, link, snippet
            - query: Original search query
            - total_results: Total number of results found
    
    Example:
        >>> result = web_search("LangGraph tutorial", num_results=5)
        >>> if result["status"] == "success":
        ...     for item in result["results"]:
        ...         print(f"{item['title']}: {item['link']}")
    
    Raises:
        Returns error dict if API key missing or request fails
    """
    # Validate API key
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        logger.error("SERPER_API_KEY not found in environment")
        return {
            "status": "error",
            "error": "SERPER_API_KEY not found in environment variables",
            "query": query
        }
    
    # Validate parameters
    try:
        num_results = int(num_results)
    except (ValueError, TypeError):
        num_results = 10
        
    num_results = max(1, min(100, num_results))
    if search_type not in ["search", "news", "images", "places"]:
        search_type = "search"
    
    # Prepare request
    url = f"https://google.serper.dev/{search_type}"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": query,
        "num": num_results
    }
    
    try:
        logger.debug(f"Searching: '{query}' (type: {search_type}, num: {num_results})")
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract results based on search type
        if search_type == "search":
            raw_results = data.get("organic", [])
        elif search_type == "news":
            raw_results = data.get("news", [])
        elif search_type == "images":
            raw_results = data.get("images", [])
        elif search_type == "places":
            raw_results = data.get("places", [])
        else:
            raw_results = []
        
        # Format results
        formatted_results = []
        for item in raw_results[:num_results]:
            formatted_results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", item.get("description", "")),
                "position": item.get("position", 0),
                "date": item.get("date", "")
            })
        
        logger.info(f"Found {len(formatted_results)} results for '{query}'")
        
        return {
            "status": "success",
            "results": formatted_results,
            "query": query,
            "search_type": search_type,
            "total_results": len(formatted_results),
            "knowledge_graph": data.get("knowledgeGraph"),  # Rich snippets
            "answer_box": data.get("answerBox")  # Featured snippets
        }
    
    except requests.exceptions.Timeout:
        logger.error(f"Timeout searching for '{query}'")
        return {
            "status": "error",
            "error": "Search request timed out after 10 seconds",
            "query": query
        }
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error searching for '{query}': {e}")
        if response.status_code == 429:
            error_msg = "API rate limit exceeded (free tier: 2,500 queries/month)"
        elif response.status_code == 401:
            error_msg = "Invalid SERPER_API_KEY"
        else:
            error_msg = f"HTTP {response.status_code}: {str(e)}"
        
        return {
            "status": "error",
            "error": error_msg,
            "query": query,
            "status_code": response.status_code
        }
    
    except Exception as e:
        logger.error(f"Unexpected error searching for '{query}': {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "query": query
        }
