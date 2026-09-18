"""Standard aquaculture growth/performance calculators.

Every function is a deterministic formula, not a model guess — same
philosophy as integrity.py: pure Python, no LLM call, fully unit-testable.

FCR terminology varies across sources (some use "eFCR"/"bFCR" to mean
different corrections). Rather than assert one universal naming convention,
each function documents exactly what it computes so the caller can label it
correctly for their target journal.
"""

from __future__ import annotations

import math


def calculate_fcr(
    feed_given_g: float,
    initial_weight_g: float,
    final_weight_g: float,
    dry_matter_fraction: float = 1.0,
) -> dict:
    """Apparent feed conversion ratio: feed given / weight gain.

    Formula (dry-matter basis when dry_matter_fraction < 1), matching the
    worked example in Yossa (2014), J. Applied Aquaculture 26:4:
        FCR (g/g) = (feed given (g) x dry matter fraction) / (final weight (g) - initial weight (g))

    dry_matter_fraction: fraction of the feed that is dry matter (e.g. 0.9 for
        90% dry matter feed). Defaults to 1.0 (feed_given_g already on a dry
        or as-fed basis, whichever the caller intends to report).
    """
    if not (0 < dry_matter_fraction <= 1):
        raise ValueError("dry_matter_fraction must be in (0, 1]")
    if feed_given_g < 0:
        raise ValueError("feed_given_g cannot be negative")
    if initial_weight_g <= 0 or final_weight_g <= 0:
        raise ValueError("weights must be positive")

    weight_gain_g = final_weight_g - initial_weight_g
    if weight_gain_g <= 0:
        raise ValueError(
            "final_weight_g must exceed initial_weight_g — FCR is undefined "
            "for zero or negative weight gain (report the weight loss "
            "directly instead of a ratio)"
        )

    dry_feed_given_g = feed_given_g * dry_matter_fraction
    fcr = dry_feed_given_g / weight_gain_g
    return {
        "fcr": fcr,
        "weight_gain_g": weight_gain_g,
        "dry_feed_given_g": dry_feed_given_g,
        "formula": "FCR (g/g) = (feed given x dry matter fraction) / (final weight - initial weight)",
        "source": "Yossa (2014), J. Applied Aquaculture 26:4, 293-309",
    }


def calculate_biomass_corrected_fcr(
    feed_given_g: float,
    initial_biomass_g: float,
    final_biomass_g: float,
    dead_or_removed_biomass_g: float = 0.0,
    dry_matter_fraction: float = 1.0,
) -> dict:
    """FCR corrected for biomass removed mid-trial (mortalities, sampling).

    Some sources call this "biological FCR" (bFCR) or "corrected FCR" — naming
    is not fully standardized across the literature, so state explicitly in
    your Methods what correction you applied rather than relying on the label
    alone.

    Adjusted gain = (final biomass + biomass removed during the trial) -
    initial biomass. This credits feed consumed by animals that died or were
    sampled mid-trial against the biomass they had accrued, rather than
    penalizing the survivors' apparent FCR for it.
    """
    if not (0 < dry_matter_fraction <= 1):
        raise ValueError("dry_matter_fraction must be in (0, 1]")
    if feed_given_g < 0 or dead_or_removed_biomass_g < 0:
        raise ValueError("feed_given_g and dead_or_removed_biomass_g cannot be negative")
    if initial_biomass_g <= 0 or final_biomass_g <= 0:
        raise ValueError("biomass values must be positive")

    adjusted_gain_g = (final_biomass_g + dead_or_removed_biomass_g) - initial_biomass_g
    if adjusted_gain_g <= 0:
        raise ValueError(
            "adjusted biomass gain is zero or negative — check that "
            "dead_or_removed_biomass_g reflects biomass AT TIME OF removal, "
            "not final weight"
        )

    dry_feed_given_g = feed_given_g * dry_matter_fraction
    fcr = dry_feed_given_g / adjusted_gain_g
    return {
        "biomass_corrected_fcr": fcr,
        "adjusted_gain_g": adjusted_gain_g,
        "dry_feed_given_g": dry_feed_given_g,
        "formula": "FCR = (feed given x dry matter fraction) / ((final biomass + removed biomass) - initial biomass)",
        "note": "State your exact correction method in Methods; naming (bFCR/corrected FCR) varies by source.",
    }


def calculate_economic_fcr(
    feed_given_g: float,
    feed_cost_per_kg: float,
    weight_gain_g: float,
    product_value_per_kg: float,
) -> dict:
    """Economic FCR: cost of feed consumed per unit value of weight gained.

    economic_fcr = (feed cost) / (value of weight gain). A value below 1
    means feed cost is less than the value of the biomass it produced.
    """
    if feed_given_g < 0 or feed_cost_per_kg < 0 or product_value_per_kg < 0:
        raise ValueError("feed_given_g, feed_cost_per_kg, and product_value_per_kg cannot be negative")
    if weight_gain_g <= 0:
        raise ValueError("weight_gain_g must be positive")

    feed_cost = (feed_given_g / 1000) * feed_cost_per_kg
    gain_value = (weight_gain_g / 1000) * product_value_per_kg
    if gain_value == 0:
        raise ValueError("product_value_per_kg is zero — economic FCR is undefined")

    return {
        "economic_fcr": feed_cost / gain_value,
        "feed_cost": feed_cost,
        "gain_value": gain_value,
        "formula": "economic FCR = feed cost / value of weight gain",
    }


def calculate_sgr(initial_weight_g: float, final_weight_g: float, days: float) -> dict:
    """Specific growth rate (%/day): SGR = (ln(Wf) - ln(Wi)) / t x 100."""
    if initial_weight_g <= 0 or final_weight_g <= 0:
        raise ValueError("weights must be positive (natural log is undefined for <= 0)")
    if days <= 0:
        raise ValueError("days must be positive")

    sgr = (math.log(final_weight_g) - math.log(initial_weight_g)) / days * 100
    return {
        "sgr_percent_per_day": sgr,
        "formula": "SGR (%/day) = (ln(final weight) - ln(initial weight)) / days x 100",
    }


def calculate_stocking_density(
    biomass_kg: float,
    volume_m3: float | None = None,
    area_m2: float | None = None,
) -> dict:
    """Stocking density as biomass per volume (kg/m3) and/or per area (kg/m2).

    Supply volume_m3 for tanks/ponds measured by water volume, area_m2 for
    systems measured by surface area (e.g. shallow ponds, raceways) — or both
    if you want both figures.
    """
    if biomass_kg <= 0:
        raise ValueError("biomass_kg must be positive")
    if volume_m3 is None and area_m2 is None:
        raise ValueError("supply at least one of volume_m3 or area_m2")
    if volume_m3 is not None and volume_m3 <= 0:
        raise ValueError("volume_m3 must be positive")
    if area_m2 is not None and area_m2 <= 0:
        raise ValueError("area_m2 must be positive")

    result: dict = {}
    if volume_m3 is not None:
        result["density_kg_per_m3"] = biomass_kg / volume_m3
    if area_m2 is not None:
        result["density_kg_per_m2"] = biomass_kg / area_m2
    return result


def calculate_survival_rate(initial_count: int, final_count: int) -> dict:
    """Survival and cumulative mortality rate as percentages."""
    if initial_count <= 0:
        raise ValueError("initial_count must be positive")
    if final_count < 0:
        raise ValueError("final_count cannot be negative")
    if final_count > initial_count:
        raise ValueError(
            "final_count exceeds initial_count — check for a data-entry "
            "error or restocking event, this calculator assumes no "
            "additions after stocking"
        )

    survival_pct = (final_count / initial_count) * 100
    return {
        "survival_percent": survival_pct,
        "cumulative_mortality_percent": 100 - survival_pct,
        "mortality_count": initial_count - final_count,
        "formula": "survival % = (final count / initial count) x 100",
    }
