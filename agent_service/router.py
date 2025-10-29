"""
Embedded router for service recommendation using llama-cpp-python.

The router uses a small quantized model to analyze user queries and recommend
which services should handle them. This informs the main agent's decision-making
without replacing it.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from prompts import ROUTER_SYSTEM_PROMPT

# Import config (works in both package and script mode)
try:
    from .config import RouterConfig
except ImportError:
    from config import RouterConfig

logger = logging.getLogger(__name__)


class Router:
    """
    Embedded router using llama-cpp-python for service recommendation.
    
    The router analyzes user queries and recommends which services should
    be involved in handling them. It returns structured JSON with:
    - recommended_services: List of service names
    - primary_service: Main service to use
    - confidence: 0.0-1.0 confidence score
    """
    
    def __init__(self, config: Optional[RouterConfig] = None):
        """Initialize router with configuration."""
        self.config = config or RouterConfig()
        self.llm = None  # Lazy load on first use
        self.metrics = {
            "total_calls": 0,
            "successful_routes": 0,
            "fallback_routes": 0,
            "errors": 0,
            "avg_latency_ms": 0.0
        }
        self._validate_model_exists()
    
    def _validate_model_exists(self) -> None:
        """Validate that model exists."""
        model_path = Path(self.config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Router model not found: {self.config.model_path}")
        
        logger.info(f"Router model validated: {model_path.name}")
        logger.info(
            f"Router initialized: model={model_path.name}, "
            f"temp={self.config.temperature}, timeout={self.config.timeout_seconds}s"
        )
    
    def _load_model(self):
        """Lazy load the LLM model."""
        if self.llm is not None:
            return
        
        try:
            from llama_cpp import Llama
            
            logger.info(f"Loading router model: {self.config.model_path}")
            self.llm = Llama(
                model_path=self.config.model_path,
                n_ctx=self.config.n_ctx,
                n_threads=self.config.n_threads,
                verbose=False
            )
            logger.info("Router model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load router model: {e}")
            raise
    
    def route(self, query: str) -> Dict[str, Any]:
        """
        Analyze query and recommend services.
        
        Args:
            query: User's natural language query
        
        Returns:
            dict: Router recommendation with keys:
                - recommended_services: List of service recommendations
                - primary_service: Most appropriate service
                - requires_tools: Whether tools are needed
                - confidence: Overall confidence score
                - latency_ms: Router execution time
                - error: Error message (if routing failed)
        """
        start_time = time.time()
        self.metrics["total_calls"] += 1
        
        try:
            # Lazy load model on first use
            self._load_model()
            
            # Build prompt
            prompt = self._build_prompt(query)
            
            # Call LLM with JSON format constraint
            response = self.llm(
                prompt,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stop=["</s>", "\n\n"],
                echo=False
            )
            
            # Extract and parse JSON
            output_text = response["choices"][0]["text"].strip()
            recommendation = self._parse_router_output(output_text)
            
            # Add latency
            latency_ms = int((time.time() - start_time) * 1000)
            recommendation["latency_ms"] = latency_ms
            
            # Update metrics
            self.metrics["successful_routes"] += 1
            self._update_avg_latency(latency_ms)
            
            logger.info(
                f"Router recommendation: primary={recommendation['primary_service']}, "
                f"confidence={recommendation['confidence']:.2f}, "
                f"latency={latency_ms}ms"
            )
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Router error: {e}")
            self.metrics["errors"] += 1
            
            # Fallback to heuristic routing
            return self._fallback_route(query, start_time, str(e))
    
    def _build_prompt(self, query: str) -> str:
        """Build chat-formatted prompt for router."""
        return f"""<|im_start|>system
        {ROUTER_SYSTEM_PROMPT}<|im_end|>
        <|im_start|>user
        {query}<|im_end|>
        <|im_start|>assistant
        """
    
    def _parse_router_output(self, output: str) -> Dict[str, Any]:
        """
        Parse router output to extract JSON recommendation.
        
        Uses brace counting to handle cases where LLM outputs extra text
        after the JSON object.
        """
        # Find first opening brace
        start_idx = output.find('{')
        if start_idx == -1:
            raise ValueError("No JSON object found in router output")
        
        # Count braces to find matching closing brace
        brace_count = 0
        end_idx = start_idx
        
        for i in range(start_idx, len(output)):
            if output[i] == '{':
                brace_count += 1
            elif output[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        
        # Extract and parse JSON
        json_str = output[start_idx:end_idx]
        recommendation = json.loads(json_str)
        
        # Validate required fields
        required_fields = ["recommended_services", "primary_service", "requires_tools"]
        missing = [f for f in required_fields if f not in recommendation]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
        # Extract overall confidence from first recommended service
        if (recommendation.get("recommended_services") and 
            len(recommendation["recommended_services"]) > 0 and
            "confidence" in recommendation["recommended_services"][0]):
            recommendation["confidence"] = recommendation["recommended_services"][0]["confidence"]
        else:
            # Default confidence if not provided
            recommendation["confidence"] = 0.7
        
        return recommendation
    
    def _fallback_route(self, query: str, start_time: float, error: str) -> Dict[str, Any]:
        """
        Fallback routing using keyword heuristics.
        
        Args:
            query: User query
            start_time: Start timestamp
            error: Error message from primary routing
        
        Returns:
            dict: Fallback recommendation
        """
        query_lower = query.lower()
        latency_ms = int((time.time() - start_time) * 1000)
        
        self.metrics["fallback_routes"] += 1
        
        # Keyword-based heuristics
        if any(kw in query_lower for kw in ["search", "find", "look up", "google"]):
            primary = "web_search"
            services = ["web_search"]
        elif any(kw in query_lower for kw in ["calculate", "math", "compute", "+", "-", "*", "/"]):
            primary = "math_solver"
            services = ["math_solver"]
        elif any(kw in query_lower for kw in ["load", "fetch", "read", "download", "url", "http"]):
            primary = "load_web_page"
            services = ["load_web_page"]
        else:
            primary = "llm_service"
            services = ["llm_service"]
        
        logger.info(f"Fallback routing: primary={primary}, confidence=0.50")
        
        return {
            "recommended_services": services,
            "primary_service": primary,
            "requires_tools": primary != "llm_service",
            "confidence": 0.5,
            "latency_ms": latency_ms,
            "error": error,
            "fallback": True
        }
    
    def _update_avg_latency(self, new_latency_ms: int) -> None:
        """Update running average latency."""
        successful = self.metrics["successful_routes"]
        current_avg = self.metrics["avg_latency_ms"]
        
        # Incremental average: new_avg = old_avg + (new_value - old_avg) / count
        self.metrics["avg_latency_ms"] = current_avg + (new_latency_ms - current_avg) / successful
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get router performance metrics."""
        return {
            **self.metrics,
            "success_rate": (
                self.metrics["successful_routes"] / self.metrics["total_calls"]
                if self.metrics["total_calls"] > 0
                else 0.0
            ),
            "fallback_rate": (
                self.metrics["fallback_routes"] / self.metrics["total_calls"]
                if self.metrics["total_calls"] > 0
                else 0.0
            )
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Check router health status."""
        model_path = Path(self.config.model_path)
        model_exists = model_path.exists()
        
        return {
            "model_path": str(model_path),
            "model_exists": model_exists,
            "model_loaded": self.llm is not None,
            "model_size_mb": model_path.stat().st_size / (1024 * 1024) if model_exists else 0,
            "config": {
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "n_ctx": self.config.n_ctx,
                "timeout_seconds": self.config.timeout_seconds
            },
            "metrics": self.get_metrics()
        }
