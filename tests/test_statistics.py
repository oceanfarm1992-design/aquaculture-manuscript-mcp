import pytest

from aquaculture_manuscript_mcp.tools import statistics as stats_tool

# Fixed seed data so expected values are hand-verifiable, not dependent on
# random generation at test time.
GROUP_A = [10.1, 10.5, 9.8, 10.2, 10.0]
GROUP_B = [12.3, 12.1, 12.6, 12.0, 12.4]
GROUP_C = [8.5, 8.7, 8.4, 8.6, 8.3]


def test_descriptive_stats():
    result = stats_tool.descriptive_stats(GROUP_A)
    assert result["n"] == 5
    assert result["mean"] == pytest.approx(10.12, abs=0.01)
    assert result["sd"] > 0
    assert result["sem"] == pytest.approx(result["sd"] / (5**0.5))


def test_descriptive_stats_requires_two_values():
    with pytest.raises(ValueError, match="at least 2"):
        stats_tool.descriptive_stats([5.0])


def test_check_normality_returns_shapiro_fields():
    result = stats_tool.check_normality(GROUP_A + GROUP_B + GROUP_C)
    assert result["test"] == "Shapiro-Wilk"
    assert 0 <= result["p_value"] <= 1


def test_check_variance_homogeneity():
    result = stats_tool.check_variance_homogeneity([GROUP_A, GROUP_B, GROUP_C])
    assert result["test"] == "Levene"
    assert 0 <= result["p_value"] <= 1


def test_ttest_detects_clear_difference():
    # Group B is obviously higher than Group A -> should be significant.
    result = stats_tool.analyze_ttest(GROUP_B, GROUP_A)
    assert result["significant_at_alpha_0.05"] is True
    assert result["mean_difference"] > 0


def test_ttest_no_difference_for_identical_groups():
    result = stats_tool.analyze_ttest(GROUP_A, GROUP_A)
    assert result["statistic"] == pytest.approx(0.0, abs=1e-9)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-9)


def test_ttest_paired_requires_equal_length():
    with pytest.raises(ValueError, match="equal-length"):
        stats_tool.analyze_ttest(GROUP_A, GROUP_A[:3], paired=True)


def test_anova_detects_group_differences():
    result = stats_tool.analyze_anova([GROUP_A, GROUP_B, GROUP_C], ["A", "B", "C"])
    assert result["significant_at_alpha_0.05"] is True
    assert result["group_means"]["B"] > result["group_means"]["A"] > result["group_means"]["C"]


def test_anova_label_mismatch_raises():
    with pytest.raises(ValueError, match="group_labels"):
        stats_tool.analyze_anova([GROUP_A, GROUP_B], ["only_one_label"])


def test_kruskal_wallis_detects_difference():
    result = stats_tool.analyze_kruskal_wallis([GROUP_A, GROUP_B, GROUP_C], ["A", "B", "C"])
    assert result["significant_at_alpha_0.05"] is True


def test_posthoc_tukey_requires_three_groups():
    with pytest.raises(ValueError, match="3\\+ groups"):
        stats_tool.analyze_posthoc_tukey([GROUP_A, GROUP_B], ["A", "B"])


def test_posthoc_tukey_pairwise_matrix_is_complete():
    result = stats_tool.analyze_posthoc_tukey([GROUP_A, GROUP_B, GROUP_C], ["A", "B", "C"])
    # 3 groups -> exactly 3 pairwise comparisons (AB, AC, BC).
    assert len(result["pairwise_comparisons"]) == 3
    pairs = {frozenset((c["group1"], c["group2"])) for c in result["pairwise_comparisons"]}
    assert pairs == {frozenset(("A", "B")), frozenset(("A", "C")), frozenset(("B", "C"))}
    # All three groups are well-separated by construction -> all significant.
    assert all(c["significant_at_alpha_0.05"] for c in result["pairwise_comparisons"])


def test_cohens_d_large_effect():
    result = stats_tool.calculate_effect_size_cohens_d(GROUP_B, GROUP_A)
    assert result["cohens_d"] > 0.8
    assert result["magnitude"] == "large"


def test_cohens_d_zero_for_identical_groups():
    # Identical groups -> pooled SD is nonzero (within-group variance still
    # exists) but mean difference is zero, so d should be ~0, not an error.
    result = stats_tool.calculate_effect_size_cohens_d(GROUP_A, GROUP_A)
    assert result["cohens_d"] == pytest.approx(0.0, abs=1e-9)


def test_eta_squared_large_for_well_separated_groups():
    result = stats_tool.calculate_eta_squared([GROUP_A, GROUP_B, GROUP_C])
    assert result["eta_squared"] > 0.14
    assert result["magnitude"] == "large"


def test_confidence_interval_contains_mean():
    result = stats_tool.calculate_confidence_interval(GROUP_A, confidence=0.95)
    assert result["ci_lower"] < result["mean"] < result["ci_upper"]


def test_confidence_interval_bad_confidence_raises():
    with pytest.raises(ValueError, match="confidence"):
        stats_tool.calculate_confidence_interval(GROUP_A, confidence=1.5)


def test_validate_group_rejects_nan():
    with pytest.raises(ValueError, match="NaN"):
        stats_tool.descriptive_stats([1.0, float("nan"), 3.0])
