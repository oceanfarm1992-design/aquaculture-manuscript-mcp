"""Models for repeated measurements on cages — the analyses farm records
actually need, because daily or monthly rows from the same cage are not
independent observations.

- fit_mixed_model: linear mixed model (statsmodels MixedLM), random
  intercept per unit (cage). For continuous responses such as interval SGR
  or FCR.
- fit_gee_model: generalized estimating equations (statsmodels GEE) with a
  within-unit correlation structure (AR(1) over time, exchangeable or
  independence) and robust standard errors. For daily counts such as
  mortality (Poisson with log(fish count) offset), or continuous responses.
- estimate_effect_size_from_records: an effect size whose source is the
  farm's own between-cage variation, for the sample-size tools.

Column names from the user's table are never interpolated into a formula:
columns are copied to fixed internal names (v0, v1, ...) first, as in
statistics.analyze_two_way_anova.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from aquaculture_manuscript_mcp.tools.farm_data import _py, load_table

FEW_CLUSTERS = 40  # below this, sandwich SEs are biased downward


def _prepare(
    table_path: str,
    response: str,
    fixed_effects: list[str],
    group: str,
    categorical: list[str] | None,
    interactions: list[list[str]] | None,
    quadratic: list[str] | None,
    extra: list[str] | None = None,
    sheet: str | None = None,
) -> tuple[pd.DataFrame, str, dict, dict]:
    df = load_table(table_path, sheet)
    needed = [response, group, *fixed_effects, *(extra or [])]
    for name in [*(categorical or []), *(quadratic or []), *(c for pair in (interactions or []) for c in pair)]:
        if name not in fixed_effects:
            raise ValueError(f"'{name}' is used in categorical/interactions/quadratic but is not in fixed_effects")
    missing = [c for c in dict.fromkeys(needed) if c not in df.columns]
    if missing:
        raise ValueError(f"column(s) {missing} not in the table. Columns: {list(df.columns)}")
    if not fixed_effects:
        raise ValueError("give at least one fixed effect")

    names = {col: f"v{i}" for i, col in enumerate(dict.fromkeys(needed))}
    data = df[list(names)].rename(columns=names)
    n_before = len(data)
    data = data.dropna()
    cats = set(categorical or [])
    for col in fixed_effects:
        if not pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            cats.add(col)
    for col in fixed_effects:
        if col not in cats:
            data[names[col]] = pd.to_numeric(data[names[col]], errors="raise")
    data[names[response]] = pd.to_numeric(data[names[response]], errors="raise")

    def term(c: str) -> str:
        return f"C({names[c]})" if c in cats else names[c]

    terms = [term(c) for c in fixed_effects]
    terms += [f"I({names[c]} ** 2)" for c in quadratic or []]
    terms += [":".join(term(c) for c in pair) for pair in interactions or []]
    formula = f"{names[response]} ~ " + " + ".join(terms)
    reverse = {v: k for k, v in names.items()}
    info = {"rows_used": len(data), "rows_dropped_missing": n_before - len(data), "categorical": sorted(cats)}
    return data, formula, reverse, info


def _rename_term(term: str, reverse: dict) -> str:
    for internal, original in sorted(reverse.items(), key=lambda kv: -len(kv[0])):
        term = term.replace(internal, original)
    return term


def _coef_table(params, bse, pvalues, conf, reverse, exponentiate: bool) -> list[dict]:
    rows = []
    for name in params.index:
        if name == "Group Var":
            continue
        row = {
            "term": _rename_term(name, reverse),
            "estimate": params[name],
            "std_error": bse[name],
            "p_value": pvalues[name],
            "ci_lower": conf.loc[name, 0],
            "ci_upper": conf.loc[name, 1],
        }
        if exponentiate:
            row["rate_ratio"] = math.exp(params[name])
            row["rate_ratio_ci"] = [math.exp(conf.loc[name, 0]), math.exp(conf.loc[name, 1])]
        rows.append(row)
    return rows


def fit_mixed_model(
    table_path: str,
    response: str,
    fixed_effects: list[str],
    group: str,
    categorical: list[str] | None = None,
    interactions: list[list[str]] | None = None,
    quadratic: list[str] | None = None,
    sheet: str | None = None,
) -> dict:
    """Linear mixed model: response ~ fixed effects, random intercept per
    ``group`` (e.g. cage). REML fit. Use for continuous unit-level repeated
    measures (interval SGR, FCR, cycle survival)."""
    data, formula, reverse, info = _prepare(table_path, response, fixed_effects, group, categorical, interactions, quadratic, sheet=sheet)
    group_col = {v: k for k, v in reverse.items()}[group]
    n_groups = int(data[group_col].nunique())
    if n_groups < 3:
        raise ValueError(f"only {n_groups} group(s): a random effect needs at least 3 units, preferably many more")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = smf.mixedlm(formula, data, groups=data[group_col])
        res = model.fit(reml=True)
    group_var = float(res.cov_re.iloc[0, 0])
    resid_var = float(res.scale)
    notes = [str(w.message) for w in caught]
    caveats = []
    if n_groups < 10:
        caveats.append(f"only {n_groups} units: the between-unit variance is poorly estimated; treat fixed-effect p-values as approximate")
    if not res.converged:
        caveats.append("model did not converge; do not report these estimates")
    return _py(
        {
            "model": "linear mixed model (REML), random intercept per group",
            "formula": _rename_term(formula, reverse),
            "response": response,
            "group": group,
            "n_observations": int(res.nobs),
            "n_groups": n_groups,
            **info,
            "converged": bool(res.converged),
            "fixed_effects": _coef_table(res.fe_params, res.bse_fe, res.pvalues[res.fe_params.index], res.conf_int().loc[res.fe_params.index], reverse, False),
            "random_intercept_variance": group_var,
            "residual_variance": resid_var,
            "icc": group_var / (group_var + resid_var) if (group_var + resid_var) > 0 else None,
            "aic_note": "REML fit: compare models with different fixed effects only after refitting with ML.",
            "fit_warnings": notes,
            "caveats": caveats,
        }
    )


def fit_gee_model(
    table_path: str,
    response: str,
    fixed_effects: list[str],
    group: str,
    family: str = "gaussian",
    time: str | None = None,
    correlation: str | None = None,
    offset: str | None = None,
    categorical: list[str] | None = None,
    interactions: list[list[str]] | None = None,
    quadratic: list[str] | None = None,
    sheet: str | None = None,
) -> dict:
    """GEE for repeated measures within units (cages).

    family: "gaussian" (continuous), "poisson" (counts, e.g. daily deaths;
        pass offset="log_fish_count" to model a mortality RATE), or
        "binomial" (0/1 outcomes).
    correlation: "ar1" (needs ``time``, e.g. day_index), "exchangeable" or
        "independence". Defaults to "ar1" when time is given, else "exchangeable".
    Standard errors are robust (sandwich); with fewer than 40 units the
    bias-reduced (Mancl–DeRouen) version is used, and a caveat says so.
    """
    families = {"gaussian": sm.families.Gaussian(), "poisson": sm.families.Poisson(), "binomial": sm.families.Binomial()}
    if family not in families:
        raise ValueError(f"family must be one of {sorted(families)}")
    correlation = correlation or ("ar1" if time else "exchangeable")
    if correlation not in ("ar1", "exchangeable", "independence"):
        raise ValueError("correlation must be 'ar1', 'exchangeable' or 'independence'")
    if correlation == "ar1" and not time:
        raise ValueError("correlation 'ar1' needs a time column (e.g. day_index)")
    extra = [c for c in (time, offset) if c]
    data, formula, reverse, info = _prepare(table_path, response, fixed_effects, group, categorical, interactions, quadratic, extra, sheet)
    fwd = {v: k for k, v in reverse.items()}
    sort_cols = [fwd[group]] + ([fwd[time]] if time else [])
    data = data.sort_values(sort_cols).reset_index(drop=True)
    n_groups = int(data[fwd[group]].nunique())
    if n_groups < 3:
        raise ValueError(f"only {n_groups} group(s): GEE needs several independent units")

    cov = {"ar1": sm.cov_struct.Autoregressive(grid=True), "exchangeable": sm.cov_struct.Exchangeable(), "independence": sm.cov_struct.Independence()}[correlation]
    kwargs = {"groups": data[fwd[group]], "cov_struct": cov, "family": families[family]}
    if time:
        kwargs["time"] = pd.to_numeric(data[fwd[time]])
    if offset:
        kwargs["offset"] = pd.to_numeric(data[fwd[offset]])
    cov_type = "bias_reduced" if n_groups < FEW_CLUSTERS else "robust"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = smf.gee(formula, data=data, **kwargs)
        res = model.fit(cov_type=cov_type)
    caveats = []
    if n_groups < FEW_CLUSTERS:
        caveats.append(
            f"{n_groups} units (clusters): sandwich standard errors are unreliable with few clusters even after "
            "bias reduction; treat p-values as approximate and confirm with a mixed model or a designed study"
        )
    dispersion = None
    if family in ("poisson", "binomial"):
        dispersion = float(np.sum(np.asarray(res.resid_pearson) ** 2) / max(res.nobs - len(res.params), 1))
        if dispersion > 1.5:
            caveats.append(
                f"Pearson dispersion {dispersion:.2f} (>1.5): the counts are overdispersed. Robust SEs account for "
                "this in inference, but consider whether unmeasured events (disease, handling) drive the extra variation."
            )
    return _py(
        {
            "model": f"GEE, {family} family, {correlation} working correlation, {cov_type} standard errors",
            "formula": _rename_term(formula, reverse),
            "response": response,
            "group": group,
            "time": time,
            "offset": offset,
            "n_observations": int(res.nobs),
            "n_groups": n_groups,
            **info,
            "coefficients": _coef_table(res.params, res.bse, res.pvalues, res.conf_int(), reverse, family == "poisson"),
            "working_correlation": _working_corr(cov, correlation),
            "pearson_dispersion": dispersion,
            "interpretation_note": (
                "Poisson coefficients are log rate ratios; rate_ratio = exp(estimate) is the multiplicative change "
                "in the mortality rate per unit of the predictor." if family == "poisson" else None
            ),
            "fit_warnings": [str(w.message) for w in caught],
            "caveats": caveats,
        }
    )


def _working_corr(cov, correlation: str):
    if correlation == "ar1":
        return {"ar1_parameter": float(cov.dep_params)}
    if correlation == "exchangeable":
        return {"exchangeable_correlation": float(cov.dep_params)}
    return None


def estimate_effect_size_from_records(
    table_path: str,
    response: str,
    unit_column: str,
    minimum_important_difference: float,
    difference_rationale: str,
    group_column: str | None = None,
    k_groups: int = 2,
    sheet: str | None = None,
) -> dict:
    """Effect size for a planned trial, from the farm's own between-unit
    variation: d = minimum important difference / SD of unit means.

    unit_column: the experimental unit (cage). Each unit's mean of
        ``response`` is one observation, so the SD is between cages, which is
        what a cage-level trial's replication must overcome.
    group_column: optional (e.g. species); SD is then pooled within groups.
    minimum_important_difference: the smallest difference worth detecting,
        in the response's units — a management/scientific judgement from the
        user, explained in difference_rationale.
    Also returns Cohen's f for a one-way design with k_groups where two
    means differ by that amount and the rest sit midway (Cohen 1988, pattern 1).
    """
    if minimum_important_difference <= 0:
        raise ValueError("minimum_important_difference must be positive")
    if not difference_rationale.strip():
        raise ValueError("difference_rationale is required: why is this difference the one worth detecting?")
    df = load_table(table_path, sheet)
    for c in [response, unit_column] + ([group_column] if group_column else []):
        if c not in df.columns:
            raise ValueError(f"column '{c}' not in the table")
    keys = [unit_column] + ([group_column] if group_column else [])
    unit_means = df.dropna(subset=[response]).groupby(keys)[response].mean().reset_index()
    if group_column:
        parts = [g[response] for _, g in unit_means.groupby(group_column) if len(g) >= 2]
        if not parts:
            raise ValueError("need at least 2 units in some group to estimate a pooled SD")
        dof = sum(len(p) - 1 for p in parts)
        sd = math.sqrt(sum((len(p) - 1) * p.var(ddof=1) for p in parts) / dof)
        n_units = sum(len(p) for p in parts)
    else:
        if len(unit_means) < 2:
            raise ValueError("need at least 2 units to estimate an SD")
        sd = float(unit_means[response].std(ddof=1))
        n_units = len(unit_means)
        dof = n_units - 1
    if sd == 0:
        raise ValueError("between-unit SD is zero; an effect size can't be derived")
    d = minimum_important_difference / sd
    f = d * math.sqrt(1 / (2 * k_groups))
    source = (
        f"between-{unit_column} SD of {response} ({sd:.4g}, {n_units} units"
        f"{', pooled within ' + group_column if group_column else ''}) from {Path(table_path).name}; "
        f"minimum important difference {minimum_important_difference:g}: {difference_rationale}"
    )
    caveats = []
    if dof < 10:
        caveats.append(f"SD estimated from only {dof} degrees of freedom: it is imprecise, so plan conservatively (e.g. use a larger SD).")
    caveats.append("Farm (observational) variation can differ from the variation between cages in a controlled trial.")
    return _py(
        {
            "between_unit_sd": sd,
            "n_units": n_units,
            "degrees_of_freedom": dof,
            "minimum_important_difference": minimum_important_difference,
            "cohens_d": d,
            "cohens_f_for_k_groups": f,
            "k_groups": k_groups,
            "effect_size_source": source,
            "caveats": caveats,
            "next_step": "Pass cohens_d (two groups) or cohens_f (k groups) with effect_size_source to calculate_sample_size.",
        }
    )
