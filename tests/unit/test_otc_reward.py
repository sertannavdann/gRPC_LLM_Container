"""
Unit tests for OTC reward function.

Tests the OTC-GRPO reward computation including:
- Peak reward at m==n
- Symmetry penalties for undershoot/overshoot
- Edge cases (m=0, n=0)
- Composite reward with success/failure
- Run-unit normalization
- Frozen dataclass immutability
"""
import pytest
from shared.billing.otc_reward import (
    OTCRewardConfig,
    otc_tool_reward,
    compute_composite_reward,
)


class TestOTCToolReward:
    """Test otc_tool_reward() properties."""

    def test_peak_at_optimal(self):
        """Reward peaks at m==n (should return ~1.0)."""
        reward = otc_tool_reward(m=3, n=3.0, c=2.0)
        assert 0.95 <= reward <= 1.0, f"Expected peak near 1.0, got {reward}"

    def test_undershoot_penalized(self):
        """Reward for undershoot (m < n) is less than optimal."""
        r_undershoot = otc_tool_reward(m=1, n=3.0, c=2.0)
        r_optimal = otc_tool_reward(m=3, n=3.0, c=2.0)
        assert r_undershoot < r_optimal, "Undershoot should be penalized"

    def test_overshoot_penalized(self):
        """Reward for overshoot (m > n) is less than optimal."""
        r_overshoot = otc_tool_reward(m=5, n=3.0, c=2.0)
        r_optimal = otc_tool_reward(m=3, n=3.0, c=2.0)
        assert r_overshoot < r_optimal, "Overshoot should be penalized"

    def test_edge_case_both_zero(self):
        """m=0, n=0 returns 1.0 (no calls needed, none made)."""
        reward = otc_tool_reward(m=0, n=0.0, c=2.0)
        assert reward == 1.0

    def test_edge_case_n_zero_m_positive(self):
        """n=0, m>0 returns cosine decay (unnecessary calls)."""
        reward = otc_tool_reward(m=2, n=0.0, c=2.0)
        assert 0.0 < reward < 1.0, "Should decay for unnecessary calls"

    def test_symmetric_penalty(self):
        """Verify penalty roughly symmetric around optimal."""
        r_optimal = otc_tool_reward(m=3, n=3.0, c=2.0)
        r_minus_1 = otc_tool_reward(m=2, n=3.0, c=2.0)
        r_plus_1 = otc_tool_reward(m=4, n=3.0, c=2.0)
        # Not exact symmetry, but both should be penalized relative to optimal
        assert r_minus_1 < r_optimal, "Undershoot should be less than optimal"
        assert r_plus_1 < r_optimal, "Overshoot should be less than optimal"


class TestCompositeReward:
    """Test compute_composite_reward() integration."""

    def test_success_with_optimal_calls(self):
        """Success at m==n should yield high composite reward."""
        result = compute_composite_reward(
            tool_calls=3,
            run_units=0.9,  # near baseline
            success=True,
            optimal_n=3.0,
            cfg=OTCRewardConfig(alpha=1.0, beta=0.1, smooth_c=2.0, ru_baseline=1.0),
        )
        assert result["r_correctness"] == 1.0
        assert result["r_tool"] > 0.95
        assert result["r_composite"] > 0.8, "High success should yield high composite"

    def test_failure_yields_negative_composite(self):
        """Failure should result in negative composite (cost penalty only)."""
        result = compute_composite_reward(
            tool_calls=3,
            run_units=1.5,
            success=False,
            optimal_n=3.0,
            cfg=OTCRewardConfig(alpha=1.0, beta=0.1, smooth_c=2.0, ru_baseline=1.0),
        )
        assert result["r_correctness"] == 0.0
        assert result["r_composite"] < 0.0, "Failure with cost should be negative"

    def test_run_units_normalization_caps_at_5x(self):
        """Run-unit cost should cap at 5x baseline."""
        result = compute_composite_reward(
            tool_calls=3,
            run_units=10.0,  # 10x baseline
            success=True,
            optimal_n=3.0,
            cfg=OTCRewardConfig(alpha=1.0, beta=0.1, smooth_c=2.0, ru_baseline=1.0),
        )
        # r_cost should be capped: min(10.0/1.0, 5.0) / 5.0 = 1.0
        assert result["r_cost"] == 1.0

    def test_return_type_has_all_components(self):
        """Verify return dict has all required keys."""
        result = compute_composite_reward(
            tool_calls=2,
            run_units=0.5,
            success=True,
            optimal_n=2.0,
        )
        assert "r_correctness" in result
        assert "r_tool" in result
        assert "r_cost" in result
        assert "r_composite" in result

    def test_reward_components_rounded(self):
        """Verify reward components are rounded to 6 decimals."""
        result = compute_composite_reward(
            tool_calls=3,
            run_units=0.333333333,
            success=True,
            optimal_n=3.0,
        )
        # Check precision (should have at most 6 decimal places)
        for key in ["r_tool", "r_cost", "r_composite"]:
            str_val = str(result[key])
            if "." in str_val:
                decimals = len(str_val.split(".")[1])
                assert decimals <= 6, f"{key} has more than 6 decimals: {str_val}"


class TestOTCRewardConfig:
    """Test OTCRewardConfig dataclass."""

    def test_frozen_dataclass(self):
        """OTCRewardConfig should be immutable (frozen=True)."""
        cfg = OTCRewardConfig(alpha=1.0, beta=0.1)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            cfg.alpha = 2.0

    def test_default_values(self):
        """Verify default configuration values."""
        cfg = OTCRewardConfig()
        assert cfg.alpha == 1.0
        assert cfg.beta == 0.1
        assert cfg.smooth_c == 2.0
        assert cfg.ru_baseline == 1.0

    def test_custom_values(self):
        """Verify custom configuration values."""
        cfg = OTCRewardConfig(alpha=0.8, beta=0.2, smooth_c=3.0, ru_baseline=2.0)
        assert cfg.alpha == 0.8
        assert cfg.beta == 0.2
        assert cfg.smooth_c == 3.0
        assert cfg.ru_baseline == 2.0
