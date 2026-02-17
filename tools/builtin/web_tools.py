"""
WebTool - Consolidated web search and page loading.

Replaces:
    - web_search.py (web_search function)
    - web_loader.py (load_web_page function)

Unified behind a single BaseTool with action='search' | 'load'.
"""
import logging
import os
import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import requests

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class WebTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """Search the web or load/extract content from web pages."""

    name = "web"
    description = (
        "Search the web or load web pages. "
        "action='search' for web search, action='load' for page content extraction."
    )
    version = "2.0.0"

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "search")
        if action not in ("search", "load"):
            raise ValueError(f"Unknown action '{action}'. Use 'search' or 'load'.")
        return {
            "action": action,
            "query": kwargs.get("query"),
            "url": kwargs.get("url"),
            "num_results": kwargs.get("num_results", 10),
            "search_type": kwargs.get("search_type", "search"),
            "max_length": kwargs.get("max_length", 5000),
            "include_links": kwargs.get("include_links", False),
            "extract_links": kwargs.get("extract_links", False),
            "max_chars": kwargs.get("max_chars", 8000),
        }

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if request["action"] == "search":
            return self._web_search(request)
        return self._load_web_page(request)

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return response

    # ── Search (from web_search.py) ──────────────────────────────────

    def _web_search(self, request: Dict[str, Any]) -> Dict[str, Any]:
        query = request.get("query")
        if not query:
            return {"status": "error", "error": "Query is required for search action"}

        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            logger.error("SERPER_API_KEY not found in environment")
            return {"status": "error", "error": "SERPER_API_KEY not found", "query": query}

        try:
            num_results = int(request.get("num_results", 10))
        except (ValueError, TypeError):
            num_results = 10
        num_results = max(1, min(100, num_results))

        search_type = request.get("search_type", "search")
        if search_type not in ("search", "news", "images", "places"):
            search_type = "search"

        url = f"https://google.serper.dev/{search_type}"
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": num_results}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            type_key = {"search": "organic", "news": "news", "images": "images", "places": "places"}
            raw_results = data.get(type_key.get(search_type, "organic"), [])

            formatted_results = []
            for item in raw_results[:num_results]:
                formatted_results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", item.get("description", "")),
                    "position": item.get("position", 0),
                    "date": item.get("date", ""),
                })

            return {
                "status": "success",
                "results": formatted_results,
                "query": query,
                "search_type": search_type,
                "total_results": len(formatted_results),
                "knowledge_graph": data.get("knowledgeGraph"),
                "answer_box": data.get("answerBox"),
            }

        except requests.exceptions.Timeout:
            return {"status": "error", "error": "Search request timed out", "query": query}
        except requests.exceptions.HTTPError as e:
            status_code = response.status_code if "response" in dir() else 0
            if status_code == 429:
                error_msg = "API rate limit exceeded"
            elif status_code == 401:
                error_msg = "Invalid SERPER_API_KEY"
            else:
                error_msg = f"HTTP {status_code}: {str(e)}"
            return {"status": "error", "error": error_msg, "query": query}
        except Exception as e:
            return {"status": "error", "error": f"Unexpected error: {str(e)}", "query": query}

    # ── Load Page (from web_loader.py) ───────────────────────────────

    def _load_web_page(self, request: Dict[str, Any]) -> Dict[str, Any]:
        url = request.get("url")
        if not url:
            return {"status": "error", "error": "URL is required for load action"}

        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception as e:
            return {"status": "error", "error": f"Invalid URL: {str(e)}", "url": url}

        include_links = request.get("include_links") or request.get("extract_links", False)
        max_length = request.get("max_length") or request.get("max_chars", 5000)
        try:
            max_length = int(max_length)
        except (ValueError, TypeError):
            max_length = 5000

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; ADK-Agent/1.0; +http://example.com/bot)"
            }
            response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            response.raise_for_status()
            html_content = response.text

            # Extract title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "No title"

            # Remove scripts and styles
            clean_html = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r"<style[^>]*>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

            # Extract links if requested
            links = []
            if include_links:
                link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
                for match in re.finditer(link_pattern, html_content, re.IGNORECASE):
                    href = match.group(1)
                    text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                    if href and not href.startswith("#"):
                        links.append({"href": href, "text": text})

            # Remove HTML tags
            text_content = re.sub(r"<[^>]+>", " ", clean_html)
            text_content = re.sub(r"\s+", " ", text_content).strip()

            truncated = False
            if len(text_content) > max_length:
                text_content = text_content[:max_length] + "..."
                truncated = True

            word_count = len(text_content.split())

            result = {
                "status": "success",
                "content": text_content,
                "title": title,
                "url": url,
                "word_count": word_count,
                "truncated": truncated,
                "content_length": len(text_content),
            }

            if include_links:
                result["links"] = links[:50]
                result["link_count"] = len(links)

            return result

        except requests.exceptions.Timeout:
            return {"status": "error", "error": "Request timed out", "url": url}
        except requests.exceptions.HTTPError as e:
            status_code = response.status_code if "response" in dir() else 0
            error_map = {404: "Page not found (404)", 403: "Access forbidden (403)", 500: "Server error (500)"}
            error_msg = error_map.get(status_code, f"HTTP {status_code}: {str(e)}")
            return {"status": "error", "error": error_msg, "url": url}
        except requests.exceptions.ConnectionError:
            return {"status": "error", "error": "Failed to connect to server", "url": url}
        except Exception as e:
            return {"status": "error", "error": f"Unexpected error: {str(e)}", "url": url}


# ── Backward-compat module-level functions ────────────────────────────

_default_tool: Optional[WebTool] = None


def _get_default_tool() -> WebTool:
    global _default_tool
    if _default_tool is None:
        _default_tool = WebTool()
    return _default_tool


def web_search(
    query: str,
    num_results: int = 10,
    search_type: str = "search",
) -> Dict[str, Any]:
    """Legacy wrapper for web search."""
    return _get_default_tool()(
        action="search", query=query,
        num_results=num_results, search_type=search_type,
    )


def load_web_page(
    url: str,
    max_length: int = 5000,
    include_links: bool = False,
    extract_links: bool = False,
    max_chars: int = 8000,
) -> Dict[str, Any]:
    """Legacy wrapper for web page loading."""
    return _get_default_tool()(
        action="load", url=url,
        max_length=max_length, include_links=include_links,
        extract_links=extract_links, max_chars=max_chars,
    )


def extract_metadata(html_content: str) -> Dict[str, Any]:
    """Legacy wrapper - extract metadata from HTML content."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    meta_desc = ""
    desc_match = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html_content, re.IGNORECASE,
    )
    if desc_match:
        meta_desc = desc_match.group(1).strip()

    return {"title": title, "description": meta_desc}
