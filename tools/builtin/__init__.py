"""Actions a spoken turn can ask for: web search (Serper) and page loading."""
from .web_search import web_search
from .web_loader import load_web_page, extract_metadata

__all__ = ["web_search", "load_web_page", "extract_metadata"]
