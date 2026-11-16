"""Resource planning for a designed trial (Feasibility & Resource Planning
Agent). Deterministic arithmetic from the design and from sourced inputs;
costs are computed only from unit costs the user supplies.
"""

from __future__ import annotations

import math


def _require_source(value, source: str | None, name: str) -> None:
    if value is not None and not (source and source.strip()):
        raise ValueError(f"{name}_source is required when {name} is given (farm records, supplier quote, or a cited study)")


def plan_trial_resources(
    treatments: int,
    units_per_treatment: int,
    fish_per_unit: int,
    initial_weight_g: float,
    expected_final_weight_g: float,
    duration_days: int,
    expected_fcr: float,
    expected_fcr_source: str,
    expected_survival_pct: float,
    expected_survival_source: str,
    fish_sampled_per_unit_per_event: int = 0,
    sampling_events: int = 0,
    spare_fish_pct: float = 10.0,
    unit_volume_m3: float | None = None,
    feed_cost_per_kg: float | None = None,
    feed_cost_source: str | None = None,
    fish_cost_each: float | None = None,
    fish_cost_source: str | None = None,
    currency: str | None = None,
) -> dict:
    """Fish, units, biomass, density and feed needed for a trial, plus feed
    and fish costs when unit costs (with sources) are given.

    Feed = expected FCR x ((final biomass + biomass removed by mortality and
    sampling) - initial biomass), the same biomass-corrected FCR definition
    the farm-data tools use. Removed fish are valued at the mean of initial
    and final weight.
    """
    for name, v in (("treatments", treatments), ("units_per_treatment", units_per_treatment), ("fish_per_unit", fish_per_unit), ("duration_days", duration_days)):
        if v < 1:
            raise ValueError(f"{name} must be >= 1")
    if not 0 < initial_weight_g < expected_final_weight_g:
        raise ValueError("need 0 < initial_weight_g < expected_final_weight_g")
    if expected_fcr <= 0:
        raise ValueError("expected_fcr must be positive")
    if not 0 < expected_survival_pct <= 100:
        raise ValueError("expected_survival_pct must be in (0, 100]")
    if not expected_fcr_source.strip() or not expected_survival_source.strip():
        raise ValueError("expected_fcr_source and expected_survival_source are required")
    _require_source(feed_cost_per_kg, feed_cost_source, "feed_cost")
    _require_source(fish_cost_each, fish_cost_source, "fish_cost")
    if (feed_cost_per_kg is not None or fish_cost_each is not None) and not currency:
        raise ValueError("currency is required when costs are given")

    units = treatments * units_per_treatment
    sampled_per_unit = fish_sampled_per_unit_per_event * sampling_events
    deaths_per_unit = fish_per_unit * (1 - expected_survival_pct / 100)
    end_per_unit = fish_per_unit - deaths_per_unit - sampled_per_unit
    if end_per_unit <= 0:
        raise ValueError("sampling and expected mortality remove every fish before the end; increase fish_per_unit")
    mean_w = (initial_weight_g + expected_final_weight_g) / 2
    b0 = fish_per_unit * initial_weight_g / 1000
    b1 = end_per_unit * expected_final_weight_g / 1000
    removed = (deaths_per_unit + sampled_per_unit) * mean_w / 1000
    gain_per_unit = (b1 + removed) - b0
    feed_per_unit = expected_fcr * gain_per_unit
    stocked = units * fish_per_unit
    to_procure = math.ceil(stocked * (1 + spare_fish_pct / 100))

    result: dict = {
        "design": {"treatments": treatments, "units_per_treatment": units_per_treatment, "total_units": units, "duration_days": duration_days},
        "fish": {
            "stocked": stocked,
            "spare_pct": spare_fish_pct,
            "to_procure": to_procure,
            "removed_by_sampling": units * sampled_per_unit,
            "expected_deaths": round(units * deaths_per_unit, 1),
            "expected_at_end": round(units * end_per_unit, 1),
        },
        "biomass_kg": {
            "initial_per_unit": b0,
            "final_per_unit": b1,
            "initial_total": b0 * units,
            "final_total": b1 * units,
        },
        "feed_kg": {"per_unit": feed_per_unit, "total": feed_per_unit * units, "per_day_total_average": feed_per_unit * units / duration_days},
        "assumptions": {
            "expected_fcr": expected_fcr,
            "expected_fcr_source": expected_fcr_source,
            "expected_survival_pct": expected_survival_pct,
            "expected_survival_source": expected_survival_source,
            "removed_fish_weight": "mean of initial and final weight",
        },
    }
    if unit_volume_m3 is not None:
        if unit_volume_m3 <= 0:
            raise ValueError("unit_volume_m3 must be positive")
        result["density_kg_m3"] = {"initial": b0 / unit_volume_m3, "final": b1 / unit_volume_m3}
        result["density_note"] = "Compare against welfare limits for the species before approving the design."
    costs: dict = {"currency": currency}
    if feed_cost_per_kg is not None:
        costs["feed"] = {"amount": feed_per_unit * units * feed_cost_per_kg, "unit_cost": feed_cost_per_kg, "source": feed_cost_source}
    else:
        costs["feed"] = "unit cost needed"
    if fish_cost_each is not None:
        costs["fish"] = {"amount": to_procure * fish_cost_each, "unit_cost": fish_cost_each, "source": fish_cost_source}
    else:
        costs["fish"] = "unit cost needed"
    result["costs"] = costs
    result["not_included"] = ["staff time", "laboratory analyses", "equipment", "energy and vessel time", "contingency"]
    return result
