import pytest

from aquaculture_manuscript_mcp.tools import power

SRC = "pilot trial 2025, cage SGR SD"


def test_two_sample_t_textbook_value():
    # Cohen (1988): d = 0.5, alpha = 0.05, power = 0.8 -> 64 per group
    r = power.calculate_sample_size("two_sample_t", 0.5, SRC)
    assert r["units_per_group"] == 64
    assert r["effect_size_source"] == SRC


def test_one_way_anova_medium_effect():
    # f = 0.25, k = 3, alpha 0.05, power 0.8 -> ~159 total (G*Power), 53 per group
    r = power.calculate_sample_size("one_way_anova", 0.25, SRC, k_groups=3)
    assert 52 <= r["units_per_group"] <= 54


def test_effect_size_source_is_required():
    with pytest.raises(ValueError, match="effect_size_source is required"):
        power.calculate_sample_size("two_sample_t", 0.5, "  ")


def test_achieved_power_is_consistent_with_sample_size():
    n = power.calculate_sample_size("two_sample_t", 1.2, SRC)["units_per_group"]
    assert power.calculate_achieved_power("two_sample_t", 1.2, SRC, n)["power"] >= 0.8
    assert power.calculate_achieved_power("two_sample_t", 1.2, SRC, 3)["adequate_at_0.8"] is False


def test_bad_inputs():
    with pytest.raises(ValueError):
        power.calculate_sample_size("chi_square", 0.5, SRC)
    with pytest.raises(ValueError):
        power.calculate_sample_size("two_sample_t", -0.5, SRC)
