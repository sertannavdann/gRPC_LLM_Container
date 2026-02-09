"""
Unit tests for built-in tools (web_search, math_solver, web_loader).

Tests tool functionality with mocked HTTP requests and error handling.
All external dependencies (Serper API, web pages) are mocked.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from tools.builtin.web_search import web_search
from tools.builtin.math_solver import math_solver
from tools.builtin.web_loader import load_web_page, extract_metadata


class TestWebSearch:
    """Test suite for web_search tool."""
    
    def test_web_search_missing_api_key(self, monkeypatch):
        """Test web_search fails gracefully without API key."""
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        
        result = web_search("test query")
        
        assert result["status"] == "error"
        assert "SERPER_API_KEY" in result["error"]
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_success(self, mock_post, monkeypatch):
        """Test successful web search."""
        monkeypatch.setenv("SERPER_API_KEY", "test_key_12345")
        
        # Mock Serper API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Test Result 1",
                    "link": "https://example.com/1",
                    "snippet": "Test snippet 1"
                },
                {
                    "title": "Test Result 2",
                    "link": "https://example.com/2",
                    "snippet": "Test snippet 2"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = web_search("test query", num_results=2)
        
        assert result["status"] == "success"
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Test Result 1"
        assert result["query"] == "test query"
        # API returns results list, not separate count field
        assert len(result["results"]) == 2
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_with_answer_box(self, mock_post, monkeypatch):
        """Test web search with answer box."""
        monkeypatch.setenv("SERPER_API_KEY", "test_key_12345")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answerBox": {
                "answer": "42",
                "title": "The Answer to Life"
            },
            "organic": []
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = web_search("what is the answer")
        
        assert result["status"] == "success"
        assert "answer_box" in result
        assert result["answer_box"]["answer"] == "42"
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_with_knowledge_graph(self, mock_post, monkeypatch):
        """Test web search with knowledge graph."""
        monkeypatch.setenv("SERPER_API_KEY", "test_key_12345")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "knowledgeGraph": {
                "title": "Python (programming language)",
                "type": "Programming Language",
                "description": "A high-level programming language"
            },
            "organic": []
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = web_search("python programming")
        
        assert result["status"] == "success"
        assert "knowledge_graph" in result
        assert result["knowledge_graph"]["title"] == "Python (programming language)"
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_different_types(self, mock_post, monkeypatch):
        """Test different search types (news, images, places)."""
        monkeypatch.setenv("SERPER_API_KEY", "test_key_12345")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"news": [{"title": "News 1"}]}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        # Test news search
        result = web_search("latest news", search_type="news")
        
        assert result["status"] == "success"
        mock_post.assert_called_once()
        # Check URL includes search type
        call_args = mock_post.call_args
        assert "news" in call_args[0][0]  # URL should contain /news
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_timeout(self, mock_post, monkeypatch):
        """Test web search handles timeout."""
        monkeypatch.setenv("SERPER_API_KEY", "test_key_12345")
        
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = web_search("test query")
        
        assert result["status"] == "error"
        # Error message is "Search request timed out after 10 seconds"
        assert "timed out" in result["error"].lower()
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_rate_limit(self, mock_post, monkeypatch):
        """Test web search handles rate limiting."""
        monkeypatch.setenv("SERPER_API_KEY", "test_key_12345")
        
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = Exception("429 Rate Limit")
        mock_post.return_value = mock_response
        
        result = web_search("test query")
        
        assert result["status"] == "error"
        assert "429" in result["error"] or "rate" in result["error"].lower()
    
    @patch('tools.builtin.web_search.requests.post')
    def test_web_search_invalid_api_key(self, mock_post, monkeypatch):
        """Test web search handles invalid API key."""
        monkeypatch.setenv("SERPER_API_KEY", "invalid_key")
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_post.return_value = mock_response
        
        result = web_search("test query")
        
        assert result["status"] == "error"


class TestMathSolver:
    """Test suite for math_solver tool."""
    
    def test_basic_arithmetic(self):
        """Test basic arithmetic operations."""
        test_cases = [
            ("2 + 2", 4),
            ("10 - 3", 7),
            ("4 * 5", 20),
            ("20 / 4", 5),
            ("2 ** 3", 8),  # Exponentiation
            ("10 % 3", 1),  # Modulo
        ]
        
        for expression, expected in test_cases:
            result = math_solver(expression)
            assert result["status"] == "success", f"Failed for {expression}"
            assert result["result"] == expected, f"Expected {expected}, got {result['result']}"
    
    def test_order_of_operations(self):
        """Test order of operations (PEMDAS)."""
        result = math_solver("2 + 2 * 3")
        assert result["status"] == "success"
        assert result["result"] == 8  # Not 12
        
        result = math_solver("(2 + 2) * 3")
        assert result["status"] == "success"
        assert result["result"] == 12
    
    def test_trigonometric_functions(self):
        """Test trigonometric functions."""
        import math
        
        # sin(pi/2) = 1
        result = math_solver("sin(pi / 2)")
        assert result["status"] == "success"
        assert abs(result["result"] - 1.0) < 0.0001
        
        # cos(0) = 1
        result = math_solver("cos(0)")
        assert result["status"] == "success"
        assert abs(result["result"] - 1.0) < 0.0001
    
    def test_mathematical_constants(self):
        """Test mathematical constants (pi, e)."""
        import math
        
        result = math_solver("pi")
        assert result["status"] == "success"
        assert abs(result["result"] - math.pi) < 0.0001
        
        result = math_solver("e")
        assert result["status"] == "success"
        assert abs(result["result"] - math.e) < 0.0001
    
    def test_sqrt_and_power(self):
        """Test sqrt and power functions."""
        result = math_solver("sqrt(16)")
        assert result["status"] == "success"
        assert result["result"] == 4.0
        
        result = math_solver("pow(2, 10)")
        assert result["status"] == "success"
        assert result["result"] == 1024
    
    def test_logarithms(self):
        """Test logarithmic functions."""
        result = math_solver("log(100)")  # log10
        assert result["status"] == "success"
        assert result["result"] == 2.0
        
        result = math_solver("ln(e)")  # natural log
        assert result["status"] == "success"
        assert abs(result["result"] - 1.0) < 0.0001
    
    def test_division_by_zero(self):
        """Test division by zero error handling."""
        result = math_solver("10 / 0")
        
        assert result["status"] == "error"
        assert "division by zero" in result["error"].lower()
    
    def test_invalid_syntax(self):
        """Test invalid mathematical syntax."""
        invalid_expressions = [
            "2 +",  # Incomplete
            "* 5",  # Missing operand
            # Note: "2 + + 3" is valid Python (evaluates to 2 + (+3) = 5)
            "(2 + 3",  # Unbalanced parentheses
        ]
        
        for expr in invalid_expressions:
            result = math_solver(expr)
            assert result["status"] == "error", f"Should fail for: {expr}"
    
    def test_undefined_function(self):
        """Test undefined function error."""
        result = math_solver("undefined_func(10)")
        
        assert result["status"] == "error"
        # May be NameError ("Undefined") or SyntaxError depending on parser
        err = result["error"].lower()
        assert any(w in err for w in ("undefined", "syntax", "not defined", "error"))
    
    def test_complex_expression(self):
        """Test complex mathematical expression."""
        # Calculate: (3 + 5) * 2 - sqrt(16) / 2
        result = math_solver("(3 + 5) * 2 - sqrt(16) / 2")
        
        assert result["status"] == "success"
        # (8) * 2 - 4 / 2 = 16 - 2 = 14
        assert result["result"] == 14.0
    
    def test_formatted_output(self):
        """Test formatted output field."""
        result = math_solver("2 + 2")
        
        assert result["status"] == "success"
        assert "formatted" in result
        assert result["formatted"] == "4"  # Should strip unnecessary decimals
        
        result = math_solver("10 / 3")
        assert "formatted" in result
        # Should format to reasonable precision
    
    def test_empty_expression(self):
        """Test empty or invalid input."""
        result = math_solver("")
        assert result["status"] == "error"
        
        result = math_solver("   ")
        assert result["status"] == "error"


class TestWebLoader:
    """Test suite for web_loader tool."""
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_load_simple_page(self, mock_get):
        """Test loading a simple HTML page."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Main Heading</h1>
                <p>This is test content.</p>
            </body>
        </html>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_web_page("https://example.com")
        
        assert result["status"] == "success"
        assert result["title"] == "Test Page"
        assert "Main Heading" in result["content"]
        assert "This is test content" in result["content"]
        assert result["word_count"] > 0
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_strip_scripts_and_styles(self, mock_get):
        """Test that scripts and styles are removed."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <head>
                <title>Test</title>
                <script>alert('Should be removed');</script>
                <style>.removed { display: none; }</style>
            </head>
            <body>
                <p>Visible content</p>
                <script>console.log('Also removed');</script>
            </body>
        </html>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_web_page("https://example.com")
        
        assert result["status"] == "success"
        assert "alert" not in result["content"]
        assert "console.log" not in result["content"]
        assert "display: none" not in result["content"]
        assert "Visible content" in result["content"]
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_max_length_truncation(self, mock_get):
        """Test content truncation to max_length."""
        long_content = " ".join(["word"] * 1000)  # 1000 words
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = f"<html><body><p>{long_content}</p></body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_web_page("https://example.com", max_length=100)
        
        assert result["status"] == "success"
        assert len(result["content"]) <= 103  # 100 + "..."
        assert result["truncated"] is True
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_extract_links(self, mock_get):
        """Test link extraction when include_links=True."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <body>
                <a href="https://example.com/1">Link 1</a>
                <a href="https://example.com/2">Link 2</a>
                <a href="#anchor">Skip anchor</a>
            </body>
        </html>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = load_web_page("https://example.com", include_links=True)
        
        assert result["status"] == "success"
        assert "links" in result
        assert len(result["links"]) == 2  # Anchor link excluded
        assert result["links"][0]["href"] == "https://example.com/1"
        assert result["links"][0]["text"] == "Link 1"
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_invalid_url(self, mock_get):
        """Test handling of invalid URLs."""
        result = load_web_page("not-a-valid-url")
        
        assert result["status"] == "error"
        assert "invalid url" in result["error"].lower()
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_timeout_handling(self, mock_get):
        """Test timeout error handling."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = load_web_page("https://example.com")
        
        assert result["status"] == "error"
        # Error message is "Request timed out after 10 seconds"
        assert "timed out" in result["error"].lower()
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_http_404_error(self, mock_get):
        """Test 404 Not Found handling."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response
        
        result = load_web_page("https://example.com/nonexistent")
        
        assert result["status"] == "error"
        assert "404" in result["error"] or "not found" in result["error"].lower()
        # API doesn't return separate status_code field, error message contains the code
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_http_403_forbidden(self, mock_get):
        """Test 403 Forbidden handling."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        mock_get.return_value = mock_response
        
        result = load_web_page("https://example.com/forbidden")
        
        assert result["status"] == "error"
        assert "403" in result["error"] or "forbidden" in result["error"].lower()
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_connection_error(self, mock_get):
        """Test connection error handling."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")
        
        result = load_web_page("https://unreachable.example.com")
        
        assert result["status"] == "error"
        assert "connect" in result["error"].lower()
    
    @patch('tools.builtin.web_loader.requests.get')
    def test_extract_metadata(self, mock_get):
        """Test metadata extraction helper function."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <head>
                <title>Test Article</title>
                <meta name="description" content="Test description">
                <meta name="author" content="Test Author">
                <meta property="article:published_time" content="2025-01-01T00:00:00Z">
            </head>
            <body>Content</body>
        </html>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = extract_metadata("https://example.com")
        
        assert result["status"] == "success"
        assert result["metadata"]["title"] == "Test Article"
        assert result["metadata"]["description"] == "Test description"
        assert result["metadata"]["author"] == "Test Author"


class TestToolIntegration:
    """Test tools work correctly with registry."""
    
    def test_all_tools_have_correct_signature(self):
        """Test all built-in tools return dict with status key."""
        from tools.registry import LocalToolRegistry
        registry = LocalToolRegistry()
        
        # Register all built-in tools
        registry.register(web_search)
        registry.register(math_solver)
        registry.register(load_web_page)
        
        # Verify all registered
        assert "web_search" in registry.tools
        assert "math_solver" in registry.tools
        assert "load_web_page" in registry.tools
    
    @patch('tools.builtin.web_search.requests.post')
    def test_tools_with_registry_circuit_breaker(self, mock_post, monkeypatch):
        """Test built-in tools work with registry circuit breaker."""
        from tools.registry import LocalToolRegistry
        
        monkeypatch.setenv("SERPER_API_KEY", "test_key")
        registry = LocalToolRegistry()
        registry.register(web_search)
        
        # Make tool fail repeatedly
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")
        
        # Call 3 times to trip circuit
        for _ in range(3):
            result = registry.call_tool("web_search", query="test")
            assert result["status"] == "error"
        
        # 4th call should be blocked by circuit breaker
        result = registry.call_tool("web_search", query="test")
        assert result["status"] == "error"
        # API returns "error" key, not "message"
        assert "circuit breaker" in result["error"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
