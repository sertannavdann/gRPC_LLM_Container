"""
Self-Consistency Scoring Module (Agent0 Phase 2)

Implements self-consistency based reasoning verification:
- Sample k responses from the model
- Use majority voting to identify consensus
- Compute p̂ (proportion agreeing with majority) as uncertainty metric

Reference: Agent0 paper (arXiv:2511.16043) - Section on Tool-Integrated Reasoning
"""

import json
import logging
from collections import Counter
from typing import List, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


def normalize_response(response: str) -> str:
    """
    Normalize a response for comparison.
    Extracts answer content from JSON if applicable.
    """
    try:
        parsed = json.loads(response)
        if isinstance(parsed, dict):
            # Check common answer fields
            for key in ["content", "answer", "result", "output"]:
                if key in parsed:
                    return str(parsed[key]).strip().lower()
            # Fallback: stringify the dict
            return json.dumps(parsed, sort_keys=True).lower()
        return str(parsed).strip().lower()
    except json.JSONDecodeError:
        return response.strip().lower()


def compute_self_consistency(
    responses: List[str],
    normalize: bool = True
) -> Tuple[float, str, int]:
    """
    Compute self-consistency score via majority voting.
    
    Args:
        responses: List of k model responses
        normalize: Whether to normalize responses before comparison
    
    Returns:
        Tuple of (p̂ score, majority_answer, majority_count)
        - p̂: proportion of responses agreeing with majority [0.0, 1.0]
        - majority_answer: the most common response
        - majority_count: number of responses that agree
    """
    if not responses:
        return 0.0, "", 0
    
    if normalize:
        normalized = [normalize_response(r) for r in responses]
    else:
        normalized = [r.strip() for r in responses]
    
    counter = Counter(normalized)
    if not counter:
        return 0.0, "", 0
    
    most_common_norm, count = counter.most_common(1)[0]
    
    # Find original response matching the majority
    majority_answer = responses[0]
    for i, norm in enumerate(normalized):
        if norm == most_common_norm:
            majority_answer = responses[i]
            break
    
    # p̂ = proportion agreeing with majority
    p_hat = count / len(responses)
    
    logger.debug(f"Self-consistency: {p_hat:.2f} ({count}/{len(responses)} agree)")
    
    return p_hat, majority_answer, count


def should_use_tool_verification(
    consistency_score: float,
    threshold: float = 0.6
) -> bool:
    """
    Determine if tool verification is needed based on consistency score.
    
    When consistency is low (p̂ < threshold), the model is uncertain
    and tool-assisted verification may improve accuracy.
    
    Args:
        consistency_score: p̂ from self-consistency computation
        threshold: Minimum consistency required (default 0.6)
    
    Returns:
        True if additional tool verification is recommended
    """
    return consistency_score < threshold


def compute_weighted_answer(
    responses: List[str],
    weights: Optional[List[float]] = None
) -> Tuple[str, float]:
    """
    Compute weighted majority answer for ensemble methods.
    
    Args:
        responses: List of k model responses
        weights: Optional weights per response (e.g., from confidence scores)
    
    Returns:
        Tuple of (weighted_answer, weighted_score)
    """
    if not responses:
        return "", 0.0
    
    if weights is None:
        weights = [1.0] * len(responses)
    
    if len(weights) != len(responses):
        raise ValueError("Weights must match number of responses")
    
    normalized = [normalize_response(r) for r in responses]
    
    # Accumulate weights per unique answer
    answer_weights: Dict[str, float] = {}
    answer_originals: Dict[str, str] = {}
    
    for i, (norm, weight) in enumerate(zip(normalized, weights)):
        answer_weights[norm] = answer_weights.get(norm, 0.0) + weight
        if norm not in answer_originals:
            answer_originals[norm] = responses[i]
    
    if not answer_weights:
        return "", 0.0
    
    # Find highest weighted answer
    best_norm = max(answer_weights.keys(), key=lambda k: answer_weights[k])
    best_weight = answer_weights[best_norm]
    total_weight = sum(weights)
    
    return answer_originals[best_norm], best_weight / total_weight if total_weight > 0 else 0.0


class SelfConsistencyVerifier:
    """
    Orchestrates self-consistency verification workflow.
    Integrates with LLMClient for batch generation.
    """
    
    def __init__(
        self,
        llm_client: Any,
        num_samples: int = 5,
        consistency_threshold: float = 0.6
    ):
        """
        Initialize verifier.
        
        Args:
            llm_client: LLMClient instance for batch generation
            num_samples: Number of samples (k) to generate
            consistency_threshold: Minimum p̂ for high confidence
        """
        self.llm_client = llm_client
        self.num_samples = num_samples
        self.consistency_threshold = consistency_threshold
    
    def verify(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        response_format: str = ""
    ) -> Dict[str, Any]:
        """
        Generate samples and compute self-consistency.
        
        Returns:
            Dict with:
                - answer: Best answer (majority)
                - consistency_score: p̂
                - is_confident: True if p̂ >= threshold
                - all_responses: List of all generated responses
                - needs_tool_verification: True if consistency is low
        """
        result = self.llm_client.generate_batch(
            prompt=prompt,
            num_samples=self.num_samples,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format
        )
        
        consistency = result.get("self_consistency_score", 0.0)
        is_confident = consistency >= self.consistency_threshold
        
        return {
            "answer": result.get("majority_answer", ""),
            "consistency_score": consistency,
            "is_confident": is_confident,
            "all_responses": result.get("responses", []),
            "majority_count": result.get("majority_count", 0),
            "needs_tool_verification": not is_confident
        }
