"""
Web page content loader tool.

Fetches and extracts main content from web pages, stripping HTML
and returning clean text suitable for RAG or agent processing.
"""

import logging
import requests
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import re

logger = logging.getLogger(__name__)


def load_web_page(
    url: str,
    max_length: int = 5000,
    include_links: bool = False
) -> Dict[str, Any]:
    """
    Load and extract content from a web page.
    
    Fetches HTML content and extracts the main text, removing scripts,
    styles, and navigation elements. Returns clean, readable text
    suitable for RAG ingestion or agent analysis.
    
    Args:
        url (str): URL of the web page to load
        max_length (int): Maximum content length in characters (default: 5000)
        include_links (bool): Whether to include extracted links (default: False)
    
    Returns:
        Dict with status key:
            - status: "success" or "error"
            - content: Extracted page content (text)
            - title: Page title if available
            - url: Original URL
            - word_count: Number of words in content
            - links: List of links (if include_links=True)
    
    Example:
        >>> result = load_web_page("https://example.com")
        >>> if result["status"] == "success":
        ...     print(f"Title: {result['title']}")
        ...     print(f"Content: {result['content'][:200]}...")
    
    Raises:
        Returns error dict for invalid URLs or request failures
    """
    # Validate URL  
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")
    except Exception as e:
        logger.error(f"Invalid URL '{url}': {e}")
        return {
            "status": "error",
            "error": f"Invalid URL: {str(e)}",
            "url": url
        }
    
    try:
        logger.debug(f"Loading web page: {url}")
        
        # Fetch page with timeout
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ADK-Agent/1.0; +http://example.com/bot)"
        }
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
        
        html_content = response.text
        
        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "No title"
        
        # Remove scripts and styles
        clean_html = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
        
        # Extract links if requested
        links = []
        if include_links:
            link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
            for match in re.finditer(link_pattern, html_content, re.IGNORECASE):
                href = match.group(1)
                text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                if href and not href.startswith('#'):
                    links.append({"href": href, "text": text})
        
        # Remove HTML tags
        text_content = re.sub(r'<[^>]+>', ' ', clean_html)
        
        # Clean up whitespace
        text_content = re.sub(r'\s+', ' ', text_content)
        text_content = text_content.strip()
        
        # Ensure max_length is an integer
        try:
            max_length = int(max_length)
        except (ValueError, TypeError):
            max_length = 5000
            
        # Truncate to max length
        if len(text_content) > max_length:
            text_content = text_content[:max_length] + "..."
            truncated = True
        else:
            truncated = False
        
        # Count words
        word_count = len(text_content.split())
        
        logger.info(f"Loaded page: {title} ({word_count} words)")
        
        result = {
            "status": "success",
            "content": text_content,
            "title": title,
            "url": url,
            "word_count": word_count,
            "truncated": truncated,
            "content_length": len(text_content)
        }
        
        if include_links:
            result["links"] = links[:50]  # Limit to 50 links
            result["link_count"] = len(links)
        
        return result
    
    except requests.exceptions.Timeout:
        logger.error(f"Timeout loading page: {url}")
        return {
            "status": "error",
            "error": "Request timed out after 10 seconds",
            "url": url
        }
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error loading '{url}': {e}")
        status_code = response.status_code if 'response' in locals() else 0
        
        if status_code == 404:
            error_msg = "Page not found (404)"
        elif status_code == 403:
            error_msg = "Access forbidden (403)"
        elif status_code == 500:
            error_msg = "Server error (500)"
        else:
            error_msg = f"HTTP {status_code}: {str(e)}"
        
        return {
            "status": "error",
            "error": error_msg,
            "url": url,
            "status_code": status_code
        }
    
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error loading '{url}'")
        return {
            "status": "error",
            "error": "Failed to connect to server",
            "url": url
        }
    
    except Exception as e:
        logger.error(f"Unexpected error loading '{url}': {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "url": url
        }


def extract_metadata(url: str) -> Dict[str, Any]:
    """
    Extract metadata from a web page (title, description, author, etc.).
    
    Args:
        url: URL to extract metadata from
    
    Returns:
        Dict with metadata fields
    """
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        html = response.text
        
        metadata = {
            "url": url,
            "title": "",
            "description": "",
            "author": "",
            "published_date": ""
        }
        
        # Extract meta tags
        meta_patterns = {
            "description": r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
            "author": r'<meta[^>]*name=["\']author["\'][^>]*content=["\']([^"\']+)["\']',
            "published": r'<meta[^>]*property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)["\']'
        }
        
        for key, pattern in meta_patterns.items():
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1)
        
        # Title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            metadata["title"] = title_match.group(1).strip()
        
        return {
            "status": "success",
            "metadata": metadata
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "url": url
        }
