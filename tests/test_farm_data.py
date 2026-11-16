import json
import math

import pandas as pd
import pytest

from aquaculture_manuscript_mcp.tools import farm_data
from conftest import build_farm_frame


def test_suggest_column_roles_matches_common_names(farm_csv, column_roles):
    result = farm_data.suggest_column_roles(farm_csv)
    suggested = result["suggested_column_roles"]
    for role in ("date", "cage", "species", "temperature_c", "do_mg_l", "feed_kg", "mortality_count", "abw_g", "fish_count", "salinity_ppt"):
        assert suggested.get(role) == column_roles[role], role


def test_profile_dataset_counts_rows_duplicates_and_sparse_abw(farm_csv):
    p = farm_data.profile_dataset(farm_csv)
    assert p["rows"] == 6 * 400 + 2
    assert p["exact_duplicate_rows"] == 1
    assert p["column_profiles"]["ABW (g)"]["missing_pct"] > 90
    assert p["column_profiles"]["Date"]["looks_like_date"] is True
    json.dumps(p)  # JSON-safe


def test_excel_input_loads(tmp_path):
    path = tmp_path / "farm.xlsx"
    build_farm_frame().head(50).to_excel(path, index=False)
    assert farm_data.profile_dataset(str(path))["rows"] == 50


def test_quality_check_finds_every_planted_problem(farm_csv, column_roles):
    q = farm_data.check_data_quality(farm_csv, column_roles)
    checks = {i["check"] for i in q["issues"]}
    assert "implausible_value" in checks
    assert "exact_duplicate_rows" in checks
    assert "conflicting_cage_date_rows" in checks
    assert "abw_decrease" in checks
    implausible = next(i for i in q["issues"] if i["check"] == "implausible_value")
    assert implausible["examples"][0]["temperature_c"] == 99.0
    json.dumps(q)


def test_unknown_role_or_column_rejected(farm_csv):
    with pytest.raises(ValueError, match="unknown role"):
        farm_data.check_data_quality(farm_csv, {"water_temp": "Temp (C)"})
    with pytest.raises(ValueError, match="not in the file"):
        farm_data.check_data_quality(farm_csv, {"temperature_c": "Temperature"})


def test_sampling_interval_sgr_matches_formula(farm_csv, column_roles):
    m = farm_data.compute_performance_metrics(farm_csv, column_roles)
    iv = m["intervals"][0]
    expected = (math.log(iv["abw_end_g"]) - math.log(iv["abw_start_g"])) / iv["days"] * 100
    assert iv["sgr"] == pytest.approx(expected)
    assert iv["days"] == 30
    assert m["cleaning_log"]["exact_duplicate_rows_dropped"] == 1
    assert m["cleaning_log"]["duplicate_cage_date_rows_dropped_keep_first"] == 1
    assert m["cleaning_log"]["implausible_values_set_to_missing"] == {"temperature_c": 1}
    assert any("fcr" in r for r in m["intervals"])
    json.dumps(m)


def test_opportunities_detect_planted_heat_mortality_link(farm_csv, column_roles):
    r = farm_data.discover_research_opportunities(farm_csv, column_roles, high_temperature_threshold_c=30.0)
    ids = {c["id"] for c in r["candidates"]}
    assert {"thermal_mortality", "species_survival", "temperature_growth", "temperature_fcr", "seasonal_variation", "environmental_interaction"} <= ids
    thermal = next(c for c in r["candidates"] if c["id"] == "thermal_mortality")
    assert thermal["threshold_source"] == "user-supplied"
    a = thermal["evidence"]["SpeciesA"]
    assert a["hot_vs_other_days"]["ratio"] > 1
    assert a["lagged_correlation_temperature_vs_mortality"]["0"]["spearman_rho"] > 0  # JSON keys are strings
    assert all(c["evidence_type"] == "observational association" for c in r["candidates"])
    # density role absent -> skipped with reason, not silently dropped
    assert any(s["id"] == "density_growth" for s in r["skipped_candidates"])
    json.dumps(r)


def test_default_threshold_is_labelled_as_a_default(farm_csv, column_roles):
    r = farm_data.discover_research_opportunities(farm_csv, column_roles)
    thermal = next(c for c in r["candidates"] if c["id"] == "thermal_mortality")
    assert "90th percentile" in thermal["threshold_source"]


def test_species_comparison_flags_low_cage_replication(tmp_path, column_roles):
    df = build_farm_frame()
    df = df[df["Cage"].isin(["A1", "A2", "B1", "B2"])]
    path = tmp_path / "small.csv"
    df.to_csv(path, index=False)
    r = farm_data.discover_research_opportunities(str(path), column_roles)
    sp = next(c for c in r["candidates"] if c["id"] == "species_survival")
    assert sp["data_sufficiency"] != "adequate_for_exploration"
    assert any("independent unit" in reason for reason in sp["sufficiency_reasons"])


def _restocked_farm(tmp_path):
    """Two cages, each harvested and restocked twice (3 cycles)."""
    rows = []
    for cage in ("C1", "C2"):
        for i, d in enumerate(pd.date_range("2023-01-01", periods=900, freq="D")):
            day_in_cycle = i % 300
            fish = 1000 - day_in_cycle  # one death per day, reset on restock
            abw = 30 * math.exp(0.01 * day_in_cycle)
            rows.append({"Date": d.date().isoformat(), "Cage": cage, "Species": "S",
                         "Temp (C)": 26.0 + (i % 7), "Feed (kg)": round(fish * abw / 1000 * 0.02, 2),
                         "Mortality": 1, "ABW (g)": round(abw, 2) if day_in_cycle % 30 == 0 else None,
                         "Fish count": fish})
    path = tmp_path / "restock.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    roles = {"date": "Date", "cage": "Cage", "species": "Species", "temperature_c": "Temp (C)",
             "feed_kg": "Feed (kg)", "mortality_count": "Mortality", "abw_g": "ABW (g)", "fish_count": "Fish count"}
    return str(path), roles


def test_restocking_splits_production_cycles(tmp_path):
    """Regression: survival went negative and FCR exploded when a cage was
    harvested and restocked, because metrics spanned the restock."""
    path, roles = _restocked_farm(tmp_path)
    m = farm_data.compute_performance_metrics(path, roles)
    assert m["cleaning_log"]["production_cycles_per_cage"] == {"C1": 3, "C2": 3}
    complete = [c for c in m["cycles"] if c["complete"]]
    assert len(complete) == 2  # middle cycle of each cage
    for c in complete:
        assert c["survival_pct"] == pytest.approx((1 - 300 / 1000) * 100)
        assert c["sgr"] == pytest.approx(1.0, rel=1e-3)
    assert all(iv["abw_end_g"] > iv["abw_start_g"] for iv in m["intervals"])  # no interval crosses a restock
    assert all(0 <= c["mean_survival_pct"] <= 100 for c in m["per_cage"])
    # cycle FCR is total feed / total gain over the cycle's intervals
    for c in complete:
        ivs = [iv for iv in m["intervals"] if iv["cage"] == c["cage"] and iv["cycle"] == c["cycle"]]
        assert c["fcr"] == pytest.approx(sum(iv["feed_kg"] for iv in ivs) / sum(iv["adjusted_biomass_gain_kg"] for iv in ivs))


def test_fcr_left_undefined_when_gain_is_near_zero(tmp_path):
    path, roles = _restocked_farm(tmp_path)
    df = pd.read_csv(path)
    c1 = df[(df["Cage"] == "C1") & df["ABW (g)"].notna()].index
    df.loc[c1[2], "ABW (g)"] = df.loc[c1[1], "ABW (g)"]  # flat ABW: gain = 0 once dead biomass is credited
    df.to_csv(path, index=False)
    m = farm_data.compute_performance_metrics(path, roles)
    flagged = [iv for iv in m["intervals"] if iv.get("fcr_note")]
    assert flagged and all(iv["fcr"] is None for iv in flagged)
    assert all(iv["fcr"] is None or iv["fcr"] < 100 for iv in m["intervals"])
    q = farm_data.check_data_quality(path, roles)
    checks = {i["check"] for i in q["issues"]}
    assert "abw_decrease" not in checks  # the restock reset is not an ABW drop
    assert "restocking_detected" in checks


def test_abw_entered_in_kg_is_flagged_as_unit_error(tmp_path):
    path, roles = _restocked_farm(tmp_path)
    df = pd.read_csv(path)
    idx = df[(df["Cage"] == "C1") & df["ABW (g)"].notna()].index[3]
    df.loc[idx, "ABW (g)"] = df.loc[idx, "ABW (g)"] / 1000
    df.to_csv(path, index=False)
    q = farm_data.check_data_quality(path, roles)
    assert any(i["check"] == "abw_possible_unit_error" for i in q["issues"])


def test_unsupported_file_type(tmp_path):
    p = tmp_path / "farm.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="unsupported file type"):
        farm_data.load_table(str(p))
