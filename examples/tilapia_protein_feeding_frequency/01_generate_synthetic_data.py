"""Generate a SYNTHETIC tank-level dataset for the worked example manuscript.

THESE ARE NOT REAL MEASUREMENTS. No fish were reared. The numbers are drawn
from a seeded random model so the example is reproducible and the rest of the
pipeline (calculators, statistics, .docx export) has realistic-looking input
to work on. Never reuse this file as data for a real paper.

Design: Nile tilapia, 3 dietary crude-protein levels (25, 30, 35 %) x
2 feeding frequencies (2 or 3 meals/day), 3 replicate tanks per combination
= 18 tanks, 20 fish per tank, 56-day trial.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

SEED = 20261116
OUT = Path(__file__).with_name("synthetic_tank_data.csv")

FISH_PER_TANK = 20
DAYS = 56
PROTEIN_LEVELS = [25, 30, 35]
FEEDING_FREQUENCIES = [2, 3]
REPLICATES = 3

# Assumed "true" cell means used only to generate the synthetic numbers.
MEAN_FINAL_WEIGHT_G = {
    (25, 2): 27.5, (25, 3): 29.0,
    (30, 2): 32.5, (30, 3): 34.5,
    (35, 2): 33.5, (35, 3): 35.0,
}
MEAN_FCR = {
    (25, 2): 1.58, (25, 3): 1.52,
    (30, 2): 1.38, (30, 3): 1.32,
    (35, 2): 1.34, (35, 3): 1.31,
}


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = []
    tank = 0
    for cp in PROTEIN_LEVELS:
        for ff in FEEDING_FREQUENCIES:
            for rep in range(1, REPLICATES + 1):
                tank += 1
                initial_mean_w = round(float(rng.normal(5.0, 0.08)), 2)
                final_mean_w = round(float(rng.normal(MEAN_FINAL_WEIGHT_G[(cp, ff)], 1.1)), 2)
                deaths = int(rng.binomial(FISH_PER_TANK, 0.05))
                final_count = FISH_PER_TANK - deaths
                # Dead fish assumed removed at roughly mid-trial weight.
                dead_biomass = round(deaths * (initial_mean_w + final_mean_w) / 2, 1)
                initial_biomass = round(initial_mean_w * FISH_PER_TANK, 1)
                final_biomass = round(final_mean_w * final_count, 1)
                fcr_true = float(rng.normal(MEAN_FCR[(cp, ff)], 0.04))
                feed_given = round(fcr_true * ((final_biomass + dead_biomass) - initial_biomass), 1)
                rows.append(
                    {
                        "tank": tank,
                        "crude_protein_pct": cp,
                        "meals_per_day": ff,
                        "replicate": rep,
                        "initial_count": FISH_PER_TANK,
                        "final_count": final_count,
                        "initial_mean_weight_g": initial_mean_w,
                        "final_mean_weight_g": final_mean_w,
                        "initial_biomass_g": initial_biomass,
                        "final_biomass_g": final_biomass,
                        "dead_biomass_g": dead_biomass,
                        "feed_given_g_as_fed": feed_given,
                        "mean_temperature_c": round(float(rng.normal(27.0, 0.3)), 1),
                        "mean_do_mg_l": round(float(rng.normal(5.9, 0.2)), 2),
                        "mean_ph": round(float(rng.normal(7.4, 0.1)), 2),
                        "mean_tan_mg_l": round(float(rng.normal(0.27, 0.03)), 2),
                        "days": DAYS,
                    }
                )

    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} synthetic tanks to {OUT}")


if __name__ == "__main__":
    main()
