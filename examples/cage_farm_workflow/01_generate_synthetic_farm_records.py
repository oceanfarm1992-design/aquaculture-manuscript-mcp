"""Generate SYNTHETIC offshore cage-farm records for the Phase 1 demo.

NOT REAL FARM DATA. Three years of daily records for three species (Sobaity,
Shaam, Gabit), three cages each, with a seasonal Gulf-like temperature
cycle. Built-in "truth" (so you can check what the agents find):
  - Mortality rises above ~32 °C, most steeply in Sobaity, least in Gabit,
    and with a ~2-day lag.
  - Low DO on hot days adds mortality.
  - Growth peaks near 26–28 °C and slows at temperature extremes.
Planted recording problems: a 99 °C temperature, a negative feed entry,
duplicate rows, a conflicting cage-day, an ABW sample entered as kg, and a
gap of missing days in one cage.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 7
OUT = Path(__file__).with_name("synthetic_cage_farm_records.xlsx")

SPECIES = {
    # name: (heat mortality slope per °C above 32, optimum temp, cages)
    "Sobaity": (0.0030, 26.5, ["S1", "S2", "S3"]),
    "Shaam": (0.0015, 27.5, ["H1", "H2", "H3"]),
    "Gabit": (0.0006, 28.0, ["G1", "G2", "G3"]),
}


def main() -> None:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    base_temp = 25 + 8.5 * np.sin(2 * np.pi * (dates.day_of_year - 120) / 365)
    rows = []
    for species, (slope, t_opt, cages) in SPECIES.items():
        for cage in cages:
            offset = rng.normal(0, 0.3)  # cage position effect
            fish, abw = 12000, 35.0
            temps = base_temp + offset + rng.normal(0, 0.6, len(dates))
            for i, d in enumerate(dates):
                if d.month == 3 and d.day == 1 and i > 0:  # annual harvest + restock
                    fish, abw = 12000, 35.0
                t = temps[i]
                t_lag = temps[i - 2] if i >= 2 else t
                do = 7.8 - 0.22 * (t - 24) + rng.normal(0, 0.35)
                rate = 0.0003 + slope * max(0.0, t_lag - 32) + 0.002 * max(0.0, 4.5 - do)
                dead = int(rng.binomial(fish, min(rate, 0.08)))
                g = 0.009 * max(0.05, 1 - ((t - t_opt) / 9) ** 2) * (1 - abw / 1500)
                abw *= np.exp(g)
                feed = fish * abw / 1000 * (0.006 + 0.014 * max(0.0, 1 - abs(t - t_opt) / 10))
                rows.append(
                    {
                        "Date": d.date(),
                        "Cage No": cage,
                        "Species": species,
                        "Water Temp (°C)": round(t, 1),
                        "Salinity (ppt)": round(41 + 1.5 * np.sin(2 * np.pi * (d.day_of_year - 200) / 365) + rng.normal(0, 0.4), 1),
                        "DO (mg/L)": round(do, 2),
                        "Feed Given (kg)": round(feed, 1),
                        "Mortality (pcs)": dead,
                        "ABW (g)": round(abw * rng.normal(1, 0.03), 1) if d.day == 15 else np.nan,
                        "Fish Count": fish,
                    }
                )
                fish -= dead
    df = pd.DataFrame(rows)

    # Planted recording problems ------------------------------------------
    df.loc[500, "Water Temp (°C)"] = 99.0
    df.loc[1200, "Feed Given (kg)"] = -35.0
    df = pd.concat([df, df.iloc[[2000, 2001, 2002]]], ignore_index=True)
    conflict = df.iloc[[3000]].copy()
    conflict["Mortality (pcs)"] += 40
    df = pd.concat([df, conflict], ignore_index=True)
    abw_rows = df[(df["Cage No"] == "H2") & df["ABW (g)"].notna()].index
    df.loc[abw_rows[10], "ABW (g)"] = round(df.loc[abw_rows[10], "ABW (g)"] / 1000, 3)  # entered in kg
    gap = df[(df["Cage No"] == "G3") & (pd.to_datetime(df["Date"]).between("2023-07-10", "2023-07-19"))].index
    df = df.drop(gap)

    df.to_excel(OUT, index=False, sheet_name="Daily records")
    print(f"wrote {len(df)} rows to {OUT}")


if __name__ == "__main__":
    main()
