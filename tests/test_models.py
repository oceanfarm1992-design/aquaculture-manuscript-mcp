import json
import math

import numpy as np
import pandas as pd
import pytest

from aquaculture_manuscript_mcp.tools import farm_data, models


@pytest.fixture
def daily_counts(tmp_path):
    """12 cages x 200 days of Poisson deaths with a known temperature effect:
    log(rate) = -7 + 0.15 * temperature (rate ratio exp(0.15) = 1.162 per °C)."""
    rng = np.random.default_rng(3)
    rows = []
    for c in range(12):
        temps = 28 + 4 * np.sin(np.arange(200) / 30) + rng.normal(0, 0.5, 200)
        for d, t in enumerate(temps):
            fish = 5000
            rows.append({"cage": f"C{c}", "day_index": d, "temperature_c": t, "fish_count": fish,
                         "log_fish_count": math.log(fish), "deaths": rng.poisson(fish * math.exp(-7 + 0.15 * (t - 28)) )})
    path = tmp_path / "daily.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def test_gee_poisson_recovers_known_rate_ratio(daily_counts):
    r = models.fit_gee_model(daily_counts, "deaths", ["temperature_c"], "cage", family="poisson",
                             time="day_index", offset="log_fish_count")
    temp = next(c for c in r["coefficients"] if c["term"] == "temperature_c")
    assert temp["estimate"] == pytest.approx(0.15, abs=0.03)
    assert temp["rate_ratio_ci"][0] < math.exp(0.15) < temp["rate_ratio_ci"][1]
    assert "ar1" in r["model"] and "bias_reduced" in r["model"]
    assert any("clusters" in c for c in r["caveats"])  # 12 cages < 40
    json.dumps(r)


def test_gee_validation(daily_counts):
    with pytest.raises(ValueError, match="needs a time column"):
        models.fit_gee_model(daily_counts, "deaths", ["temperature_c"], "cage", correlation="ar1")
    with pytest.raises(ValueError, match="family"):
        models.fit_gee_model(daily_counts, "deaths", ["temperature_c"], "cage", family="gamma")
    with pytest.raises(ValueError, match="not in the table"):
        models.fit_gee_model(daily_counts, "deaths", ["salinity"], "cage")


def test_mixed_model_recovers_slope_and_cage_variance(tmp_path):
    rng = np.random.default_rng(5)
    rows = []
    for c in range(15):
        u = rng.normal(0, 1.0)  # cage random effect
        for _ in range(10):
            x = rng.uniform(20, 32)
            rows.append({"cage": f"K{c}", "temp": x, "species": "A" if c % 2 else "B", "y": 2 + 0.5 * x + u + rng.normal(0, 0.5)})
    path = tmp_path / "iv.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    r = models.fit_mixed_model(str(path), "y", ["temp", "species"], "cage")
    slope = next(f for f in r["fixed_effects"] if f["term"] == "temp")
    assert slope["estimate"] == pytest.approx(0.5, abs=0.05)
    assert r["converged"] and r["icc"] > 0.5
    assert "species" in r["categorical"]
    json.dumps(r)


def test_formula_never_contains_user_column_names(tmp_path):
    """Column names with formula syntax must not be interpolated into patsy."""
    path = tmp_path / "t.csv"
    rng = np.random.default_rng(1)
    pd.DataFrame({"cage": [f"c{i % 5}" for i in range(50)], "temp (°C) + 1": rng.normal(size=50),
                  "y": rng.normal(size=50)}).to_csv(path, index=False)
    r = models.fit_mixed_model(str(path), "y", ["temp (°C) + 1"], "cage")
    assert r["fixed_effects"][1]["term"] == "temp (°C) + 1"


def test_effect_size_from_records_uses_between_cage_sd(tmp_path):
    # cage means 1, 2, 3 -> SD = 1; MID 0.5 -> d = 0.5
    rows = [{"cage": c, "sgr": m + e} for c, m in (("a", 1), ("b", 2), ("c", 3)) for e in (-0.1, 0.1)]
    path = tmp_path / "t.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    r = models.estimate_effect_size_from_records(str(path), "sgr", "cage", 0.5, "10% of typical SGR")
    assert r["between_unit_sd"] == pytest.approx(1.0)
    assert r["cohens_d"] == pytest.approx(0.5)
    assert r["cohens_f_for_k_groups"] == pytest.approx(0.5 * math.sqrt(1 / 4))
    assert "10% of typical SGR" in r["effect_size_source"]
    with pytest.raises(ValueError, match="difference_rationale"):
        models.estimate_effect_size_from_records(str(path), "sgr", "cage", 0.5, " ")


def test_daily_table_lag_respects_missing_days(farm_csv, column_roles, tmp_path):
    out = tmp_path / "daily.csv"
    farm_data.export_analysis_table(farm_csv, column_roles, str(out), "daily", temperature_lags=[2])
    t = pd.read_csv(out, parse_dates=["date"])
    a1 = t[t["cage"] == "A1"].set_index("date")
    day = a1.index[50]
    assert a1.loc[day, "temperature_c_lag2"] == pytest.approx(a1.loc[day - pd.Timedelta(days=2), "temperature_c"])
    assert {"day_index", "log_fish_count", "cycle", "season", "mortality_rate_pct"} <= set(t.columns)
