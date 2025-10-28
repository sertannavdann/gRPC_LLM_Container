"""
Unit tests for the embedded router.

Tests router JSON parsing, fallback logic, and recommendation structure.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import subprocess

# Import from agent_service (need to adjust path)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agent_service"))

from router import Router, RouterConfig


class TestRouterConfig:
    """Test RouterConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RouterConfig()
        assert config.temperature == 0.1
        assert config.max_tokens == 512
        assert config.timeout_seconds == 10
        assert config.n_threads == 4
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = RouterConfig(
            temperature=0.2,
            max_tokens=256,
            timeout_seconds=5,
        )
        assert config.temperature == 0.2
        assert config.max_tokens == 256
        assert config.timeout_seconds == 5


class TestRouter:
    """Test Router class."""
    
    @pytest.fixture
    def router(self):
        """Create a router instance for testing."""
        config = RouterConfig(
            model_path="/fake/model.gguf",
            llama_cli_path="/fake/llama-cli",
        )
        return Router(config=config)
    
    def test_router_initialization(self, router):
        """Test router initializes correctly."""
        assert router.config is not None
        assert router.config.temperature == 0.1
        assert not router.model_loaded  # Paths are fake
    
    def test_parse_router_output_valid(self, router):
        """Test parsing valid JSON output."""
        output = '''
        Some preamble text
        {
          "recommended_services": [
            {
              "service": "web_search",
              "confidence": 0.95,
              "reasoning": "Need current data"
            }
          ],
          "primary_service": "web_search",
          "requires_tools": true
        }
        Some trailing text
        '''
        
        result = router._parse_router_output(output)
        
        assert result["primary_service"] == "web_search"
        assert result["requires_tools"] is True
        assert len(result["recommended_services"]) == 1
        assert result["recommended_services"][0]["confidence"] == 0.95
    
    def test_parse_router_output_missing_fields(self, router):
        """Test parsing JSON with missing optional fields."""
        output = '''
        {
          "recommended_services": [
            {"service": "llm_service", "confidence": 1.0, "reasoning": "Simple query"}
          ]
        }
        '''
        
        result = router._parse_router_output(output)
        
        # Should infer primary_service from first recommendation
        assert result["primary_service"] == "llm_service"
        # Should infer requires_tools as False for llm_service
        assert result["requires_tools"] is False
    
    def test_parse_router_output_invalid_json(self, router):
        """Test parsing invalid JSON raises error."""
        output = "This is not JSON at all"
        
        with pytest.raises(ValueError, match="No JSON in output"):
            router._parse_router_output(output)
    
    def test_parse_router_output_malformed_json(self, router):
        """Test parsing malformed JSON raises error."""
        output = '{"incomplete": "json"'
        
        with pytest.raises(ValueError):
            router._parse_router_output(output)
    
    def test_fallback_route_web_search(self, router):
        """Test fallback routing for web search query."""
        result = router._fallback_route("What is the current weather in Tokyo?", 0.0)
        
        assert result["primary_service"] == "web_search"
        assert result["requires_tools"] is True
        assert result["fallback"] is True
        assert "confidence" in result
        assert result["confidence"] > 0.5
    
    def test_fallback_route_math_solver(self, router):
        """Test fallback routing for math query."""
        result = router._fallback_route("Calculate 15 * 23", 0.0)
        
        assert result["primary_service"] == "math_solver"
        assert result["requires_tools"] is True
        assert result["fallback"] is True
    
    def test_fallback_route_load_web_page(self, router):
        """Test fallback routing for URL query."""
        result = router._fallback_route("Load https://example.com", 0.0)
        
        assert result["primary_service"] == "load_web_page"
        assert result["requires_tools"] is True
        assert result["fallback"] is True
    
    def test_fallback_route_llm_service(self, router):
        """Test fallback routing for simple query."""
        result = router._fallback_route("Hello, how are you?", 0.0)
        
        assert result["primary_service"] == "llm_service"
        assert result["requires_tools"] is False
        assert result["fallback"] is True
    
    @patch('subprocess.run')
    def test_route_success(self, mock_run, router):
        """Test successful routing with mocked subprocess."""
        # Mock the router to appear loaded
        router.model_loaded = True
        
        # Mock subprocess output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '''
        {
          "recommended_services": [
            {"service": "web_search", "confidence": 0.9, "reasoning": "Current info"}
          ],
          "primary_service": "web_search",
          "requires_tools": true
        }
        '''
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = router.route("What is the weather?")
        
        assert result["primary_service"] == "web_search"
        assert result["requires_tools"] is True
        assert "latency_ms" in result
        assert "confidence" in result
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_route_timeout(self, mock_run, router):
        """Test routing with timeout."""
        router.model_loaded = True
        mock_run.side_effect = subprocess.TimeoutExpired("llama-cli", 10)
        
        result = router.route("Any query")
        
        # Should fall back gracefully
        assert result["fallback"] is True
        assert "error" in result
        assert result["error"] == "timeout"
    
    @patch('subprocess.run')
    def test_route_subprocess_error(self, mock_run, router):
        """Test routing with subprocess error."""
        router.model_loaded = True
        
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Model loading failed"
        mock_run.return_value = mock_result
        
        result = router.route("Any query")
        
        # Should fall back gracefully
        assert result["fallback"] is True
        assert "error" in result
    
    def test_route_model_not_loaded(self, router):
        """Test routing when model is not loaded."""
        # Router initialized with fake paths, so model_loaded should be False
        assert not router.model_loaded
        
        result = router.route("Any query")
        
        # Should use fallback immediately
        assert result["fallback"] is True
        assert "primary_service" in result
    
    def test_health_check(self, router):
        """Test health check returns correct status."""
        health = router.health_check()
        
        assert "status" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        assert "model_loaded" in health
        assert "config" in health
        assert health["config"]["temperature"] == 0.1


class TestRouterIntegration:
    """Integration tests for router (require actual files)."""
    
    @pytest.mark.skipif(
        not Path("/app/models/qwen2.5-3b-instruct-q5_k_m.gguf").exists(),
        reason="Router model not available"
    )
    def test_router_with_real_model(self):
        """Test router with actual model (only runs in container)."""
        router = Router()
        
        if not router.model_loaded:
            pytest.skip("Model not available for integration test")
        
        result = router.route("What is 2 + 2?")
        
        assert "primary_service" in result
        assert "confidence" in result
        assert "latency_ms" in result
        assert result["latency_ms"] < 1000  # Should be fast (< 1 second)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
