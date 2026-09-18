"""Real statistical computation via scipy/statsmodels — the model never
computes a p-value, F-statistic, or effect size itself; it only interprets
what this module returns.

Scope note: this module deliberately does NOT auto-generate compact-letter
displays (the a/b/c superscript groups aquaculture tables use). Naive greedy
letter-assignment algorithms get this wrong in cases where a group must share
a letter with two other groups that are themselves significantly different
from each other (this is why R's multcompView package exists as dedicated,
carefully-tested machinery rather than a one-line greedy loop). Getting it
wrong would silently mislabel a published table, which is a worse outcome
than not having the feature. Instead, analyze_posthoc_tukey returns the full
pairwise significance matrix with adjusted p-values — correct and
unambiguous — for a human (or a future, properly-verified CLD
implementation) to turn into letters.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.multicomp import pairwise_tukeyhsd


def _validate_group(values: list[float], name: str = "values") -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size < 2:
        raise ValueError(f"{name} needs at least 2 observations, got {arr.size}")
    if np.any(np.isnan(arr)):
        raise ValueError(f"{name} contains NaN — remove or impute missing values before analysis")
    return arr


def descriptive_stats(values: list[float]) -> dict:
    """n, mean, SD, SEM, min, max, coefficient of variation."""
    arr = _validate_group(values)
    mean = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1))
    n = int(arr.size)
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "sem": sd / np.sqrt(n),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "cv_percent": (sd / mean * 100) if mean != 0 else None,
    }


def check_normality(values: list[float]) -> dict:
    """Shapiro-Wilk test for normality. Reliable for n roughly 3-5000;
    outside that range scipy still runs it but interpret cautiously."""
    arr = _validate_group(values)
    if arr.size < 3:
        raise ValueError("Shapiro-Wilk requires at least 3 observations")
    statistic, p_value = scipy_stats.shapiro(arr)
    return {
        "test": "Shapiro-Wilk",
        "statistic": float(statistic),
        "p_value": float(p_value),
        "normal_at_alpha_0.05": bool(p_value > 0.05),
        "n": int(arr.size),
        "note": "n < 3 or n very large reduces this test's reliability; inspect a Q-Q plot for borderline cases.",
    }


def check_variance_homogeneity(groups: list[list[float]]) -> dict:
    """Levene's test for equal variances across 2+ groups (robust to
    non-normality, unlike Bartlett's test)."""
    if len(groups) < 2:
        raise ValueError("need at least 2 groups")
    arrays = [_validate_group(g, f"group {i}") for i, g in enumerate(groups)]
    statistic, p_value = scipy_stats.levene(*arrays)
    return {
        "test": "Levene",
        "statistic": float(statistic),
        "p_value": float(p_value),
        "equal_variances_at_alpha_0.05": bool(p_value > 0.05),
    }


def analyze_ttest(
    group_a: list[float],
    group_b: list[float],
    paired: bool = False,
    equal_var: bool | None = None,
) -> dict:
    """Two-sample t-test. equal_var=None runs Welch's t-test (does not
    assume equal variances — the safer default); pass True to force
    Student's t-test, or run check_variance_homogeneity first to decide."""
    arr_a = _validate_group(group_a, "group_a")
    arr_b = _validate_group(group_b, "group_b")

    if paired:
        if arr_a.size != arr_b.size:
            raise ValueError("paired t-test requires equal-length groups")
        statistic, p_value = scipy_stats.ttest_rel(arr_a, arr_b)
        test_name = "paired t-test"
        df = arr_a.size - 1
    else:
        use_equal_var = False if equal_var is None else equal_var
        statistic, p_value = scipy_stats.ttest_ind(arr_a, arr_b, equal_var=use_equal_var)
        test_name = "Student's t-test" if use_equal_var else "Welch's t-test"
        df = _welch_df(arr_a, arr_b) if not use_equal_var else (arr_a.size + arr_b.size - 2)

    return {
        "test": test_name,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "df": float(df),
        "significant_at_alpha_0.05": bool(p_value < 0.05),
        "mean_a": float(np.mean(arr_a)),
        "mean_b": float(np.mean(arr_b)),
        "mean_difference": float(np.mean(arr_a) - np.mean(arr_b)),
    }


def _welch_df(a: np.ndarray, b: np.ndarray) -> float:
    v_a, v_b = np.var(a, ddof=1), np.var(b, ddof=1)
    n_a, n_b = a.size, b.size
    numerator = (v_a / n_a + v_b / n_b) ** 2
    denominator = (v_a / n_a) ** 2 / (n_a - 1) + (v_b / n_b) ** 2 / (n_b - 1)
    return float(numerator / denominator)


def analyze_anova(groups: list[list[float]], group_labels: list[str] | None = None) -> dict:
    """One-way ANOVA across 2+ groups (F-test)."""
    if len(groups) < 2:
        raise ValueError("need at least 2 groups")
    arrays = [_validate_group(g, f"group {i}") for i, g in enumerate(groups)]
    labels = group_labels or [f"group_{i+1}" for i in range(len(groups))]
    if len(labels) != len(groups):
        raise ValueError("group_labels must match the number of groups")

    statistic, p_value = scipy_stats.f_oneway(*arrays)

    k = len(arrays)
    n_total = sum(a.size for a in arrays)
    df_between = k - 1
    df_within = n_total - k

    return {
        "test": "one-way ANOVA",
        "f_statistic": float(statistic),
        "p_value": float(p_value),
        "df_between": df_between,
        "df_within": df_within,
        "significant_at_alpha_0.05": bool(p_value < 0.05),
        "group_means": {label: float(np.mean(a)) for label, a in zip(labels, arrays)},
        "note": "Significant ANOVA indicates at least one group differs — run analyze_posthoc_tukey for pairwise comparisons.",
    }


def analyze_kruskal_wallis(groups: list[list[float]], group_labels: list[str] | None = None) -> dict:
    """Kruskal-Wallis H-test — non-parametric alternative to one-way ANOVA
    when normality/variance-homogeneity assumptions fail."""
    if len(groups) < 2:
        raise ValueError("need at least 2 groups")
    arrays = [_validate_group(g, f"group {i}") for i, g in enumerate(groups)]
    labels = group_labels or [f"group_{i+1}" for i in range(len(groups))]
    if len(labels) != len(groups):
        raise ValueError("group_labels must match the number of groups")

    statistic, p_value = scipy_stats.kruskal(*arrays)
    return {
        "test": "Kruskal-Wallis",
        "h_statistic": float(statistic),
        "p_value": float(p_value),
        "significant_at_alpha_0.05": bool(p_value < 0.05),
        "group_medians": {label: float(np.median(a)) for label, a in zip(labels, arrays)},
    }


def analyze_posthoc_tukey(groups: list[list[float]], group_labels: list[str] | None = None) -> dict:
    """Tukey HSD pairwise post-hoc comparisons. Returns every pairwise
    adjusted p-value and significance flag — NOT letter groups (see module
    docstring for why)."""
    if len(groups) < 3:
        raise ValueError("Tukey HSD is for 3+ groups — use analyze_ttest for 2 groups")
    arrays = [_validate_group(g, f"group {i}") for i, g in enumerate(groups)]
    labels = group_labels or [f"group_{i+1}" for i in range(len(groups))]
    if len(labels) != len(groups):
        raise ValueError("group_labels must match the number of groups")

    all_values = np.concatenate(arrays)
    all_labels = np.concatenate([[label] * len(a) for label, a in zip(labels, arrays)])

    result = pairwise_tukeyhsd(all_values, all_labels, alpha=0.05)
    # Public arrays (meandiffs/confint/pvalues/reject) are ordered as
    # itertools.combinations(sorted(groupsunique), 2) — verified directly
    # against statsmodels' own table output rather than assumed, since this
    # ordering isn't documented. Using these instead of the private
    # `_results_table` attribute keeps this working across statsmodels
    # versions that may change internal table formatting.
    pairs = list(itertools.combinations(result.groupsunique, 2))
    pairwise = []
    for (group1, group2), meandiff, (lower, upper), p_adj, reject in zip(
        pairs, result.meandiffs, result.confint, result.pvalues, result.reject
    ):
        pairwise.append(
            {
                "group1": str(group1),
                "group2": str(group2),
                "mean_difference": float(meandiff),
                "p_adjusted": float(p_adj),
                "ci_lower": float(lower),
                "ci_upper": float(upper),
                "significant_at_alpha_0.05": bool(reject),
            }
        )

    return {
        "test": "Tukey HSD",
        "group_means": {label: float(np.mean(a)) for label, a in zip(labels, arrays)},
        "pairwise_comparisons": pairwise,
        "note": "Use this pairwise matrix to assign significance letters by hand — auto letter-grouping isn't implemented here (see module docstring).",
    }


def calculate_effect_size_cohens_d(group_a: list[float], group_b: list[float]) -> dict:
    """Cohen's d for two independent groups (pooled SD)."""
    arr_a = _validate_group(group_a, "group_a")
    arr_b = _validate_group(group_b, "group_b")
    n_a, n_b = arr_a.size, arr_b.size
    pooled_sd = np.sqrt(
        ((n_a - 1) * np.var(arr_a, ddof=1) + (n_b - 1) * np.var(arr_b, ddof=1)) / (n_a + n_b - 2)
    )
    if pooled_sd == 0:
        raise ValueError("pooled standard deviation is zero — Cohen's d is undefined")
    d = (np.mean(arr_a) - np.mean(arr_b)) / pooled_sd

    magnitude = "negligible"
    if abs(d) >= 0.8:
        magnitude = "large"
    elif abs(d) >= 0.5:
        magnitude = "medium"
    elif abs(d) >= 0.2:
        magnitude = "small"

    return {
        "cohens_d": float(d),
        "magnitude": magnitude,
        "convention": "Cohen (1988): 0.2 small, 0.5 medium, 0.8 large",
    }


def calculate_eta_squared(groups: list[list[float]]) -> dict:
    """Eta-squared (proportion of variance explained) from a one-way ANOVA
    design."""
    if len(groups) < 2:
        raise ValueError("need at least 2 groups")
    arrays = [_validate_group(g, f"group {i}") for i, g in enumerate(groups)]
    all_values = np.concatenate(arrays)
    grand_mean = np.mean(all_values)

    ss_between = sum(a.size * (np.mean(a) - grand_mean) ** 2 for a in arrays)
    ss_total = np.sum((all_values - grand_mean) ** 2)
    if ss_total == 0:
        raise ValueError("total sum of squares is zero — eta-squared is undefined")

    eta_sq = ss_between / ss_total
    magnitude = "negligible"
    if eta_sq >= 0.14:
        magnitude = "large"
    elif eta_sq >= 0.06:
        magnitude = "medium"
    elif eta_sq >= 0.01:
        magnitude = "small"

    return {
        "eta_squared": float(eta_sq),
        "magnitude": magnitude,
        "convention": "Cohen (1988): 0.01 small, 0.06 medium, 0.14 large",
    }


def calculate_confidence_interval(values: list[float], confidence: float = 0.95) -> dict:
    """Confidence interval for the mean, via the t-distribution."""
    if not (0 < confidence < 1):
        raise ValueError("confidence must be between 0 and 1")
    arr = _validate_group(values)
    n = arr.size
    mean = float(np.mean(arr))
    sem = float(np.std(arr, ddof=1) / np.sqrt(n))
    t_crit = scipy_stats.t.ppf((1 + confidence) / 2, df=n - 1)
    margin = t_crit * sem
    return {
        "mean": mean,
        "confidence_level": confidence,
        "ci_lower": mean - margin,
        "ci_upper": mean + margin,
        "margin_of_error": margin,
    }


def analyze_two_way_anova(
    values: list[float],
    factor1: list[str],
    factor2: list[str],
    factor1_name: str = "factor1",
    factor2_name: str = "factor2",
) -> dict:
    """Two-way factorial ANOVA with interaction term (Type II sum of squares),
    via statsmodels — the standard design for aquaculture nutrition trials
    with two crossed treatments (e.g. diet x feeding frequency).

    values, factor1, factor2 are one entry PER OBSERVATION (long format, not
    pre-grouped) — e.g. values=[SGR for each tank], factor1=[diet level for
    each tank], factor2=[feeding frequency for each tank]. All three must be
    the same length.

    Column names in the internal formula are fixed ("f1"/"f2") regardless of
    factor1_name/factor2_name, so arbitrary factor names never get interpolated
    into the statsmodels/patsy formula string.
    """
    n = len(values)
    if n != len(factor1) or n != len(factor2):
        raise ValueError("values, factor1, and factor2 must be the same length (one entry per observation)")
    if n < 4:
        raise ValueError("need at least 4 observations for a two-way ANOVA with an interaction term")

    frame = pd.DataFrame({"value": [float(v) for v in values], "f1": factor1, "f2": factor2})
    model = ols("value ~ C(f1) * C(f2)", data=frame).fit()
    table = anova_lm(model, typ=2)

    ss_total = table["sum_sq"].sum()
    table["eta_sq"] = table["sum_sq"] / ss_total

    term_map = {
        "C(f1)": factor1_name,
        "C(f2)": factor2_name,
        "C(f1):C(f2)": f"{factor1_name}:{factor2_name} (interaction)",
        "Residual": "Residual",
    }

    terms = {}
    for term_key, row in table.iterrows():
        f_stat = row["F"]
        p_val = row["PR(>F)"]
        terms[term_map.get(term_key, term_key)] = {
            "sum_sq": float(row["sum_sq"]),
            "df": float(row["df"]),
            "f_statistic": None if pd.isna(f_stat) else float(f_stat),
            "p_value": None if pd.isna(p_val) else float(p_val),
            "eta_squared": float(row["eta_sq"]),
            "significant_at_alpha_0.05": None if pd.isna(p_val) else bool(p_val < 0.05),
        }

    return {
        "test": "two-way ANOVA (Type II sum of squares)",
        "terms": terms,
        "note": (
            "eta_squared here is simple (non-partial) eta-squared: term SS / "
            "total SS. A significant interaction term means the two factors' "
            "effects are not simply additive — interpret each main effect "
            "with that in mind rather than in isolation."
        ),
    }


def calculate_pearson_correlation(x: list[float], y: list[float]) -> dict:
    """Pearson correlation coefficient between two continuous variables."""
    arr_x = _validate_group(x, "x")
    arr_y = _validate_group(y, "y")
    if arr_x.size != arr_y.size:
        raise ValueError("x and y must be the same length")

    r, p_value = scipy_stats.pearsonr(arr_x, arr_y)
    return {
        "r": float(r),
        "r_squared": float(r**2),
        "p_value": float(p_value),
        "n": int(arr_x.size),
        "significant_at_alpha_0.05": bool(p_value < 0.05),
    }
