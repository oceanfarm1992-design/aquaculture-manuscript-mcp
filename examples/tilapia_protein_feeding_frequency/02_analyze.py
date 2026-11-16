"""Compute every number the example manuscript reports, using only this
package's own calculators and statistics tools. The manuscript text quotes
results.json; it never computes a statistic itself.

Input is synthetic_tank_data.csv (SYNTHETIC — see 01_generate_synthetic_data.py).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from aquaculture_manuscript_mcp.tools import calculators as calc
from aquaculture_manuscript_mcp.tools import statistics as st
from aquaculture_manuscript_mcp.tools import water_quality as wq

HERE = Path(__file__).parent
DRY_MATTER = 0.92  # assumed dry-matter fraction of the experimental feeds

RESPONSES = {
    "final_weight_g": "Final mean weight (g)",
    "weight_gain_pct": "Weight gain (%)",
    "sgr": "SGR (% day-1)",
    "fcr": "FCR",
    "per": "PER",
    "survival_pct": "Survival (%)",
}


def load() -> list[dict]:
    with (HERE / "synthetic_tank_data.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k, v in r.items():
            r[k] = float(v)
    return rows


def per_tank_metrics(r: dict) -> dict:
    sgr = calc.calculate_sgr(r["initial_mean_weight_g"], r["final_mean_weight_g"], r["days"])
    fcr = calc.calculate_biomass_corrected_fcr(
        feed_given_g=r["feed_given_g_as_fed"],
        initial_biomass_g=r["initial_biomass_g"],
        final_biomass_g=r["final_biomass_g"],
        dead_or_removed_biomass_g=r["dead_biomass_g"],
        dry_matter_fraction=DRY_MATTER,
    )
    surv = calc.calculate_survival_rate(int(r["initial_count"]), int(r["final_count"]))
    protein_fed_g = fcr["dry_feed_given_g"] * r["crude_protein_pct"] / 100
    nh3 = wq.calculate_unionized_ammonia(r["mean_tan_mg_l"], r["mean_ph"], r["mean_temperature_c"])
    return {
        "tank": int(r["tank"]),
        "cp": int(r["crude_protein_pct"]),
        "ff": int(r["meals_per_day"]),
        "final_weight_g": r["final_mean_weight_g"],
        "weight_gain_pct": (r["final_mean_weight_g"] - r["initial_mean_weight_g"]) / r["initial_mean_weight_g"] * 100,
        "sgr": sgr["sgr_percent_per_day"],
        "fcr": fcr["biomass_corrected_fcr"],
        # PER = wet biomass gain / dry protein fed (simple ratio; formula stated in Methods)
        "per": fcr["adjusted_gain_g"] / protein_fed_g,
        "survival_pct": surv["survival_percent"],
        "nh3_mg_l": nh3["unionized_ammonia_nh3_n_mg_l"],
        "temp": r["mean_temperature_c"],
        "do": r["mean_do_mg_l"],
        "ph": r["mean_ph"],
        "tan": r["mean_tan_mg_l"],
        "initial_weight_g": r["initial_mean_weight_g"],
    }


def residuals(tanks: list[dict], key: str) -> list[float]:
    out = []
    for t in tanks:
        cell = [u[key] for u in tanks if u["cp"] == t["cp"] and u["ff"] == t["ff"]]
        out.append(t[key] - float(np.mean(cell)))
    return out


def main() -> None:
    tanks = [per_tank_metrics(r) for r in load()]
    cells = sorted({(t["cp"], t["ff"]) for t in tanks})
    cp_levels = sorted({t["cp"] for t in tanks})
    ff_levels = sorted({t["ff"] for t in tanks})
    results: dict = {"n_tanks": len(tanks), "responses": {}}

    for key in RESPONSES:
        values = [t[key] for t in tanks]
        entry: dict = {}
        entry["cell_stats"] = {
            f"CP{cp}_F{ff}": st.descriptive_stats([t[key] for t in tanks if (t["cp"], t["ff"]) == (cp, ff)])
            for cp, ff in cells
        }
        entry["cp_main_means"] = {
            f"CP{cp}": st.descriptive_stats([t[key] for t in tanks if t["cp"] == cp]) for cp in cp_levels
        }
        entry["ff_main_means"] = {
            f"F{ff}": st.descriptive_stats([t[key] for t in tanks if t["ff"] == ff]) for ff in ff_levels
        }
        entry["normality_of_residuals"] = st.check_normality(residuals(tanks, key))
        entry["levene_across_cells"] = st.check_variance_homogeneity(
            [[t[key] for t in tanks if (t["cp"], t["ff"]) == c] for c in cells]
        )
        entry["two_way_anova"] = st.analyze_two_way_anova(
            values,
            [f"CP{t['cp']}" for t in tanks],
            [f"F{t['ff']}" for t in tanks],
            factor1_name="protein",
            factor2_name="feeding_frequency",
        )
        entry["tukey_protein"] = st.analyze_posthoc_tukey(
            [[t[key] for t in tanks if t["cp"] == cp] for cp in cp_levels],
            [f"CP{cp}" for cp in cp_levels],
        )
        if key == "survival_pct":
            entry["kruskal_wallis_cells"] = st.analyze_kruskal_wallis(
                [[t[key] for t in tanks if (t["cp"], t["ff"]) == c] for c in cells],
                [f"CP{cp}_F{ff}" for cp, ff in cells],
            )
        results["responses"][key] = entry

    results["initial_weight"] = st.descriptive_stats([t["initial_weight_g"] for t in tanks])
    results["initial_weight_anova"] = st.analyze_anova(
        [[t["initial_weight_g"] for t in tanks if (t["cp"], t["ff"]) == c] for c in cells]
    )
    results["sgr_vs_fcr"] = st.calculate_pearson_correlation(
        [t["sgr"] for t in tanks], [t["fcr"] for t in tanks]
    )
    results["water_quality"] = {
        name: st.descriptive_stats([t[name] for t in tanks]) for name in ("temp", "do", "ph", "tan", "nh3_mg_l")
    }
    results["water_quality_checks"] = {
        "temperature_c": wq.check_water_parameter("nile_tilapia", "temperature_c", results["water_quality"]["temp"]["mean"]),
        "dissolved_oxygen_mg_l": wq.check_water_parameter("nile_tilapia", "dissolved_oxygen_mg_l", results["water_quality"]["do"]["mean"]),
        "ph": wq.check_water_parameter("nile_tilapia", "ph", results["water_quality"]["ph"]["mean"]),
        "total_ammonia_nitrogen_mg_l": wq.check_water_parameter("nile_tilapia", "total_ammonia_nitrogen_mg_l", results["water_quality"]["tan"]["mean"]),
    }
    results["per_tank"] = tanks

    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print("wrote results.json")


if __name__ == "__main__":
    main()
