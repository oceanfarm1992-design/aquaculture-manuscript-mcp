"""Validated against a real 18-tank factorial tilapia trial (2 diets x 3
feeding frequencies) and an independently hand-written statsmodels script on
that same dataset — not synthetic toy numbers. Ground truth: F=252.807
(diet), F=199.156 (frequency), F=11.266 (interaction) for SGR."""

import pytest

from aquaculture_manuscript_mcp.tools import statistics as stats_tool

DIET = ["30%"] * 9 + ["38%"] * 9
FREQ = (["2x"] * 3 + ["3x"] * 3 + ["4x"] * 3) * 2
SGR = [
    2.05, 2.01, 2.07, 2.20, 2.16, 2.22, 2.25, 2.25, 2.27,
    2.14, 2.18, 2.13, 2.43, 2.43, 2.40, 2.48, 2.45, 2.50,
]
TAN = [
    0.42, 0.45, 0.40, 0.58, 0.61, 0.55, 0.78, 0.82, 0.75,
    0.48, 0.51, 0.46, 0.68, 0.72, 0.66, 0.95, 0.98, 0.92,
]


def test_two_way_anova_matches_real_trial_ground_truth():
    result = stats_tool.analyze_two_way_anova(
        values=SGR, factor1=DIET, factor2=FREQ,
        factor1_name="Diet_Protein", factor2_name="Feed_Freq",
    )
    terms = result["terms"]
    assert terms["Diet_Protein"]["f_statistic"] == pytest.approx(252.807, abs=0.01)
    assert terms["Feed_Freq"]["f_statistic"] == pytest.approx(199.156, abs=0.01)
    assert terms["Diet_Protein:Feed_Freq (interaction)"]["f_statistic"] == pytest.approx(11.266, abs=0.01)
    assert terms["Diet_Protein"]["eta_squared"] == pytest.approx(0.36871, abs=0.001)
    assert terms["Feed_Freq"]["eta_squared"] == pytest.approx(0.58092, abs=0.001)
    assert terms["Diet_Protein:Feed_Freq (interaction)"]["significant_at_alpha_0.05"] is True


def test_two_way_anova_residual_has_no_f_or_p():
    result = stats_tool.analyze_two_way_anova(values=SGR, factor1=DIET, factor2=FREQ)
    assert result["terms"]["Residual"]["f_statistic"] is None
    assert result["terms"]["Residual"]["p_value"] is None


def test_two_way_anova_mismatched_lengths_raises():
    with pytest.raises(ValueError, match="same length"):
        stats_tool.analyze_two_way_anova(values=SGR, factor1=DIET[:5], factor2=FREQ)


def test_two_way_anova_too_few_observations_raises():
    with pytest.raises(ValueError, match="at least 4"):
        stats_tool.analyze_two_way_anova(values=[1.0, 2.0], factor1=["a", "b"], factor2=["x", "y"])


def test_two_way_anova_factor_names_never_reach_formula_string():
    # Factor names containing characters that would break a patsy formula
    # (or attempt injection) must not affect the computation - only "f1"/"f2"
    # are ever used internally.
    result = stats_tool.analyze_two_way_anova(
        values=SGR, factor1=DIET, factor2=FREQ,
        factor1_name="weird '); DROP TABLE x -- name",
        factor2_name="also + weird * name",
    )
    terms = result["terms"]
    assert terms["weird '); DROP TABLE x -- name"]["f_statistic"] == pytest.approx(252.807, abs=0.01)


def test_pearson_correlation_matches_real_trial_ground_truth():
    freq_numeric = [2, 2, 2, 3, 3, 3, 4, 4, 4] * 2
    result = stats_tool.calculate_pearson_correlation(freq_numeric, TAN)
    assert result["r"] == pytest.approx(0.9321, abs=0.001)
    assert result["n"] == 18
    assert result["significant_at_alpha_0.05"] is True


def test_pearson_correlation_mismatched_lengths_raises():
    with pytest.raises(ValueError, match="same length"):
        stats_tool.calculate_pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0])
