"""Shared fixtures: a small synthetic cage-farm dataset with known,
deliberately planted problems, so quality checks can be tested against
ground truth."""

import numpy as np
import pandas as pd
import pytest

COLUMN_ROLES = {
    "date": "Date",
    "cage": "Cage",
    "species": "Species",
    "temperature_c": "Temp (C)",
    "salinity_ppt": "Salinity",
    "do_mg_l": "DO (mg/L)",
    "feed_kg": "Feed (kg)",
    "mortality_count": "Mortality",
    "abw_g": "ABW (g)",
    "fish_count": "Fish count",
}


def build_farm_frame(seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    rows = []
    for species, cages, heat_sensitivity in (("SpeciesA", ["A1", "A2", "A3"], 0.004), ("SpeciesB", ["B1", "B2", "B3"], 0.001)):
        for cage in cages:
            fish = 5000
            abw = 20.0
            for i, d in enumerate(dates):
                temp = 26 + 7 * np.sin(2 * np.pi * (d.day_of_year - 110) / 365) + rng.normal(0, 0.4)
                rate = 0.0005 + heat_sensitivity * max(0.0, temp - 30)
                dead = int(rng.binomial(fish, min(rate, 0.05)))
                growth = 0.012 * max(0.1, 1 - abs(temp - 27) / 10)
                abw *= np.exp(growth)
                feed = fish * abw / 1000 * 0.015
                rows.append(
                    {
                        "Date": d.date().isoformat(),
                        "Cage": cage,
                        "Species": species,
                        "Temp (C)": round(temp, 2),
                        "Salinity": round(40 + rng.normal(0, 0.5), 2),
                        "DO (mg/L)": round(7.5 - 0.15 * (temp - 26) + rng.normal(0, 0.2), 2),
                        "Feed (kg)": round(feed, 1),
                        "Mortality": dead,
                        "ABW (g)": round(abw * rng.normal(1, 0.02), 1) if i % 30 == 0 else np.nan,
                        "Fish count": fish,
                    }
                )
                fish -= dead
    df = pd.DataFrame(rows)
    # Planted problems -------------------------------------------------------
    df.loc[10, "Temp (C)"] = 99.0                       # implausible temperature
    df = pd.concat([df, df.iloc[[20]]], ignore_index=True)  # exact duplicate row
    conflict = df.iloc[[30]].copy()
    conflict["Feed (kg)"] = conflict["Feed (kg)"] + 50  # same cage+date, different value
    df = pd.concat([df, conflict], ignore_index=True)
    a1_samples = df[(df["Cage"] == "A1") & df["ABW (g)"].notna()].index
    df.loc[a1_samples[3], "ABW (g)"] = df.loc[a1_samples[2], "ABW (g)"] * 0.5  # ABW drop
    return df


@pytest.fixture
def farm_csv(tmp_path):
    path = tmp_path / "farm.csv"
    build_farm_frame().to_csv(path, index=False)
    return str(path)


@pytest.fixture
def column_roles():
    return dict(COLUMN_ROLES)
