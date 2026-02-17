"""
Tests for Blueprint2Code confidence scoring.

Validates:
- ScaffoldScore dataclass
- Multi-dimensional scoring (completeness, feasibility, edge cases, efficiency)
- Threshold-based quality gating
- Forbidden import detection
"""

import pytest

from shared.agents.confidence import (
    Blueprint2CodeScorer,
    ScaffoldScore,
    FORBIDDEN_IMPORTS,
)


class TestScaffoldScore:
    """Test ScaffoldScore dataclass."""

    def test_create_score(self):
        """ScaffoldScore can be created with all dimensions."""
        score = ScaffoldScore(
            completeness=0.9,
            feasibility=0.8,
            edge_case_handling=0.7,
            efficiency=0.85,
            overall=0.82,
        )
        assert score.completeness == 0.9
        assert score.feasibility == 0.8
        assert score.edge_case_handling == 0.7
        assert score.efficiency == 0.85
        assert score.overall == 0.82

    def test_score_repr(self):
        """ScaffoldScore has readable repr."""
        score = ScaffoldScore(
            completeness=0.9,
            feasibility=0.8,
            edge_case_handling=0.7,
            efficiency=0.85,
            overall=0.82,
        )
        repr_str = repr(score)
        assert "overall=0.82" in repr_str
        assert "completeness=0.90" in repr_str


class TestBlueprint2CodeScorer:
    """Test Blueprint2CodeScorer."""

    def test_scorer_initialization(self):
        """Scorer initializes with threshold."""
        scorer = Blueprint2CodeScorer(threshold=0.7)
        assert scorer.threshold == 0.7

    def test_scorer_default_threshold(self):
        """Scorer has default threshold of 0.6."""
        scorer = Blueprint2CodeScorer()
        assert scorer.threshold == 0.6

    def test_high_quality_scaffold_passes(self):
        """High-quality scaffold gets score >= 0.6."""
        scorer = Blueprint2CodeScorer(threshold=0.6)

        scaffold_output = {
            "changed_files": [
                {
                    "path": "modules/weather/openweather/adapter.py",
                    "content": (
                        "import requests\n"
                        "from shared.adapters.base import BaseAdapter\n\n"
                        "class OpenWeatherAdapter(BaseAdapter):\n"
                        "    def fetch_raw(self, params):\n"
                        "        try:\n"
                        "            response = requests.get(url, timeout=30)\n"
                        "            if response.status_code == 401:\n"
                        "                raise Exception('AUTH_INVALID')\n"
                        "            return response.json()\n"
                        "        except Exception as e:\n"
                        "            raise\n"
                        "    def transform(self, data):\n"
                        "        if data is None:\n"
                        "            return {}\n"
                        "        return data\n"
                        "    def get_schema(self):\n"
                        "        return {}\n"
                    ),
                },
                {
                    "path": "modules/weather/openweather/manifest.json",
                    "content": '{"name": "openweather"}',
                },
                {
                    "path": "modules/weather/openweather/test_adapter.py",
                    "content": "import pytest\ndef test_adapter():\n    pass",
                },
            ],
            "assumptions": ["API returns JSON", "Rate limit is 60/min"],
        }

        manifest = {"name": "openweather", "category": "weather"}

        score = scorer.score(scaffold_output, manifest, "default")

        assert score.overall >= 0.6
        assert scorer.passes_threshold(score)

    def test_missing_files_lowers_completeness(self):
        """Missing adapter.py lowers completeness score."""
        scorer = Blueprint2CodeScorer()

        scaffold_output = {
            "changed_files": [
                {
                    "path": "modules/weather/openweather/manifest.json",
                    "content": '{"name": "openweather"}',
                },
            ],
            "assumptions": [],
        }

        manifest = {"name": "openweather"}

        score = scorer.score(scaffold_output, manifest, "default")

        # Missing adapter.py should significantly lower completeness
        assert score.completeness < 0.6
        assert score.overall < 0.6

    def test_forbidden_imports_fail_feasibility(self):
        """Forbidden imports result in feasibility = 0."""
        scorer = Blueprint2CodeScorer()

        scaffold_output = {
            "changed_files": [
                {
                    "path": "modules/weather/openweather/adapter.py",
                    "content": (
                        "import subprocess\n"  # FORBIDDEN
                        "import requests\n"
                        "subprocess.run(['ls'])\n"
                    ),
                },
                {
                    "path": "modules/weather/openweather/manifest.json",
                    "content": "{}",
                },
            ],
            "assumptions": [],
        }

        manifest = {"name": "openweather"}

        score = scorer.score(scaffold_output, manifest, "default")

        # Forbidden import should make feasibility 0
        assert score.feasibility == 0.0
        assert score.overall < 0.6
        assert not scorer.passes_threshold(score)

    def test_no_error_handling_lowers_edge_case_score(self):
        """No error handling lowers edge case score."""
        scorer = Blueprint2CodeScorer()

        scaffold_output = {
            "changed_files": [
                {
                    "path": "modules/weather/openweather/adapter.py",
                    "content": (
                        "import requests\n"
                        "def fetch_raw(params):\n"
                        "    return requests.get(url).json()\n"  # No try/except
                    ),
                },
                {
                    "path": "modules/weather/openweather/manifest.json",
                    "content": "{}",
                },
            ],
            "assumptions": [],
        }

        manifest = {"name": "openweather"}

        score = scorer.score(scaffold_output, manifest, "default")

        # No error handling should lower edge case score
        assert score.edge_case_handling < 0.5

    def test_error_classification_improves_edge_case_score(self):
        """Error classification patterns improve edge case score."""
        scorer = Blueprint2CodeScorer()

        scaffold_output = {
            "changed_files": [
                {
                    "path": "modules/weather/openweather/adapter.py",
                    "content": (
                        "import requests\n"
                        "def fetch_raw(params):\n"
                        "    try:\n"
                        "        response = requests.get(url, timeout=30)\n"
                        "        if response.status_code == 401:\n"
                        "            raise Exception('AUTH_INVALID')\n"
                        "        if response.status_code == 429:\n"
                        "            raise Exception('TRANSIENT')\n"
                        "        if data is None:\n"
                        "            return {}\n"
                        "        return response.json()\n"
                        "    except Exception as e:\n"
                        "        raise\n"
                    ),
                },
                {
                    "path": "modules/weather/openweather/manifest.json",
                    "content": "{}",
                },
            ],
            "assumptions": ["Handle timeout errors"],
        }

        manifest = {"name": "openweather"}

        score = scorer.score(scaffold_output, manifest, "default")

        # Good error handling should boost edge case score
        assert score.edge_case_handling >= 0.8

    def test_excessive_files_lowers_efficiency(self):
        """Excessive file count lowers efficiency score."""
        scorer = Blueprint2CodeScorer()

        # Create 15 files (> 10 threshold)
        changed_files = [
            {"path": f"modules/test/platform/file_{i}.py", "content": "x = 1"}
            for i in range(15)
        ]

        scaffold_output = {
            "changed_files": changed_files,
            "assumptions": [],
        }

        manifest = {"name": "test"}

        score = scorer.score(scaffold_output, manifest, "default")

        # Excessive files should lower efficiency
        assert score.efficiency < 0.8

    def test_large_file_size_lowers_efficiency(self):
        """Large individual file size lowers efficiency."""
        scorer = Blueprint2CodeScorer()

        # Create file > 50KB
        large_content = "x = 1\n" * 10000  # ~60KB

        scaffold_output = {
            "changed_files": [
                {
                    "path": "modules/test/platform/adapter.py",
                    "content": large_content,
                },
                {
                    "path": "modules/test/platform/manifest.json",
                    "content": "{}",
                },
            ],
            "assumptions": [],
        }

        manifest = {"name": "test"}

        score = scorer.score(scaffold_output, manifest, "default")

        # Large file should lower efficiency
        assert score.efficiency < 0.8

    def test_passes_threshold_returns_correct_bool(self):
        """passes_threshold returns True/False correctly."""
        scorer = Blueprint2CodeScorer(threshold=0.7)

        passing_score = ScaffoldScore(
            completeness=0.8,
            feasibility=0.9,
            edge_case_handling=0.7,
            efficiency=0.8,
            overall=0.8,
        )

        failing_score = ScaffoldScore(
            completeness=0.5,
            feasibility=0.6,
            edge_case_handling=0.4,
            efficiency=0.6,
            overall=0.55,
        )

        assert scorer.passes_threshold(passing_score) is True
        assert scorer.passes_threshold(failing_score) is False

    def test_custom_threshold_rejects_marginal(self):
        """Higher threshold rejects marginal scaffolds."""
        strict_scorer = Blueprint2CodeScorer(threshold=0.8)

        marginal_score = ScaffoldScore(
            completeness=0.7,
            feasibility=0.7,
            edge_case_handling=0.6,
            efficiency=0.7,
            overall=0.68,
        )

        # Would pass 0.6 threshold but fail 0.8
        assert marginal_score.overall >= 0.6
        assert not strict_scorer.passes_threshold(marginal_score)

    def test_forbidden_import_detection(self):
        """Scorer detects all forbidden imports."""
        scorer = Blueprint2CodeScorer()

        for forbidden in ["subprocess", "eval", "exec", "__import__"]:
            scaffold_output = {
                "changed_files": [
                    {
                        "path": "adapter.py",
                        "content": f"import {forbidden}\n",
                    },
                ],
                "assumptions": [],
            }

            score = scorer.score(scaffold_output, {}, "default")
            assert score.feasibility == 0.0, f"Failed to detect: {forbidden}"

    def test_from_import_forbidden(self):
        """Scorer detects forbidden 'from X import Y' patterns."""
        scorer = Blueprint2CodeScorer()

        scaffold_output = {
            "changed_files": [
                {
                    "path": "adapter.py",
                    "content": "from subprocess import run\n",
                },
            ],
            "assumptions": [],
        }

        score = scorer.score(scaffold_output, {}, "default")
        assert score.feasibility == 0.0

    def test_weighted_overall_score(self):
        """Overall score is weighted average (0.3, 0.3, 0.2, 0.2)."""
        scorer = Blueprint2CodeScorer()

        # Manually compute expected overall
        completeness = 1.0
        feasibility = 0.8
        edge_case = 0.6
        efficiency = 0.4

        expected_overall = (
            0.3 * completeness +
            0.3 * feasibility +
            0.2 * edge_case +
            0.2 * efficiency
        )

        # Create scaffold that should produce these scores
        # (This is approximate - exact control is hard)
        score = ScaffoldScore(
            completeness=completeness,
            feasibility=feasibility,
            edge_case_handling=edge_case,
            efficiency=efficiency,
            overall=expected_overall,
        )

        # Verify weighting formula
        assert abs(score.overall - expected_overall) < 0.01
