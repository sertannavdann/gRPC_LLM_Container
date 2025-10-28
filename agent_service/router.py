"""
Embedded router for service recommendation using llama-cli.

The router uses a small quantized model to analyze user queries and recommend
which services should handle them. This informs the main agent's decision-making
without replacing it.
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from prompts import ROUTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Configuration for the embedded router."""
    model_path: str = "/app/models/qwen2.5-3b-instruct-q5_k_m.gguf"
    llama_cli_path: str = "/app/llama/llama-cli"
    max_tokens: int = 512
    temperature: float = 0.1  # Low temperature for deterministic routing
    n_ctx: int = 2048
    n_threads: int = 4
    timeout_seconds: int = 10


class Router:
    """
    Embedded router that recommends services for user queries.
    
    Uses llama-cli binary to run a quantized 3B model for fast, low-latency
    routing decisions. The router outputs JSON recommendations that inform
    the main agent's decision-making process.
    
    Attributes:
        config: RouterConfig with model and execution settings
        model_loaded: Whether the model has been validated
    
    Example:
        >>> router = Router()
        >>> recommendation = router.route("What is the weather in Paris?")
        >>> print(recommendation["primary_service"])
        "web_search"
    """
    
    def __init__(self, config: Optional[RouterConfig] = None):
        """
        Initialize router with configuration.
        
        Args:
            config: Optional RouterConfig (uses defaults if None)
        """
        self.config = config or RouterConfig()
        self.model_loaded = False
        
        # Validate paths
        self._validate_paths()
        
        logger.info(
            f"Router initialized: "
            f"model={Path(self.config.model_path).name}, "
            f"temp={self.config.temperature}, "
            f"timeout={self.config.timeout_seconds}s"
        )
    
    def _validate_paths(self):
        """Validate that model and llama-cli exist."""
        model_path = Path(self.config.model_path)
        cli_path = Path(self.config.llama_cli_path)
        
        if not model_path.exists():
            logger.warning(f"Router model not found: {model_path}")
            return
        
        if not cli_path.exists():
            logger.warning(f"llama-cli not found: {cli_path}")
            return
        
        if not cli_path.is_file():
            logger.warning(f"llama-cli is not a file: {cli_path}")
            return
        
        self.model_loaded = True
        logger.info("Router model and llama-cli validated")
    
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
        
        Example:
            >>> recommendation = router.route("Calculate 15 * 23")
            >>> print(recommendation["primary_service"])
            "math_solver"
            >>> print(recommendation["confidence"])
            0.98
        """
        start_time = time.time()
        
        if not self.model_loaded:
            logger.warning("Router not available, using fallback")
            return self._fallback_route(query, start_time)
        
        try:
            # Build prompt
            prompt = f"{ROUTER_SYSTEM_PROMPT}\n\nUser Query: {query}\n\nJSON Output:"
            
            # Build llama-cli command
            cmd = [
                self.config.llama_cli_path,
                "-m", self.config.model_path,
                "-p", prompt,
                "-n", str(self.config.max_tokens),
                "--temp", str(self.config.temperature),
                "-c", str(self.config.n_ctx),
                "-t", str(self.config.n_threads),
                "--log-disable",  # Disable llama.cpp logging for cleaner output
            ]
            
            logger.debug(f"Executing router: query='{query[:50]}...'")
            
            # Execute with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            
            if result.returncode != 0:
                logger.error(f"llama-cli failed: {result.stderr}")
                return self._fallback_route(query, start_time, error=result.stderr)
            
            # Extract JSON from output
            output = result.stdout.strip()
            recommendation = self._parse_router_output(output)
            
            # Add metadata
            latency_ms = (time.time() - start_time) * 1000
            recommendation["latency_ms"] = latency_ms
            recommendation["query"] = query[:100]  # Truncated for logging
            
            # Calculate overall confidence
            if recommendation.get("recommended_services"):
                confidences = [
                    s.get("confidence", 0.0)
                    for s in recommendation["recommended_services"]
                ]
                recommendation["confidence"] = max(confidences) if confidences else 0.5
            else:
                recommendation["confidence"] = 0.5
            
            logger.info(
                f"Router recommendation: "
                f"primary={recommendation.get('primary_service', 'unknown')}, "
                f"confidence={recommendation.get('confidence', 0):.2f}, "
                f"latency={latency_ms:.0f}ms"
            )
            
            return recommendation
        
        except subprocess.TimeoutExpired:
            logger.error(f"Router timeout after {self.config.timeout_seconds}s")
            return self._fallback_route(query, start_time, error="timeout")
        
        except Exception as e:
            logger.error(f"Router error: {e}", exc_info=True)
            return self._fallback_route(query, start_time, error=str(e))
    
    def _parse_router_output(self, output: str) -> Dict[str, Any]:
        """
        Parse JSON output from router model.
        
        Args:
            output: Raw output from llama-cli
        
        Returns:
            dict: Parsed recommendation
        """
        # Find JSON in output (may have extra text)
        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        
        if json_start == -1 or json_end == 0:
            logger.warning("No JSON found in router output")
            raise ValueError("No JSON in output")
        
        json_str = output[json_start:json_end]
        
        try:
            recommendation = json.loads(json_str)
            
            # Validate structure
            if "recommended_services" not in recommendation:
                raise ValueError("Missing 'recommended_services' field")
            
            if "primary_service" not in recommendation:
                # Infer from first recommendation
                if recommendation["recommended_services"]:
                    recommendation["primary_service"] = (
                        recommendation["recommended_services"][0].get("service", "llm_service")
                    )
                else:
                    recommendation["primary_service"] = "llm_service"
            
            if "requires_tools" not in recommendation:
                # Infer from primary service
                primary = recommendation["primary_service"]
                recommendation["requires_tools"] = primary not in ["llm_service"]
            
            return recommendation
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from router: {e}")
            logger.debug(f"Raw output: {output[:200]}")
            raise ValueError(f"Invalid JSON: {e}")
    
    def _fallback_route(
        self,
        query: str,
        start_time: float,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Provide fallback routing when router fails.
        
        Uses simple heuristics to recommend services.
        
        Args:
            query: User query
            start_time: Request start time
            error: Optional error message
        
        Returns:
            dict: Fallback recommendation
        """
        query_lower = query.lower()
        latency_ms = (time.time() - start_time) * 1000
        
        # Simple keyword-based routing
        if any(word in query_lower for word in ["weather", "news", "current", "latest", "search"]):
            primary = "web_search"
            confidence = 0.6
            requires_tools = True
        elif any(word in query_lower for word in ["calculate", "solve", "math", "equation", "=", "+"]):
            primary = "math_solver"
            confidence = 0.7
            requires_tools = True
        elif "http" in query_lower or "www." in query_lower or ".com" in query_lower:
            primary = "load_web_page"
            confidence = 0.65
            requires_tools = True
        else:
            primary = "llm_service"
            confidence = 0.5
            requires_tools = False
        
        recommendation = {
            "recommended_services": [
                {
                    "service": primary,
                    "confidence": confidence,
                    "reasoning": "Fallback heuristic routing"
                }
            ],
            "primary_service": primary,
            "requires_tools": requires_tools,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "query": query[:100],
            "fallback": True,
        }
        
        if error:
            recommendation["error"] = error
        
        logger.info(
            f"Fallback routing: "
            f"primary={primary}, "
            f"confidence={confidence:.2f}"
        )
        
        return recommendation
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check router health status.
        
        Returns:
            dict: Health status with:
                - status: "healthy", "degraded", or "unhealthy"
                - model_loaded: Whether model is available
                - model_path: Path to model file
                - cli_path: Path to llama-cli binary
        """
        status = "healthy" if self.model_loaded else "degraded"
        
        return {
            "status": status,
            "model_loaded": self.model_loaded,
            "model_path": self.config.model_path,
            "cli_path": self.config.llama_cli_path,
            "config": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "timeout": self.config.timeout_seconds,
            },
        }
