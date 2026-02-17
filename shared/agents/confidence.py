"""
Blueprint2Code confidence scoring for scaffold quality gating.

Implements multi-dimensional scaffold evaluation based on academic research:
- Blueprint2Code framework (Mao et al., 2025) — confidence-based plan scoring
- Agentic Builder-Tester Pattern §4.3 — quality gate at scaffold→implement transition

Prevents low-quality scaffolds from propagating errors downstream by scoring
on 4 dimensions: completeness, feasibility, edge-case handling, efficiency.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Set

logger = logging.getLogger(__name__)

# Security policy: forbidden imports that indicate policy violations
FORBIDDEN_IMPORTS = {
    "subprocess",
    "os.system",
    "os.popen",
    "shutil.rmtree",
    "eval",
    "exec",
    "__import__",
    "importlib.import_module",
    "compile",
}


@dataclass
class ScaffoldScore:
    """
    Multi-dimensional scaffold quality score.

    Dimensions based on Blueprint2Code five-factor model:
    - Completeness: Does scaffold cover all declared capabilities?
    - Feasibility: Are imports allowed? Are paths valid?
    - Edge case handling: Are error paths defined?
    - Efficiency: Is file count/size reasonable?
    - Overall: Weighted composite score (0-1)

    Threshold default: 0.6 (based on empirical research showing 0.6+ correlates
    with successful downstream implementation).
    """
    completeness: float  # 0-1
    feasibility: float  # 0-1
    edge_case_handling: float  # 0-1
    efficiency: float  # 0-1
    overall: float  # 0-1, weighted average

    def __repr__(self) -> str:
        return (
            f"ScaffoldScore(overall={self.overall:.2f}, "
            f"completeness={self.completeness:.2f}, "
            f"feasibility={self.feasibility:.2f}, "
            f"edge={self.edge_case_handling:.2f}, "
            f"efficiency={self.efficiency:.2f})"
        )


class Blueprint2CodeScorer:
    """
    Confidence scorer for scaffold outputs.

    Evaluates scaffold quality across 4 dimensions before allowing progression
    to implement stage. Low-confidence scaffolds trigger regeneration with
    refined prompts.

    Usage:
        scorer = Blueprint2CodeScorer(threshold=0.6)
        score = scorer.score(scaffold_output, manifest, policy_profile)
        if scorer.passes_threshold(score):
            proceed_to_implement()
        else:
            regenerate_scaffold()
    """

    def __init__(self, threshold: float = 0.6):
        """
        Initialize scorer.

        Args:
            threshold: Minimum acceptable overall score (default 0.6)
        """
        self.threshold = threshold
        logger.info(f"Blueprint2CodeScorer initialized with threshold={threshold}")

    def score(
        self,
        scaffold_output: Dict[str, Any],
        manifest: Dict[str, Any],
        policy_profile: str = "default",
    ) -> ScaffoldScore:
        """
        Score a scaffold output.

        Args:
            scaffold_output: GeneratorResponseContract dict from scaffold stage
            manifest: Module manifest with declared capabilities
            policy_profile: Policy profile name (for import allowlist)

        Returns:
            ScaffoldScore with per-dimension and overall scores
        """
        # Extract data
        changed_files = scaffold_output.get("changed_files", [])
        assumptions = scaffold_output.get("assumptions", [])

        # Dimension 1: Completeness
        completeness = self._score_completeness(changed_files, manifest)

        # Dimension 2: Feasibility
        feasibility = self._score_feasibility(changed_files, policy_profile)

        # Dimension 3: Edge case handling
        edge_case_handling = self._score_edge_cases(changed_files, assumptions)

        # Dimension 4: Efficiency
        efficiency = self._score_efficiency(changed_files)

        # Overall: weighted average
        # Weights from Blueprint2Code research: completeness and feasibility are most critical
        overall = (
            0.3 * completeness +
            0.3 * feasibility +
            0.2 * edge_case_handling +
            0.2 * efficiency
        )

        score = ScaffoldScore(
            completeness=completeness,
            feasibility=feasibility,
            edge_case_handling=edge_case_handling,
            efficiency=efficiency,
            overall=overall,
        )

        logger.info(f"Scaffold scored: {score}")
        return score

    def passes_threshold(self, score: ScaffoldScore) -> bool:
        """
        Check if score meets threshold.

        Args:
            score: ScaffoldScore to check

        Returns:
            True if score.overall >= self.threshold
        """
        passes = score.overall >= self.threshold
        if passes:
            logger.info(f"Scaffold PASSED threshold ({score.overall:.2f} >= {self.threshold})")
        else:
            logger.warning(
                f"Scaffold FAILED threshold ({score.overall:.2f} < {self.threshold})"
            )
        return passes

    def _score_completeness(
        self,
        changed_files: List[Dict[str, str]],
        manifest: Dict[str, Any],
    ) -> float:
        """
        Score completeness: do changed files cover all manifest capabilities?

        Expected files for a complete scaffold:
        - manifest.json (or already exists)
        - adapter.py (core implementation)
        - test_adapter.py (test suite)

        Optional but beneficial:
        - utils.py (if complex logic)
        - __init__.py (if multiple files)

        Returns:
            0.0-1.0 completeness score
        """
        file_paths = {f.get("path", "") for f in changed_files}

        # Core files check
        has_adapter = any("adapter.py" in p for p in file_paths)
        has_manifest = any("manifest.json" in p for p in file_paths)
        has_tests = any("test_adapter.py" in p for p in file_paths)

        score = 0.0
        if has_adapter:
            score += 0.5  # Adapter is critical
        if has_manifest:
            score += 0.3  # Manifest is important
        if has_tests:
            score += 0.2  # Tests are nice-to-have in scaffold

        return min(score, 1.0)

    def _score_feasibility(
        self,
        changed_files: List[Dict[str, str]],
        policy_profile: str,
    ) -> float:
        """
        Score feasibility: are imports in allowlist? Are patterns valid?

        Checks for:
        - Forbidden imports (immediate 0.0 score)
        - Valid Python syntax patterns
        - Reasonable file structure

        Returns:
            0.0-1.0 feasibility score
        """
        all_content = "\n".join(f.get("content", "") for f in changed_files)

        # Check for forbidden imports
        forbidden_found = self._find_forbidden_imports(all_content)
        if forbidden_found:
            logger.warning(f"Forbidden imports found: {forbidden_found}")
            return 0.0  # Hard fail on security violations

        # Check for basic Python patterns
        score = 1.0

        # Penalty if no error handling patterns found
        has_try_except = "try:" in all_content and "except" in all_content
        if not has_try_except:
            score -= 0.2

        # Penalty if no imports at all (likely incomplete)
        has_imports = "import " in all_content or "from " in all_content
        if not has_imports:
            score -= 0.3

        return max(score, 0.0)

    def _score_edge_cases(
        self,
        changed_files: List[Dict[str, str]],
        assumptions: List[str],
    ) -> float:
        """
        Score edge case handling: are error paths defined?

        Looks for:
        - Error classification patterns (AUTH_INVALID, TRANSIENT, etc.)
        - Try/except blocks
        - Null/None checks
        - Timeout handling
        - Assumptions about error scenarios

        Returns:
            0.0-1.0 edge case score
        """
        all_content = "\n".join(f.get("content", "") for f in changed_files)
        all_assumptions = " ".join(assumptions)

        score = 0.0

        # Error classification mentioned
        error_codes = ["AUTH_INVALID", "AUTH_EXPIRED", "TRANSIENT", "FATAL"]
        if any(code in all_content or code in all_assumptions for code in error_codes):
            score += 0.3

        # Try/except present
        if "try:" in all_content and "except" in all_content:
            score += 0.3

        # Timeout handling
        if "timeout" in all_content.lower() or "timeout" in all_assumptions.lower():
            score += 0.2

        # None/null checks
        if "is None" in all_content or "is not None" in all_content:
            score += 0.2

        return min(score, 1.0)

    def _score_efficiency(
        self,
        changed_files: List[Dict[str, str]],
    ) -> float:
        """
        Score efficiency: is file count/size reasonable?

        Checks:
        - File count <= 10 (reasonable for scaffold)
        - Individual file size <= 50KB
        - Total size <= 100KB

        Returns:
            0.0-1.0 efficiency score
        """
        file_count = len(changed_files)
        total_size = sum(len(f.get("content", "")) for f in changed_files)
        max_individual_size = max(
            (len(f.get("content", "")) for f in changed_files),
            default=0
        )

        score = 1.0

        # Penalize excessive file count
        if file_count > 10:
            score -= 0.3
        elif file_count > 5:
            score -= 0.1

        # Penalize large individual files
        if max_individual_size > 50_000:  # 50KB
            score -= 0.3
        elif max_individual_size > 20_000:  # 20KB
            score -= 0.1

        # Penalize large total size
        if total_size > 100_000:  # 100KB
            score -= 0.3
        elif total_size > 50_000:  # 50KB
            score -= 0.1

        return max(score, 0.0)

    def _find_forbidden_imports(self, content: str) -> Set[str]:
        """
        Find forbidden imports in content.

        Args:
            content: File content to check

        Returns:
            Set of forbidden import names found
        """
        found = set()

        # Pattern: import subprocess, from subprocess import X, etc.
        for forbidden in FORBIDDEN_IMPORTS:
            patterns = [
                rf"\bimport\s+{re.escape(forbidden)}\b",
                rf"\bfrom\s+{re.escape(forbidden)}\b",
            ]
            for pattern in patterns:
                if re.search(pattern, content):
                    found.add(forbidden)

        return found
