"""Sample-size and power calculations (statsmodels), for the Statistical
Analysis and Experimental Design agents.

The effect size is the input that decides the answer, so it must come from
somewhere real: pilot data, the farm's own records, or a cited study. Every
function requires ``effect_size_source`` and echoes it back, so a sample size
in a proposal can always be traced to where its effect size came from.
"""

from __future__ import annotations

import math

from statsmodels.stats.power import FTestAnovaPower, TTestIndPower

_TESTS = ("two_sample_t", "one_way_anova")


def _check(test: str, effect_size: float, alpha: float, effect_size_source: str) -> None:
    if test not in _TESTS:
        raise ValueError(f"test must be one of {_TESTS}")
    if effect_size <= 0:
        raise ValueError("effect_size must be positive (Cohen's d for two_sample_t, Cohen's f for one_way_anova)")
    if not (0 < alpha < 1):
        raise ValueError("alpha must be between 0 and 1")
    if not effect_size_source or not effect_size_source.strip():
        raise ValueError(
            "effect_size_source is required: state where the effect size comes from "
            "(pilot data, the farm's own records, or a cited study). A sample size "
            "built on an unsourced effect size cannot be justified in a proposal."
        )


def calculate_sample_size(
    test: str,
    effect_size: float,
    effect_size_source: str,
    alpha: float = 0.05,
    power: float = 0.8,
    k_groups: int = 2,
) -> dict:
    """Experimental units needed per group to detect ``effect_size``.

    test: "two_sample_t" (effect_size = Cohen's d) or "one_way_anova"
        (effect_size = Cohen's f, k_groups >= 2).
    The unit is whatever is independently assigned to treatment (cage or
    tank), not individual fish.
    """
    _check(test, effect_size, alpha, effect_size_source)
    if not (0 < power < 1):
        raise ValueError("power must be between 0 and 1")
    if test == "two_sample_t":
        n = TTestIndPower().solve_power(effect_size=effect_size, alpha=alpha, power=power, ratio=1.0)
        per_group = math.ceil(n)
        groups = 2
    else:
        if k_groups < 2:
            raise ValueError("k_groups must be >= 2")
        total = FTestAnovaPower().solve_power(effect_size=effect_size, alpha=alpha, power=power, k_groups=k_groups)
        per_group = math.ceil(total / k_groups)
        groups = k_groups
    return {
        "test": test,
        "effect_size": effect_size,
        "effect_size_metric": "Cohen's d" if test == "two_sample_t" else "Cohen's f",
        "effect_size_source": effect_size_source,
        "alpha": alpha,
        "power": power,
        "groups": groups,
        "units_per_group": per_group,
        "total_units": per_group * groups,
        "note": "Units are cages/tanks (the experimental unit), not fish. Add a margin for unit loss.",
    }


def calculate_achieved_power(
    test: str,
    effect_size: float,
    effect_size_source: str,
    units_per_group: int,
    alpha: float = 0.05,
    k_groups: int = 2,
) -> dict:
    """Power of a design with a given number of units per group."""
    _check(test, effect_size, alpha, effect_size_source)
    if units_per_group < 2:
        raise ValueError("units_per_group must be >= 2")
    if test == "two_sample_t":
        pw = TTestIndPower().power(effect_size=effect_size, nobs1=units_per_group, alpha=alpha, ratio=1.0)
    else:
        if k_groups < 2:
            raise ValueError("k_groups must be >= 2")
        pw = FTestAnovaPower().power(effect_size=effect_size, nobs=units_per_group * k_groups, alpha=alpha, k_groups=k_groups)
    return {
        "test": test,
        "effect_size": effect_size,
        "effect_size_source": effect_size_source,
        "units_per_group": units_per_group,
        "alpha": alpha,
        "power": float(pw),
        "adequate_at_0.8": bool(pw >= 0.8),
    }
