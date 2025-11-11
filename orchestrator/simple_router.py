"""
Simplified keyword-based router for intent classification.

Replaces the heavy llama-cpp-python 3B model router with simple keyword matching
for determining which service or tool should handle a query.
"""

import logging
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """Route recommendation with confidence score."""
    service: str
    tool: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""


class SimpleRouter:
    """
    Lightweight keyword-based router for intent classification.
    
    Uses pattern matching and keyword detection instead of LLM inference
    for fast, deterministic routing decisions.
    """
    
    # Keyword patterns for different tools/services
    PATTERNS = {
        "web_search": {
            "keywords": [
                "search", "google", "find information", "look up", 
                "what is", "who is", "where is", "when did",
                "current", "latest", "news", "research"
            ],
            "patterns": [
                r"\bsearch\s+(?:for|about)\b",
                r"\bfind\s+(?:information|out)\b",
                r"\bwhat\s+(?:is|are|was|were)\b",
                r"\blook\s+up\b"
            ]
        },
        "math_solver": {
            "keywords": [
                "calculate", "compute", "solve", "math", "equation",
                "plus", "minus", "times", "divided", "square root",
                "factorial", "percentage", "average", "sum"
            ],
            "patterns": [
                r"\d+\s*[\+\-\*/]\s*\d+",  # Basic arithmetic
                r"\bcalculate\b",
                r"\bsolve\s+(?:for|equation)\b",
                r"=\s*\?"  # Equation with unknown
            ]
        },
        "load_web_page": {
            "keywords": [
                "load", "fetch", "read", "get content", "extract",
                "scrape", "parse page", "download page"
            ],
            "patterns": [
                r"https?://\S+",  # URL present
                r"\bload\s+(?:page|website|url)\b",
                r"\bfetch\s+(?:from|page)\b"
            ]
        },
        "chroma_service": {
            "keywords": [
                "remember", "recall", "memory", "stored",  "previously",
                "history", "past conversation", "earlier", "before"
            ],
            "patterns": [
                r"\bwhat\s+(?:did|have)\s+(?:i|we)\b",
                r"\b(?:do\s+you\s+)?remember\b",
                r"\brecall\b"
            ]
        }
    }
    
    def __init__(self):
        """Initialize simple router."""
        self.tool_names = list(self.PATTERNS.keys())
        logger.info(f"SimpleRouter initialized with tools: {self.tool_names}")
    
    def route(self, query: str) -> Route:
        """
        Route query to appropriate service/tool.
        
        Args:
            query: User query string
        
        Returns:
            Route: Recommended route with confidence score
        """
        query_lower = query.lower()
        scores: Dict[str, float] = {tool: 0.0 for tool in self.tool_names}
        
        # Score each tool based on keyword and pattern matches
        for tool, config in self.PATTERNS.items():
            # Keyword matching
            for keyword in config["keywords"]:
                if keyword in query_lower:
                    scores[tool] += 1.0
            
            # Pattern matching (higher weight)
            for pattern in config["patterns"]:
                if re.search(pattern, query_lower):
                    scores[tool] += 2.0
        
        # Find best match
        if max(scores.values()) > 0:
            best_tool = max(scores.items(), key=lambda x: x[1])[0]
            confidence = min(scores[best_tool] / 5.0, 1.0)  # Normalize to 0-1
            
            # Map tools to services
            if best_tool in ["web_search", "math_solver", "load_web_page"]:
                service = "agent_service"
                tool = best_tool
            elif best_tool == "chroma_service":
                service = "chroma_service"
                tool = None
            else:
                service = "llm_service"
                tool = None
            
            logger.info(
                f"Router decision: {service}/{tool or 'direct'} "
                f"(confidence={confidence:.2f}, score={scores[best_tool]:.1f})"
            )
            
            return Route(
                service=service,
                tool=tool,
                confidence=confidence,
                reason=f"Matched {int(scores[best_tool])} keywords/patterns"
            )
        
        # Default to LLM service for conversational queries
        logger.info("Router decision: llm_service (default, no keyword matches)")
        return Route(
            service="llm_service",
            tool=None,
            confidence=0.5,
            reason="No specific tool keywords detected, using LLM for conversation"
        )
    
    def health_check(self) -> bool:
        """Check if router is functioning."""
        try:
            # Test with a simple query
            result = self.route("What is 2+2?")
            return result.service == "agent_service" and result.tool == "math_solver"
        except Exception as e:
            logger.error(f"Router health check failed: {e}")
            return False
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tools the router knows about."""
        return self.tool_names
