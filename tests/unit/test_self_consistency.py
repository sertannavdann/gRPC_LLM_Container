"""
Unit tests for self-consistency scoring (Agent0 Phase 2).
Tests majority voting, normalization, and uncertainty detection.
"""

import pytest
import json
from core.self_consistency import (
    normalize_response,
    compute_self_consistency,
    should_use_tool_verification,
    compute_weighted_answer,
    SelfConsistencyVerifier
)
from unittest.mock import Mock, MagicMock


class TestNormalizeResponse:
    """Test response normalization for comparison."""
    
    def test_normalize_plain_text(self):
        """Test normalization of plain text responses."""
        assert normalize_response("Hello World") == "hello world"
        assert normalize_response("  UPPERCASE  ") == "uppercase"
    
    def test_normalize_json_with_content(self):
        """Test JSON responses with 'content' field."""
        response = json.dumps({"content": "The answer is 42"})
        assert normalize_response(response) == "the answer is 42"
    
    def test_normalize_json_with_answer(self):
        """Test JSON responses with 'answer' field."""
        response = json.dumps({"answer": "Paris"})
        assert normalize_response(response) == "paris"
    
    def test_normalize_json_with_result(self):
        """Test JSON responses with 'result' field."""
        response = json.dumps({"result": "SUCCESS"})
        assert normalize_response(response) == "success"
    
    def test_normalize_json_without_common_fields(self):
        """Test JSON without standard answer fields."""
        response = json.dumps({"data": {"value": 123}})
        # Should return stringified JSON
        result = normalize_response(response)
        assert "data" in result
        assert "123" in result
    
    def test_normalize_invalid_json(self):
        """Test fallback for invalid JSON."""
        response = "Not valid JSON: {broken"
        assert normalize_response(response) == "not valid json: {broken"


class TestComputeSelfConsistency:
    """Test self-consistency computation via majority voting."""
    
    def test_all_same_responses(self):
        """Test 100% agreement."""
        responses = ["answer A", "Answer A", "ANSWER A", "answer a"]
        p_hat, majority, count = compute_self_consistency(responses)
        
        assert p_hat == 1.0
        assert count == 4
    
    def test_majority_voting(self):
        """Test majority selection with partial agreement."""
        responses = ["Paris", "paris", "London", "PARIS", "Berlin"]
        p_hat, majority, count = compute_self_consistency(responses)
        
        assert p_hat == 0.6  # 3/5 agree on Paris
        assert count == 3
        assert "paris" in majority.lower()
    
    def test_no_majority_tie(self):
        """Test tie handling - first occurrence wins."""
        responses = ["A", "B", "C", "D"]
        p_hat, majority, count = compute_self_consistency(responses)
        
        assert p_hat == 0.25  # Each has 1/4
        assert count == 1
    
    def test_empty_responses(self):
        """Test empty response list."""
        p_hat, majority, count = compute_self_consistency([])
        
        assert p_hat == 0.0
        assert majority == ""
        assert count == 0
    
    def test_single_response(self):
        """Test single response - always 100% consistent."""
        responses = ["Only one answer"]
        p_hat, majority, count = compute_self_consistency(responses)
        
        assert p_hat == 1.0
        assert count == 1
    
    def test_json_responses(self):
        """Test consistency with JSON responses."""
        responses = [
            json.dumps({"content": "42"}),
            json.dumps({"content": "42"}),
            json.dumps({"content": "41"}),
            json.dumps({"answer": "42"}),
            json.dumps({"content": "42"})
        ]
        p_hat, majority, count = compute_self_consistency(responses)
        
        # 4/5 normalize to "42"
        assert p_hat == 0.8
        assert count == 4
    
    def test_no_normalization(self):
        """Test without normalization (case-sensitive)."""
        responses = ["Answer", "answer", "ANSWER"]
        p_hat, majority, count = compute_self_consistency(responses, normalize=False)
        
        # All different when case-sensitive
        assert p_hat == pytest.approx(1/3)
        assert count == 1


class TestShouldUseToolVerification:
    """Test uncertainty detection based on consistency."""
    
    def test_high_consistency_no_verification(self):
        """High consistency = confident, no verification needed."""
        assert should_use_tool_verification(0.9) is False
        assert should_use_tool_verification(0.8) is False
        assert should_use_tool_verification(0.6) is False
    
    def test_low_consistency_needs_verification(self):
        """Low consistency = uncertain, verification recommended."""
        assert should_use_tool_verification(0.5) is True
        assert should_use_tool_verification(0.3) is True
        assert should_use_tool_verification(0.0) is True
    
    def test_custom_threshold(self):
        """Test with custom threshold."""
        assert should_use_tool_verification(0.7, threshold=0.8) is True
        assert should_use_tool_verification(0.9, threshold=0.8) is False


class TestComputeWeightedAnswer:
    """Test weighted majority voting."""
    
    def test_equal_weights(self):
        """Test with equal weights (same as regular majority)."""
        responses = ["A", "A", "B"]
        weights = [1.0, 1.0, 1.0]
        
        answer, score = compute_weighted_answer(responses, weights)
        
        assert answer == "A"
        assert score == pytest.approx(2/3)
    
    def test_weighted_override_count(self):
        """Test weights overriding raw count."""
        responses = ["A", "A", "B"]
        weights = [1.0, 1.0, 5.0]  # B has high weight
        
        answer, score = compute_weighted_answer(responses, weights)
        
        assert answer.lower() == "b"
        assert score == pytest.approx(5/7)
    
    def test_default_weights(self):
        """Test default weights (all 1.0)."""
        responses = ["X", "X", "Y"]
        answer, score = compute_weighted_answer(responses)
        
        assert answer.lower() == "x"
        assert score == pytest.approx(2/3)
    
    def test_empty_responses(self):
        """Test empty input."""
        answer, score = compute_weighted_answer([])
        
        assert answer == ""
        assert score == 0.0
    
    def test_mismatched_weights_error(self):
        """Test error on mismatched weights length."""
        with pytest.raises(ValueError, match="Weights must match"):
            compute_weighted_answer(["A", "B"], [1.0])


class TestSelfConsistencyVerifier:
    """Test the verifier integration class."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock()
        client.generate_batch = Mock(return_value={
            "responses": ["42", "42", "42", "41", "42"],
            "self_consistency_score": 0.8,
            "majority_answer": "42",
            "majority_count": 4
        })
        return client
    
    def test_verify_high_confidence(self, mock_llm_client):
        """Test verification with high consistency."""
        verifier = SelfConsistencyVerifier(
            llm_client=mock_llm_client,
            num_samples=5,
            consistency_threshold=0.6
        )
        
        result = verifier.verify("What is 6 * 7?")
        
        assert result["answer"] == "42"
        assert result["consistency_score"] == 0.8
        assert result["is_confident"] is True
        assert result["needs_tool_verification"] is False
        assert len(result["all_responses"]) == 5
    
    def test_verify_low_confidence(self, mock_llm_client):
        """Test verification with low consistency."""
        mock_llm_client.generate_batch.return_value = {
            "responses": ["42", "43", "44", "45", "46"],
            "self_consistency_score": 0.2,
            "majority_answer": "42",
            "majority_count": 1
        }
        
        verifier = SelfConsistencyVerifier(
            llm_client=mock_llm_client,
            num_samples=5,
            consistency_threshold=0.6
        )
        
        result = verifier.verify("Ambiguous question?")
        
        assert result["consistency_score"] == 0.2
        assert result["is_confident"] is False
        assert result["needs_tool_verification"] is True
    
    def test_verifier_parameters_passed(self, mock_llm_client):
        """Test that parameters are properly passed to LLM client."""
        verifier = SelfConsistencyVerifier(
            llm_client=mock_llm_client,
            num_samples=7
        )
        
        verifier.verify(
            prompt="Test prompt",
            max_tokens=256,
            temperature=0.5,
            response_format="json"
        )
        
        mock_llm_client.generate_batch.assert_called_once_with(
            prompt="Test prompt",
            num_samples=7,
            max_tokens=256,
            temperature=0.5,
            response_format="json"
        )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_whitespace_normalization(self):
        """Test responses differing only in whitespace."""
        responses = [
            "  answer  ",
            "answer",
            "\tanswer\n",
            "  answer"
        ]
        p_hat, _, count = compute_self_consistency(responses)
        
        assert p_hat == 1.0
        assert count == 4
    
    def test_numeric_responses(self):
        """Test numeric responses in JSON."""
        responses = [
            json.dumps({"content": 42}),
            json.dumps({"content": 42.0}),
            json.dumps({"answer": "42"})
        ]
        p_hat, _, count = compute_self_consistency(responses)
        
        # "42" and "42.0" normalize differently
        assert count >= 2
    
    def test_nested_json(self):
        """Test nested JSON responses."""
        responses = [
            json.dumps({"data": {"result": "A"}}),
            json.dumps({"data": {"result": "A"}}),
            json.dumps({"data": {"result": "B"}})
        ]
        p_hat, _, count = compute_self_consistency(responses)
        
        assert p_hat == pytest.approx(2/3)
        assert count == 2
    
    def test_unicode_normalization(self):
        """Test Unicode handling."""
        responses = ["Café", "café", "CAFÉ"]
        p_hat, _, count = compute_self_consistency(responses)
        
        assert p_hat == 1.0  # All normalize to "café"
        assert count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
