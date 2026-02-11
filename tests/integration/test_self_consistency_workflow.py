"""
Integration tests for Self-Consistency workflow.

Tests the Agent0 Phase 2 self-consistency scoring:
- Generate multiple samples
- Majority voting
- Uncertainty detection triggering tool use

Requires Docker services to be running with ENABLE_SELF_CONSISTENCY=true.
"""

import pytest
import logging
import os
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from integration.docker_manager import DockerComposeManager

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def docker_manager():
    """Docker manager for self-consistency tests."""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.yaml"
    
    try:
        manager = DockerComposeManager(str(compose_file))
    except FileNotFoundError as e:
        pytest.skip(f"Docker not available: {e}")
    
    # Verify LLM service is running
    if not manager.wait_for_service("llm_service", 50051, timeout=10):
        pytest.skip("llm_service not available. Please start with 'make up'.")
    
    yield manager


class TestSelfConsistencyCore:
    """Test core self-consistency functions."""
    
    def test_compute_self_consistency_all_same(self):
        """Test consistency with identical responses."""
        from core.self_consistency import compute_self_consistency
        
        responses = ["Paris", "Paris", "Paris", "Paris", "Paris"]
        p_hat, majority, count = compute_self_consistency(responses)
        
        assert p_hat == 1.0
        assert count == 5
        assert "paris" in majority.lower()
        
        logger.info(f"✓ All same: p̂={p_hat}, count={count}")
    
    def test_compute_self_consistency_mixed(self):
        """Test consistency with mixed responses."""
        from core.self_consistency import compute_self_consistency
        
        responses = ["Paris", "London", "Paris", "Berlin", "Paris"]
        p_hat, majority, count = compute_self_consistency(responses)
        
        assert p_hat == 0.6  # 3/5
        assert count == 3
        
        logger.info(f"✓ Mixed: p̂={p_hat}, count={count}")
    
    def test_should_use_tool_verification(self):
        """Test uncertainty detection threshold."""
        from core.self_consistency import should_use_tool_verification
        
        # High consistency = confident, no tools needed
        assert should_use_tool_verification(0.8) is False
        
        # Low consistency = uncertain, tools recommended
        assert should_use_tool_verification(0.4) is True
        
        # At threshold
        assert should_use_tool_verification(0.6) is False
        assert should_use_tool_verification(0.59) is True
        
        logger.info("✓ Tool verification threshold works")


class TestSelfConsistencyVerifier:
    """Test SelfConsistencyVerifier class."""
    
    def test_verifier_with_mock_client(self):
        """Test verifier with mock LLM client."""
        from core.self_consistency import SelfConsistencyVerifier
        from unittest.mock import Mock
        
        mock_client = Mock()
        mock_client.generate_batch.return_value = {
            "responses": ["42", "42", "42", "41", "42"],
            "self_consistency_score": 0.8,
            "majority_answer": "42",
            "majority_count": 4
        }
        
        verifier = SelfConsistencyVerifier(
            llm_client=mock_client,
            num_samples=5,
            consistency_threshold=0.6
        )
        
        result = verifier.verify("What is 6 * 7?")
        
        assert result["is_confident"] is True
        assert result["needs_tool_verification"] is False
        assert result["consistency_score"] == 0.8
        
        logger.info(f"✓ Verifier result: {result}")
    
    def test_verifier_low_confidence(self):
        """Test verifier with low confidence scenario."""
        from core.self_consistency import SelfConsistencyVerifier
        from unittest.mock import Mock
        
        mock_client = Mock()
        mock_client.generate_batch.return_value = {
            "responses": ["A", "B", "C", "D", "E"],
            "self_consistency_score": 0.2,
            "majority_answer": "A",
            "majority_count": 1
        }
        
        verifier = SelfConsistencyVerifier(
            llm_client=mock_client,
            num_samples=5,
            consistency_threshold=0.6
        )
        
        result = verifier.verify("Ambiguous question")
        
        assert result["is_confident"] is False
        assert result["needs_tool_verification"] is True
        
        logger.info(f"✓ Low confidence detected: {result}")


class TestLLMBatchGeneration:
    """Test LLM batch generation for self-consistency (requires services)."""
    
    def test_generate_batch_direct(self, docker_manager):
        """Test direct batch generation via LLM client."""
        from shared.clients.llm_client import LLMClient
        
        client = LLMClient(host="localhost", port=50051)
        
        result = client.generate_batch(
            prompt="What is 2 + 2? Answer with just the number.",
            num_samples=3,
            max_tokens=10,
            temperature=0.7
        )
        
        assert result is not None
        assert "responses" in result
        assert len(result["responses"]) == 3
        assert "self_consistency_score" in result
        
        logger.info(f"✓ Batch generation: {len(result['responses'])} samples, "
                   f"consistency={result['self_consistency_score']:.2f}")
    
    def test_batch_with_json_format(self, docker_manager):
        """Test batch generation with JSON response format."""
        from shared.clients.llm_client import LLMClient
        
        client = LLMClient(host="localhost", port=50051)
        
        result = client.generate_batch(
            prompt='Answer the question in JSON format: {"answer": "your answer"}. Question: What is the capital of France?',
            num_samples=3,
            max_tokens=50,
            temperature=0.5,
            response_format="json"
        )
        
        assert result is not None
        assert len(result["responses"]) == 3
        
        # All responses should be valid JSON
        import json
        for resp in result["responses"]:
            try:
                parsed = json.loads(resp)
                assert "answer" in parsed or len(parsed) > 0
            except json.JSONDecodeError:
                pytest.fail(f"Response is not valid JSON: {resp}")
        
        logger.info(f"✓ JSON batch generation: consistency={result['self_consistency_score']:.2f}")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.self_consistency,
]
