"""Farm-record intelligence: load, profile, quality-check, and scan
operational aquaculture data (Excel/CSV) for candidate research questions.

Backs the Data Intelligence Agent and the Research Opportunity Discovery
Agent. Same philosophy as the rest of this package: every number comes from
pandas/scipy here, never from a model's guess.

Two rules shape every output:

1. Column meaning is never assumed silently. Farms name columns differently
   ("Temp", "WT_C", "Water temperature"), so analysis functions take a
   ``column_roles`` mapping {canonical_role: actual_column}. Use
   ``suggest_column_roles`` to get a starting guess, then confirm it with the
   person who owns the data.
2. Operational data are observational. Everything ``discover_research_opportunities``
   returns is a *candidate association*, labelled as such, with its data
   sufficiency, likely confounders and the caveat that daily farm records are
   autocorrelated (so p-values from daily rows overstate certainty). A
   candidate is a reason to design a study, not a finding.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from aquaculture_manuscript_mcp.tools import calculators

# Canonical roles the analysis functions understand.
ROLES: dict[str, str] = {
    "date": "Record date (daily rows, or sampling date)",
    "cage": "Cage / tank / pond identifier (the experimental or production unit)",
    "species": "Species name",
    "batch": "Stocking batch / cohort identifier",
    "temperature_c": "Water temperature (degrees C)",
    "salinity_ppt": "Salinity (ppt / PSU)",
    "do_mg_l": "Dissolved oxygen (mg/L)",
    "ph": "pH",
    "feed_kg": "Feed given that day (kg)",
    "mortality_count": "Number of dead fish recorded that day",
    "abw_g": "Average body weight at sampling (g); usually only on sampling days",
    "fish_count": "Number of live fish in the unit",
    "stocking_density_kg_m3": "Stocking density (kg/m3)",
    "biomass_kg": "Standing biomass (kg)",
    "cost": "Operational cost for the row (any currency, stated by the user)",
}

# Keyword heuristics for suggest_column_roles (lower-case substring match).
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "date": ["date", "day", "time"],
    "cage": ["cage", "tank", "pond", "net", "unit", "pen"],
    "species": ["species", "fish type", "sp."],
    "batch": ["batch", "cohort", "lot", "stocking id"],
    "temperature_c": ["temp", "wt_c", "°c", "deg"],
    "salinity_ppt": ["salin", "ppt", "psu"],
    "do_mg_l": ["do_", "do ", "dissolved", "oxygen", "o2"],
    "ph": ["ph"],
    "feed_kg": ["feed"],
    "mortality_count": ["mort", "dead", "death"],
    "abw_g": ["abw", "body weight", "avg weight", "average weight", "mean weight"],
    "fish_count": ["count", "number of fish", "no. fish", "stock no", "live fish", "population"],
    "stocking_density_kg_m3": ["density"],
    "biomass_kg": ["biomass"],
    "cost": ["cost", "expense"],
}

# Physically plausible bounds (NOT optimal ranges). A value outside these is
# almost certainly a recording/entry error, whatever the species.
PLAUSIBLE_RANGES: dict[str, tuple[float | None, float | None]] = {
    "temperature_c": (-2.0, 40.0),
    "salinity_ppt": (0.0, 60.0),
    "do_mg_l": (0.0, 25.0),
    "ph": (4.0, 10.5),
    "feed_kg": (0.0, None),
    "mortality_count": (0.0, None),
    "abw_g": (0.0, None),
    "fish_count": (0.0, None),
    "stocking_density_kg_m3": (0.0, 200.0),
    "biomass_kg": (0.0, None),
}

NUMERIC_ROLES = [r for r in ROLES if r not in ("date", "cage", "species", "batch")]

# Interval FCR is reported only when biomass gain is at least this fraction of
# start biomass; below it the ratio is numerically unstable (gain ~ 0).
MIN_GAIN_FRACTION_FOR_FCR = 0.005

OBSERVATIONAL_CAVEAT = (
    "Observational farm data: this is an association, not evidence of cause. "
    "Daily records from the same cage are autocorrelated, so p-values computed "
    "on daily rows overstate certainty. Treat as a candidate for a designed "
    "study, not a finding."
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _py(value):
    """Convert numpy/pandas scalars and containers to JSON-safe Python."""
    if isinstance(value, dict):
        return {str(k): _py(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_py(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.date().isoformat()
    if value is pd.NaT:
        return None
    return value


def _row_examples(frame: pd.DataFrame, cols: list[str], limit: int = 5) -> list[dict]:
    """Example records with the spreadsheet row number ("row": header is
    row 1, so data row index i is row i + 2) for corrections by row."""
    cols = [c for c in dict.fromkeys(cols) if c in frame.columns]
    out = frame[cols].head(limit).copy()
    out.insert(0, "row", out.index + 2)
    return out.to_dict("records")


def load_table(path: str, sheet: str | None = None) -> pd.DataFrame:
    """Load a CSV or Excel file into a DataFrame."""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"file not found: {path}")
    suffix = p.suffix.lower()
    if suffix in (".csv", ".txt"):
        return pd.read_csv(p)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(p, sheet_name=sheet or 0)
    raise ValueError(f"unsupported file type '{suffix}' — use .csv, .xlsx, .xlsm or .xls")


def _validate_roles(df: pd.DataFrame, column_roles: dict[str, str]) -> None:
    unknown_roles = sorted(set(column_roles) - set(ROLES))
    if unknown_roles:
        raise ValueError(f"unknown role(s) {unknown_roles}. Known roles: {sorted(ROLES)}")
    missing_cols = sorted(c for c in column_roles.values() if c not in df.columns)
    if missing_cols:
        raise ValueError(f"column(s) {missing_cols} not in the file. Columns present: {list(df.columns)}")


def _canonical(df: pd.DataFrame, column_roles: dict[str, str]) -> pd.DataFrame:
    """Return a frame with canonical role names, parsed dates and numeric columns."""
    _validate_roles(df, column_roles)
    out = pd.DataFrame({role: df[col] for role, col in column_roles.items()})
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for role in NUMERIC_ROLES:
        if role in out:
            out[role] = pd.to_numeric(out[role], errors="coerce")
    for role in ("cage", "species", "batch"):
        if role in out:
            out[role] = out[role].astype("string").str.strip()
    return out


def _clean_for_analysis(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Drop exact duplicates, blank implausible values, collapse duplicate
    cage-day keys. Returns the frame plus a record of everything changed."""
    log: dict = {}
    n0 = len(df)
    df = df.drop_duplicates()
    log["exact_duplicate_rows_dropped"] = n0 - len(df)

    excluded = {}
    for role, (lo, hi) in PLAUSIBLE_RANGES.items():
        if role not in df:
            continue
        bad = pd.Series(False, index=df.index)
        if lo is not None:
            bad |= df[role] < lo
        if hi is not None:
            bad |= df[role] > hi
        if bad.any():
            excluded[role] = int(bad.sum())
            df.loc[bad, role] = np.nan
    log["implausible_values_set_to_missing"] = excluded

    if "date" in df:
        bad_dates = int(df["date"].isna().sum())
        df = df[df["date"].notna()]
        log["rows_dropped_unparseable_date"] = bad_dates

    if {"date", "cage"} <= set(df.columns):
        dup_keys = int(df.duplicated(["cage", "date"]).sum())
        df = df.drop_duplicates(["cage", "date"], keep="first")
        log["duplicate_cage_date_rows_dropped_keep_first"] = dup_keys
    df = df.sort_values([c for c in ("cage", "date") if c in df.columns]).reset_index(drop=True)
    df["cycle"] = _cycle_index(df)
    if "cage" in df:
        log["production_cycles_per_cage"] = {str(k): int(v) for k, v in df.groupby("cage")["cycle"].nunique().items()}
    return df, log


def _cycle_index(df: pd.DataFrame) -> pd.Series:
    """Production cycle number within each cage. A new cycle starts wherever
    the live fish count goes UP (restocking after harvest), because SGR,
    FCR and survival must never be computed across a restock. Without a
    fish_count column every cage is treated as one cycle."""
    if not {"cage", "fish_count"} <= set(df.columns):
        return pd.Series(0, index=df.index)
    return df.groupby("cage")["fish_count"].transform(lambda s: (s.ffill().diff() > 0).cumsum()).astype(int)


# ---------------------------------------------------------------------------
# Data Intelligence Agent tools
# ---------------------------------------------------------------------------


def suggest_column_roles(path: str, sheet: str | None = None) -> dict:
    """Guess which column plays which canonical role, from column names only.
    A suggestion for the data owner to confirm — never use it unconfirmed."""
    df = load_table(path, sheet)
    suggestions: dict[str, str] = {}
    used: set[str] = set()
    for role, keywords in _ROLE_KEYWORDS.items():
        for col in df.columns:
            name = str(col).lower()
            if col in used:
                continue
            if role == "ph" and name.strip() not in ("ph", "p h") and not name.startswith("ph "):
                continue
            if any(k in name for k in keywords):
                suggestions[role] = str(col)
                used.add(col)
                break
    return {
        "suggested_column_roles": suggestions,
        "unmatched_columns": [str(c) for c in df.columns if c not in used],
        "known_roles": ROLES,
        "note": "Heuristic match on column names only. Confirm every mapping (and units) with the data owner before analysis.",
    }


def profile_dataset(path: str, sheet: str | None = None) -> dict:
    """Structure of a dataset: rows, columns, types, missing values,
    duplicates, numeric summaries, categorical levels and date ranges."""
    df = load_table(path, sheet)
    columns = {}
    for col in df.columns:
        s = df[col]
        info: dict = {
            "dtype": str(s.dtype),
            "missing": int(s.isna().sum()),
            "missing_pct": float(s.isna().mean() * 100),
            "unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            d = s.describe()
            info.update({k: d.get(k) for k in ("mean", "std", "min", "25%", "50%", "75%", "max")})
        else:
            parsed = pd.to_datetime(s, errors="coerce", format="mixed") if s.notna().any() else s
            if hasattr(parsed, "notna") and parsed.notna().mean() > 0.8:
                info["looks_like_date"] = True
                info["date_min"] = parsed.min()
                info["date_max"] = parsed.max()
            elif s.nunique(dropna=True) <= 30:
                info["levels"] = s.value_counts(dropna=True).to_dict()
        columns[str(col)] = info
    return _py(
        {
            "file": str(path),
            "rows": len(df),
            "columns": len(df.columns),
            "exact_duplicate_rows": int(df.duplicated().sum()),
            "column_profiles": columns,
        }
    )


def check_data_quality(path: str, column_roles: dict[str, str], sheet: str | None = None) -> dict:
    """Quality report for farm records: missing values, duplicates,
    physically implausible values, extreme outliers, gaps in daily records,
    and biologically suspicious sequences (ABW drops, fish counts rising
    without restocking). Reports problems; does not fix the source file."""
    raw = load_table(path, sheet)
    df = _canonical(raw, column_roles)
    issues: list[dict] = []

    def add(severity: str, check: str, detail: str, count: int, examples=None):
        issues.append({"severity": severity, "check": check, "detail": detail, "count": count, "examples": examples or []})

    for role in column_roles:
        n_missing = int(df[role].isna().sum())
        if n_missing and role != "abw_g":
            add("warning", "missing_values", f"{role} ({column_roles[role]}) has missing values", n_missing)
    if "date" in df:
        n_bad = int(df["date"].isna().sum() - raw[column_roles["date"]].isna().sum())
        if n_bad > 0:
            add("error", "unparseable_dates", "date values that could not be parsed", n_bad)

    key_cols = [c for c in ("date", "cage") if c in df]
    n_dup = int(df.duplicated().sum())
    if n_dup:
        add("warning", "exact_duplicate_rows", "identical rows (likely double entry); the later copy is listed", n_dup,
            _row_examples(df[df.duplicated()], key_cols))
    if {"date", "cage"} <= set(df.columns):
        keydup = df[df.duplicated(["cage", "date"], keep=False) & ~df.duplicated(keep=False)]
        if len(keydup):
            add(
                "error",
                "conflicting_cage_date_rows",
                "same cage and date recorded more than once with different values",
                int(len(keydup)),
                _row_examples(keydup, list(keydup.columns), limit=10),
            )

    for role, (lo, hi) in PLAUSIBLE_RANGES.items():
        if role not in df:
            continue
        s = df[role]
        bad = pd.Series(False, index=df.index)
        if lo is not None:
            bad |= s < lo
        if hi is not None:
            bad |= s > hi
        if bad.any():
            add(
                "error",
                "implausible_value",
                f"{role} outside physically plausible range {lo}–{hi}",
                int(bad.sum()),
                _row_examples(df.loc[bad], key_cols + [role]),
            )
        valid = s[~bad].dropna()
        if len(valid) >= 20:
            med = valid.median()
            mad = (valid - med).abs().median()
            if mad > 0:
                z = 0.6745 * (valid - med) / mad
                extreme = z.abs() > 5
                if extreme.any():
                    idx = valid[extreme].index
                    add(
                        "info",
                        "extreme_outlier",
                        f"{role} values with robust z-score > 5 (check, may be real events)",
                        int(extreme.sum()),
                        _row_examples(df.loc[idx], key_cols + [role]),
                    )

    coverage = {}
    if {"date", "cage"} <= set(df.columns):
        for cage, g in df.dropna(subset=["date"]).groupby("cage"):
            days = g["date"].dt.normalize().drop_duplicates().sort_values()
            span = (days.max() - days.min()).days + 1
            coverage[str(cage)] = {
                "first": days.min(),
                "last": days.max(),
                "days_with_records": int(len(days)),
                "days_missing_in_span": int(span - len(days)),
            }
            if span - len(days) > 0:
                add("info", "date_gaps", f"cage {cage}: {span - len(days)} day(s) without a record inside its date span", int(span - len(days)))

        cyc = df.sort_values(["cage", "date"]).copy()
        cyc["cycle"] = _cycle_index(cyc)
        if "abw_g" in df:
            for (cage, _cycle), g in cyc.dropna(subset=["abw_g", "date"]).groupby(["cage", "cycle"]):
                s = g.groupby("date")["abw_g"].mean().sort_index()
                change = s.pct_change()
                unit = change[change < -0.90]
                drops = change[(change < -0.10) & (change >= -0.90)]
                if len(unit):
                    add(
                        "error",
                        "abw_possible_unit_error",
                        f"cage {cage}: ABW fell >90% between samplings within one production cycle (kg entered instead of g?)",
                        int(len(unit)),
                        _row_examples(g[g["date"].isin(unit.index)], key_cols + ["abw_g"]),
                    )
                if len(drops):
                    add(
                        "warning",
                        "abw_decrease",
                        f"cage {cage}: ABW fell >10% between consecutive samplings within one production cycle (sampling error, grading or a real loss?)",
                        int(len(drops)),
                        _row_examples(g[g["date"].isin(drops.index)], key_cols + ["abw_g"]),
                    )
        if "fish_count" in df:
            for cage, g in df.dropna(subset=["fish_count", "date"]).sort_values("date").groupby("cage"):
                rises = g[g["fish_count"].diff() > 0]
                if len(rises):
                    add(
                        "info",
                        "restocking_detected",
                        f"cage {cage}: live fish count increased; treated as the start of a new production cycle (confirm: restocking, transfer or entry error?)",
                        int(len(rises)),
                        _row_examples(rises, key_cols + ["fish_count"]),
                    )

    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: order[i["severity"]])
    return _py(
        {
            "rows": len(df),
            "column_roles": column_roles,
            "issue_counts": {s: sum(1 for i in issues if i["severity"] == s) for s in order},
            "issues": issues,
            "coverage_by_cage": coverage,
            "note": "Errors should be resolved with the data owner before analysis. Analysis tools in this module drop exact duplicates, keep the first of conflicting cage-date rows, and treat implausible values as missing — and report every such change.",
        }
    )


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"mortality_count", "fish_count"} <= set(out.columns):
        out["mortality_rate_pct"] = out["mortality_count"] / out["fish_count"] * 100
    if "date" in out:
        out["month"] = out["date"].dt.month
        out["season"] = out["month"].map(
            {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
             6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
        )
    return out


def compute_sampling_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (cage, consecutive pair of ABW sampling dates): SGR, mean
    environment over the interval, feed and mortality totals, and FCR when
    fish counts are available. Requires roles: date, cage, abw_g."""
    need = {"date", "cage", "abw_g"}
    if not need <= set(df.columns):
        raise ValueError(f"sampling intervals need roles {sorted(need)}")
    if "cycle" not in df:
        df = df.sort_values(["cage", "date"]).assign(cycle=lambda d: _cycle_index(d))
    rows = []
    for (cage, cycle), g in df.groupby(["cage", "cycle"]):
        g = g.sort_values("date")
        samples = g.dropna(subset=["abw_g"]).groupby("date")["abw_g"].mean().sort_index()
        species = g["species"].mode().iloc[0] if "species" in g and g["species"].notna().any() else None
        for (d0, w0), (d1, w1) in zip(samples.items(), list(samples.items())[1:]):
            days = (d1 - d0).days
            if days <= 0 or w0 <= 0 or w1 <= 0:
                continue
            window = g[(g["date"] >= d0) & (g["date"] < d1)]
            row = {
                "cage": cage,
                "cycle": cycle,
                "species": species,
                "start": d0,
                "end": d1,
                "days": days,
                "abw_start_g": w0,
                "abw_end_g": w1,
                "sgr": calculators.calculate_sgr(w0, w1, days)["sgr_percent_per_day"],
            }
            for env in ("temperature_c", "salinity_ppt", "do_mg_l", "ph", "stocking_density_kg_m3"):
                if env in window:
                    row[f"mean_{env}"] = window[env].mean()
            if "temperature_c" in window:
                row["max_temperature_c"] = window["temperature_c"].max()
            if "do_mg_l" in window:
                row["min_do_mg_l"] = window["do_mg_l"].min()
            if "mortality_count" in window:
                row["mortality"] = window["mortality_count"].sum()
            if "feed_kg" in window:
                row["feed_kg"] = window["feed_kg"].sum(min_count=1)
            if "fish_count" in g:
                c0 = g.loc[g["date"] <= d0, "fish_count"].dropna()
                c1 = g.loc[g["date"] <= d1, "fish_count"].dropna()
                if len(c0) and len(c1):
                    n0, n1 = c0.iloc[-1], c1.iloc[-1]
                    row["fish_start"], row["fish_end"] = n0, n1
                    if n0 > 0:
                        row["interval_mortality_pct"] = row.get("mortality", np.nan) / n0 * 100
                    b0, b1 = n0 * w0 / 1000, n1 * w1 / 1000
                    dead_kg = row.get("mortality", 0) * (w0 + w1) / 2 / 1000
                    gain = (b1 + dead_kg) - b0
                    row["biomass_start_kg"] = b0
                    row["adjusted_biomass_gain_kg"] = gain
                    feed = row.get("feed_kg")
                    if feed is not None and not pd.isna(feed) and b0 > 0 and b1 > 0:
                        if gain < MIN_GAIN_FRACTION_FOR_FCR * b0:
                            row["fcr"] = np.nan
                            row["fcr_note"] = (
                                f"FCR undefined: biomass gain {gain:.1f} kg is below "
                                f"{MIN_GAIN_FRACTION_FOR_FCR:.1%} of start biomass (ratio unstable or negative)"
                            )
                        else:
                            row["fcr"] = calculators.calculate_biomass_corrected_fcr(
                                feed, b0, b1, dead_or_removed_biomass_g=dead_kg
                            )["biomass_corrected_fcr"]
            rows.append(row)
    return pd.DataFrame(rows)


def compute_cycle_summaries(df: pd.DataFrame, intervals: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (cage, production cycle): dates, initial fish, deaths,
    survival, SGR over the cycle's ABW samples, feed and mean interval FCR.
    ``complete`` is True only for cycles whose start (a restock) and end
    (the next restock) both fall inside the record; the first and last
    cycles of a cage are usually partial."""
    if "cage" not in df:
        return pd.DataFrame()
    if "cycle" not in df:
        df = df.sort_values(["cage", "date"]).assign(cycle=lambda d: _cycle_index(d))
    rows = []
    for cage, gc in df.groupby("cage"):
        last_cycle = gc["cycle"].max()
        for cycle, g in gc.groupby("cycle"):
            rec: dict = {"cage": cage, "cycle": cycle, "complete": bool(0 < cycle < last_cycle)}
            if "species" in g and g["species"].notna().any():
                rec["species"] = g["species"].mode().iloc[0]
            if "date" in g:
                rec["start"], rec["end"] = g["date"].min(), g["date"].max()
                rec["days"] = (rec["end"] - rec["start"]).days + 1
            if "mortality_count" in g:
                rec["deaths"] = g["mortality_count"].sum()
            if "fish_count" in g and g["fish_count"].notna().any():
                first = g["fish_count"].dropna().iloc[0]
                rec["initial_fish_count"] = first
                if "mortality_count" in g and first > 0:
                    rec["survival_pct"] = (1 - g["mortality_count"].sum() / first) * 100
            if "feed_kg" in g:
                rec["feed_kg"] = g["feed_kg"].sum()
            if intervals is not None and len(intervals):
                ci = intervals[(intervals["cage"] == cage) & (intervals["cycle"] == cycle)]
                if len(ci):
                    rec["abw_first_g"], rec["abw_last_g"] = ci["abw_start_g"].iloc[0], ci["abw_end_g"].iloc[-1]
                    span = (ci["end"].iloc[-1] - ci["start"].iloc[0]).days
                    rec["sgr"] = calculators.calculate_sgr(rec["abw_first_g"], rec["abw_last_g"], span)["sgr_percent_per_day"]
                    if {"feed_kg", "adjusted_biomass_gain_kg"} <= set(ci.columns):
                        both = ci.dropna(subset=["feed_kg", "adjusted_biomass_gain_kg"])
                        total_gain = both["adjusted_biomass_gain_kg"].sum()
                        if len(both) and total_gain > 0:
                            # Production FCR: total feed / total gain, not a mean of interval ratios.
                            rec["fcr"] = both["feed_kg"].sum() / total_gain
            rows.append(rec)
    return pd.DataFrame(rows)


def compute_performance_metrics(path: str, column_roles: dict[str, str], sheet: str | None = None) -> dict:
    """Per-production-cycle, per-cage and per-interval growth (SGR), FCR and
    survival derived from raw farm records, after the documented cleaning
    steps. Restocking (fish count rising) starts a new cycle; nothing is
    computed across a restock."""
    df, log = _clean_for_analysis(_canonical(load_table(path, sheet), column_roles))
    intervals = compute_sampling_intervals(df) if {"date", "cage", "abw_g"} <= set(df.columns) else pd.DataFrame()
    cycles = compute_cycle_summaries(df, intervals)

    per_cage = []
    if len(cycles):
        for cage, g in cycles.groupby("cage"):
            done = g[g["complete"]]
            basis = done if len(done) else g
            rec = {
                "cage": cage,
                "species": g["species"].iloc[0] if "species" in g else None,
                "cycles_in_record": len(g),
                "complete_cycles": len(done),
                "summary_basis": "complete cycles" if len(done) else "all (partial) cycles — no complete cycle in the record",
            }
            for col in ("survival_pct", "sgr", "fcr"):
                if col in basis:
                    rec[f"mean_{col}"] = basis[col].mean()
            per_cage.append(rec)

    return _py(
        {
            "cleaning_log": log,
            "per_cage": per_cage,
            "cycles": cycles.to_dict("records") if len(cycles) else [],
            "intervals": intervals.to_dict("records") if len(intervals) else [],
            "formulae": {
                "sgr": "SGR (%/day) = (ln ABW_end - ln ABW_start) / days x 100",
                "fcr": "biomass-corrected FCR = feed / ((biomass_end + dead biomass) - biomass_start); dead biomass = deaths x mean of start/end ABW. Interval FCR left undefined when gain < 0.5% of start biomass. Cycle FCR = total feed / total adjusted gain over the cycle's intervals.",
                "survival": "survival % = (1 - deaths in cycle / fish count at cycle start) x 100, per production cycle; per-cage means use complete cycles only",
            },
        }
    )


def build_analysis_table(
    path: str,
    column_roles: dict[str, str],
    level: str = "interval",
    sheet: str | None = None,
    temperature_lags: list[int] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Analysis-ready table at one of three levels:
    - "daily": one row per cage-day after cleaning, plus cycle, day_index
      (days since the cage's first record, for time-series models),
      mortality_rate_pct, log_fish_count (offset for count models), season,
      and temperature lagged by the requested days within each cage.
    - "interval": one row per cage x sampling interval (SGR, FCR, mean environment).
    - "cycle": one row per cage x production cycle.
    """
    if level not in ("daily", "interval", "cycle"):
        raise ValueError("level must be 'daily', 'interval' or 'cycle'")
    df, log = _clean_for_analysis(_canonical(load_table(path, sheet), column_roles))
    if level == "daily":
        out = _daily(df)
        if {"cage", "date"} <= set(out.columns):
            out["day_index"] = (out["date"] - out.groupby("cage")["date"].transform("min")).dt.days
        if "fish_count" in out:
            out["log_fish_count"] = np.log(out["fish_count"].where(out["fish_count"] > 0))
        for lag in temperature_lags or []:
            if lag < 1 or "temperature_c" not in out:
                raise ValueError("temperature_lags must be positive integers and need the temperature_c role")
            # Lag by calendar day within cage, so a missing day isn't silently skipped over.
            shifted = out[["cage", "date", "temperature_c"]].copy()
            shifted["date"] = shifted["date"] + pd.Timedelta(days=lag)
            out = out.merge(shifted.rename(columns={"temperature_c": f"temperature_c_lag{lag}"}), on=["cage", "date"], how="left")
        return out, log
    intervals = compute_sampling_intervals(df)
    if level == "interval":
        return intervals, log
    return compute_cycle_summaries(df, intervals), log


def export_analysis_table(
    path: str,
    column_roles: dict[str, str],
    output_path: str,
    level: str = "interval",
    sheet: str | None = None,
    temperature_lags: list[int] | None = None,
) -> dict:
    """Write an analysis-ready table (daily, interval or cycle level) to CSV
    for the modelling, effect-size and figure tools."""
    table, log = build_analysis_table(path, column_roles, level, sheet, temperature_lags)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_path, index=False)
    return _py(
        {
            "output_path": output_path,
            "level": level,
            "rows": len(table),
            "columns": list(table.columns),
            "cleaning_log": log,
        }
    )


# ---------------------------------------------------------------------------
# Research Opportunity Discovery Agent tool
# ---------------------------------------------------------------------------


def _spearman(x: pd.Series, y: pd.Series) -> dict | None:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 8 or d.iloc[:, 0].nunique() < 3 or d.iloc[:, 1].nunique() < 3:
        return None
    rho, p = scipy_stats.spearmanr(d.iloc[:, 0], d.iloc[:, 1])
    return {"spearman_rho": rho, "p_value": p, "n": len(d)}


def _sufficiency(n_units: int, n_obs: int, min_units: int = 3, min_obs: int = 30) -> tuple[str, list[str]]:
    reasons = []
    if n_units < min_units:
        reasons.append(f"only {n_units} independent unit(s) (cages); at least {min_units} per group are needed for a unit-level comparison")
    if n_obs < min_obs:
        reasons.append(f"only {n_obs} observations")
    if not reasons:
        return "adequate_for_exploration", reasons
    return ("insufficient" if n_units < 2 or n_obs < 10 else "limited"), reasons


def discover_research_opportunities(
    path: str,
    column_roles: dict[str, str],
    sheet: str | None = None,
    high_temperature_threshold_c: float | None = None,
    max_lag_days: int = 7,
) -> dict:
    """Scan farm records for candidate research questions. Each candidate
    gives the draft question, the evidence computed, data sufficiency,
    likely confounders and the next step. Candidates whose required roles
    are missing are listed as skipped, with the reason."""
    df, log = _clean_for_analysis(_canonical(load_table(path, sheet), column_roles))
    df = _daily(df)
    has = set(df.columns)
    intervals = compute_sampling_intervals(df) if {"date", "cage", "abw_g"} <= has else pd.DataFrame()
    species_list = sorted(df["species"].dropna().unique()) if "species" in has else [None]
    candidates: list[dict] = []
    skipped: list[dict] = []

    def by_species(frame: pd.DataFrame):
        if "species" in frame and frame["species"].notna().any():
            yield from frame.groupby("species")
        else:
            yield "all", frame

    mort_col = "mortality_rate_pct" if "mortality_rate_pct" in df else "mortality_count"

    # 1. Thermal stress and mortality --------------------------------------
    if {"temperature_c", "mortality_count", "date", "cage"} <= has:
        threshold = high_temperature_threshold_c
        threshold_source = "user-supplied"
        if threshold is None:
            threshold = float(df["temperature_c"].quantile(0.90))
            threshold_source = "90th percentile of recorded temperature (no threshold supplied — replace with a literature or species-specific value)"
        evidence = {}
        for sp, g in by_species(df):
            lags = {}
            for lag in range(0, max_lag_days + 1):
                shifted = g.groupby("cage")["temperature_c"].shift(lag)
                r = _spearman(shifted, g[mort_col])
                if r:
                    lags[lag] = r
            hot = g[g["temperature_c"] >= threshold][mort_col].dropna()
            cool = g[g["temperature_c"] < threshold][mort_col].dropna()
            comp = None
            if len(hot) >= 5 and len(cool) >= 5:
                u, p = scipy_stats.mannwhitneyu(hot, cool, alternative="two-sided")
                comp = {
                    "mean_mortality_hot_days": hot.mean(),
                    "mean_mortality_other_days": cool.mean(),
                    "ratio": (hot.mean() / cool.mean()) if cool.mean() > 0 else None,
                    "mann_whitney_u": u,
                    "p_value": p,
                    "n_hot_days": len(hot),
                    "n_other_days": len(cool),
                }
            best = max(lags.items(), key=lambda kv: abs(kv[1]["spearman_rho"])) if lags else None
            evidence[str(sp)] = {
                "n_cages": int(g["cage"].nunique()),
                "lagged_correlation_temperature_vs_mortality": lags,
                "strongest_lag_days": best[0] if best else None,
                "hot_vs_other_days": comp,
            }
        n_units = int(df["cage"].nunique())
        suff, reasons = _sufficiency(n_units, int(df[["temperature_c", "mortality_count"]].dropna().shape[0]))
        candidates.append(
            {
                "id": "thermal_mortality",
                "topic": "Thermal tolerance",
                "draft_research_question": f"Is daily mortality higher when water temperature reaches or exceeds {threshold:.1f} °C, and does the response differ between species and with a time lag?",
                "variables": ["temperature_c", mort_col, "species", "cage", "date"],
                "method": f"Spearman correlation of temperature (lagged 0–{max_lag_days} d, within cage) with {mort_col}; Mann–Whitney comparison of mortality on days >= threshold vs other days, per species.",
                "high_temperature_threshold_c": threshold,
                "threshold_source": threshold_source,
                "evidence": evidence,
                "data_sufficiency": suff,
                "sufficiency_reasons": reasons,
                "multiple_testing_note": f"{max_lag_days + 1} lags tested per species; the 'strongest lag' is selected post hoc and must be confirmed, not reported as a finding.",
                "likely_confounders": ["dissolved oxygen (falls as temperature rises)", "season and fish size/age", "disease outbreaks", "handling, grading or harvest events", "feeding changes during heat"],
                "next_step": "Pre-register the threshold from literature, then fit a mixed model (cage as random effect, temporal autocorrelation) or design a controlled thermal-challenge trial for causal evidence.",
                "evidence_type": "observational association",
            }
        )
    else:
        skipped.append({"id": "thermal_mortality", "needs_roles": ["temperature_c", "mortality_count", "date", "cage"]})

    # 2. Species comparison of survival -------------------------------------
    if {"species", "cage", "mortality_count", "fish_count"} <= has:
        cyc = compute_cycle_summaries(df)
        use_complete = bool(cyc["complete"].any()) if len(cyc) else False
        basis = cyc[cyc["complete"]] if use_complete else cyc
        per_cage = [
            {"cage": cage, "species": g["species"].iloc[0], "survival_pct": g["survival_pct"].mean(), "cycles_used": len(g)}
            for cage, g in basis.dropna(subset=["survival_pct"]).groupby("cage")
        ] if len(basis) else []
        pc = pd.DataFrame(per_cage)
        groups = {sp: g["survival_pct"].tolist() for sp, g in pc.groupby("species")} if len(pc) else {}
        test = None
        if len(groups) >= 2 and all(len(v) >= 2 for v in groups.values()):
            h, p = scipy_stats.kruskal(*groups.values())
            test = {"test": "Kruskal–Wallis on per-cage survival", "h_statistic": h, "p_value": p}
        min_cages = min((len(v) for v in groups.values()), default=0)
        suff, reasons = _sufficiency(min_cages, len(pc), min_obs=6)
        if not use_complete:
            reasons.append("no complete production cycle in the record: survival compares partial cycles of different lengths")
            suff = "limited" if suff == "adequate_for_exploration" else suff
        candidates.append(
            {
                "id": "species_survival",
                "topic": "Species comparison",
                "draft_research_question": "Does survival over a production cycle differ between species reared under the same farm conditions?",
                "variables": ["species", "cage", "cycle", "survival_pct"],
                "method": f"Per-cycle survival averaged per cage over {'complete' if use_complete else 'all (partial)'} production cycles (cage = experimental unit), compared across species with Kruskal–Wallis.",
                "evidence": {"per_cage_survival": per_cage, "survival_by_species": {k: {"cages": len(v), "mean": float(np.mean(v))} for k, v in groups.items()}, "test": test},
                "data_sufficiency": suff,
                "sufficiency_reasons": reasons,
                "likely_confounders": ["stocking date and season", "initial fish size and hatchery source", "cage position (exposure, current)", "stocking density"],
                "next_step": "Check whether species were stocked at comparable times and sizes; if not, compare within matched periods or design a side-by-side trial.",
                "evidence_type": "observational association",
            }
        )
    else:
        skipped.append({"id": "species_survival", "needs_roles": ["species", "cage", "mortality_count", "fish_count"]})

    # 3–4. Temperature vs growth / FCR (interval level) ----------------------
    for cid, metric, topic, q in (
        ("temperature_growth", "sgr", "Growth performance", "How does specific growth rate change with mean water temperature over the sampling interval, and is there an optimum or upper limit for each species?"),
        ("temperature_fcr", "fcr", "Feed efficiency", "How does feed conversion ratio change with water temperature, and above which temperature does feeding become inefficient?"),
    ):
        if len(intervals) and metric in intervals and "mean_temperature_c" in intervals:
            evidence = {}
            for sp, g in by_species(intervals):
                r = _spearman(g["mean_temperature_c"], g[metric])
                quad = None
                gg = g[["mean_temperature_c", metric]].dropna()
                if len(gg) >= 10:
                    coef = np.polyfit(gg["mean_temperature_c"], gg[metric], 2)
                    vertex = -coef[1] / (2 * coef[0]) if coef[0] != 0 else None
                    quad = {
                        "quadratic_coefficients": list(coef),
                        "vertex_temperature_c": vertex if vertex and gg["mean_temperature_c"].min() <= vertex <= gg["mean_temperature_c"].max() else None,
                        "note": "Descriptive curve fit only; vertex reported only if inside the observed temperature range.",
                    }
                evidence[str(sp)] = {"n_intervals": len(gg), "n_cages": int(g["cage"].nunique()), "correlation": r, "quadratic_fit": quad}
            suff, reasons = _sufficiency(int(intervals["cage"].nunique()), int(intervals[metric].notna().sum()), min_obs=20)
            candidates.append(
                {
                    "id": cid,
                    "topic": topic,
                    "draft_research_question": q,
                    "variables": ["mean_temperature_c", metric, "species", "cage"],
                    "method": f"Per sampling interval: {metric.upper()} vs mean temperature (Spearman; descriptive quadratic fit per species).",
                    "evidence": evidence,
                    "data_sufficiency": suff,
                    "sufficiency_reasons": reasons,
                    "likely_confounders": ["fish size (SGR falls with size regardless of temperature)", "feeding rate and feed type", "dissolved oxygen", "ABW sampling error (small samples)"],
                    "next_step": "Add fish size as a covariate (e.g. mixed model with cage random effect) before interpreting a temperature effect.",
                    "evidence_type": "observational association",
                }
            )
        else:
            skipped.append({"id": cid, "needs_roles": ["date", "cage", "abw_g", "temperature_c"] + (["feed_kg", "fish_count"] if metric == "fcr" else [])})

    # 5. Seasonal variation ---------------------------------------------------
    if "season" in df and (len(intervals) or "mortality_count" in has):
        evidence = {}
        for sp, g in by_species(df):
            e = {}
            if "mortality_count" in g:
                seasonal = {s: grp[mort_col].dropna().tolist() for s, grp in g.groupby("season")}
                seasonal = {k: v for k, v in seasonal.items() if len(v) >= 5}
                if len(seasonal) >= 2:
                    h, p = scipy_stats.kruskal(*seasonal.values())
                    e["mortality_by_season"] = {k: float(np.mean(v)) for k, v in seasonal.items()}
                    e["mortality_kruskal"] = {"h_statistic": h, "p_value": p}
            if len(intervals) and "species" in intervals:
                iv = intervals[intervals["species"] == sp] if sp != "all" else intervals
                iv = iv.assign(season=pd.to_datetime(iv["start"]).dt.month.map(
                    {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
                     6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}))
                e["sgr_by_season"] = iv.groupby("season")["sgr"].mean().to_dict()
            evidence[str(sp)] = e
        suff, reasons = _sufficiency(int(df["cage"].nunique()) if "cage" in df else 0, len(df))
        years = int(df["date"].dt.year.nunique())
        if years < 2:
            reasons.append("less than two years of records: season is confounded with fish age/size")
            suff = "limited"
        candidates.append(
            {
                "id": "seasonal_variation",
                "topic": "Seasonal effects",
                "draft_research_question": "How do growth and mortality vary across seasons, and is the pattern consistent between years and species?",
                "variables": ["season", mort_col, "sgr", "species"],
                "method": "Season means of daily mortality (Kruskal–Wallis) and interval SGR, per species. Seasons are Northern-Hemisphere meteorological seasons.",
                "years_of_data": years,
                "evidence": evidence,
                "data_sufficiency": suff,
                "sufficiency_reasons": reasons,
                "likely_confounders": ["fish age/size progression within a production cycle", "stocking and harvest timing", "season bundles temperature, DO, salinity and day length together"],
                "next_step": "Compare like-for-like size classes across years; decompose season into temperature, DO and salinity effects.",
                "evidence_type": "observational association",
            }
        )

    # 6. Environmental interaction (DO, salinity) -----------------------------
    env_roles = [r for r in ("do_mg_l", "salinity_ppt") if r in has]
    if env_roles and "mortality_count" in has:
        evidence = {}
        for sp, g in by_species(df):
            e = {r: _spearman(g[r], g[mort_col]) for r in env_roles}
            if {"temperature_c", "do_mg_l"} <= has:
                t_hi = g["temperature_c"] >= g["temperature_c"].quantile(0.75)
                do_lo = g["do_mg_l"] <= g["do_mg_l"].quantile(0.25)
                cells = {
                    "hot_and_low_do": g.loc[t_hi & do_lo, mort_col].mean(),
                    "hot_only": g.loc[t_hi & ~do_lo, mort_col].mean(),
                    "low_do_only": g.loc[~t_hi & do_lo, mort_col].mean(),
                    "neither": g.loc[~t_hi & ~do_lo, mort_col].mean(),
                    "n_days_hot_and_low_do": int((t_hi & do_lo).sum()),
                }
                e["combined_temperature_do_mean_mortality"] = cells
            evidence[str(sp)] = e
        suff, reasons = _sufficiency(int(df["cage"].nunique()) if "cage" in df else 0, len(df))
        candidates.append(
            {
                "id": "environmental_interaction",
                "topic": "Environmental interaction",
                "draft_research_question": "Do low dissolved oxygen and salinity extremes add to temperature-related mortality, and is the combination of high temperature and low DO worse than either alone?",
                "variables": env_roles + ["temperature_c", mort_col],
                "method": "Spearman correlations of DO and salinity with mortality; mean mortality in temperature (upper quartile) x DO (lower quartile) cells, per species.",
                "evidence": evidence,
                "data_sufficiency": suff,
                "sufficiency_reasons": reasons,
                "likely_confounders": ["temperature and DO are physically linked", "biomass load (oxygen demand)", "algal blooms / weather events"],
                "next_step": "Fit a model with temperature, DO and their interaction (cage random effect); quarter-based cells are exploratory cut-points.",
                "evidence_type": "observational association",
            }
        )
    else:
        skipped.append({"id": "environmental_interaction", "needs_roles": ["mortality_count", "do_mg_l and/or salinity_ppt"]})

    # 7. Stocking density and growth ----------------------------------------
    if len(intervals) and "mean_stocking_density_kg_m3" in intervals:
        evidence = {str(sp): _spearman(g["mean_stocking_density_kg_m3"], g["sgr"]) for sp, g in by_species(intervals)}
        suff, reasons = _sufficiency(int(intervals["cage"].nunique()), len(intervals), min_obs=20)
        candidates.append(
            {
                "id": "density_growth",
                "topic": "Production management",
                "draft_research_question": "Is higher stocking density associated with lower specific growth rate, and at what density does growth begin to decline?",
                "variables": ["mean_stocking_density_kg_m3", "sgr", "species"],
                "method": "Spearman correlation of interval mean density with interval SGR, per species.",
                "evidence": evidence,
                "data_sufficiency": suff,
                "sufficiency_reasons": reasons,
                "likely_confounders": ["density rises as fish grow, and SGR falls with size", "temperature and season"],
                "next_step": "Separate density from fish size (covariate or matched comparison) or run a controlled density trial.",
                "evidence_type": "observational association",
            }
        )
    else:
        skipped.append({"id": "density_growth", "needs_roles": ["date", "cage", "abw_g", "stocking_density_kg_m3"]})

    return _py(
        {
            "species": species_list,
            "cleaning_log": log,
            "n_sampling_intervals": int(len(intervals)),
            "candidates": candidates,
            "skipped_candidates": skipped,
            "caveat": OBSERVATIONAL_CAVEAT,
        }
    )
