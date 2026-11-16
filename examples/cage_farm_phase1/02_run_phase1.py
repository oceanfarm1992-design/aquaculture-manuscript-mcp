"""Phase 1 (Workflow B, data first) run on the synthetic cage-farm records,
calling the same functions the MCP tools call. Produces a research project
folder and phase1_report.md.

The column-role mapping below is the one a user would confirm after
suggest_column_roles; the script asserts the suggestion matches it, so a
heuristic change can't silently alter the analysis.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from aquaculture_manuscript_mcp.tools import citations, farm_data
from aquaculture_manuscript_mcp.tools import research_workspace as ws

HERE = Path(__file__).parent
DATA = HERE / "synthetic_cage_farm_records.xlsx"
PROJECT = HERE / "project_heat_stress"

CONFIRMED_ROLES = {
    "date": "Date",
    "cage": "Cage No",
    "species": "Species",
    "temperature_c": "Water Temp (°C)",
    "salinity_ppt": "Salinity (ppt)",
    "do_mg_l": "DO (mg/L)",
    "feed_kg": "Feed Given (kg)",
    "mortality_count": "Mortality (pcs)",
    "abw_g": "ABW (g)",
    "fish_count": "Fish Count",
}

LITERATURE_QUERIES = [
    "Sparidentex hasta temperature growth",
    "sobaity seabream culture Arabian Gulf",
    "cage aquaculture high temperature mortality sea bream",
]


def fmt(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def main() -> None:
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    ws.create_research_project(str(PROJECT), "Thermal stress in offshore cage species", "Phase 1 demo on synthetic records", "B_data_first")
    reg = ws.register_dataset(str(PROJECT), str(DATA), "SYNTHETIC daily cage records 2022-2024, 3 species x 3 cages")

    profile = farm_data.profile_dataset(str(DATA))
    roles = farm_data.suggest_column_roles(str(DATA))
    assert roles["suggested_column_roles"] == CONFIRMED_ROLES, roles["suggested_column_roles"]

    quality = farm_data.check_data_quality(str(DATA), CONFIRMED_ROLES)
    metrics = farm_data.compute_performance_metrics(str(DATA), CONFIRMED_ROLES)
    opps = farm_data.discover_research_opportunities(str(DATA), CONFIRMED_ROLES, high_temperature_threshold_c=None)

    for name, result in (("profile", profile), ("data_quality", quality), ("performance_metrics", metrics), ("research_opportunities", opps)):
        ws.save_analysis(str(PROJECT), name, result, {"file": DATA.name, "sha256": reg["sha256"]})

    lit = {}
    for q in LITERATURE_QUERIES:
        try:
            lit[q] = citations.search_works(q, rows=5)
        except Exception as exc:  # network failure is reported, not hidden
            lit[q] = [{"error": str(exc)}]
    ws.save_analysis(str(PROJECT), "literature_search_candidates", {"queries": lit})

    ws.record_gate_decision(
        str(PROJECT),
        "G1_research_question",
        "proposed",
        "Thermal tolerance: mortality above a temperature threshold, compared across Sobaity, Shaam and Gabit",
        "Strongest and most consistent signal in the records; directly relevant to summer losses; needs a literature-sourced threshold and a cage-level model before any claim.",
    )

    # ---------------- report ----------------
    L = []
    L.append("# Phase 1 report — research intelligence (Workflow B)\n")
    L.append("> **SYNTHETIC DATA.** These records were generated for demonstration; nothing here describes a real farm.\n")
    L.append(f"Dataset: `{DATA.name}` — {profile['rows']} rows, {profile['columns']} columns, SHA-256 `{reg['sha256'][:16]}…`\n")
    L.append("## 1. Data quality (Data Intelligence Agent)\n")
    L.append(f"Issues: {quality['issue_counts']['error']} errors, {quality['issue_counts']['warning']} warnings, {quality['issue_counts']['info']} info.\n")
    L.append("| Severity | Check | Detail | Count |\n|---|---|---|---|")
    for i in quality["issues"]:
        if i["severity"] != "info" or i["check"] == "date_gaps":
            L.append(f"| {i['severity']} | {i['check']} | {i['detail']} | {i['count']} |")
    L.append(f"\nCleaning applied for analysis (reported, not hidden): `{json.dumps(metrics['cleaning_log'])}`\n")

    L.append("## 2. Performance by cage\n")
    L.append("Restocking (fish count rising) starts a new production cycle; values are means over each cage's complete cycles.\n")
    L.append("| Cage | Species | Cycles (complete) | Survival % per cycle | SGR %/d | FCR (total feed / total gain) |\n|---|---|---|---|---|---|")
    for c in metrics["per_cage"]:
        L.append(f"| {c['cage']} | {c.get('species')} | {c['cycles_in_record']} ({c['complete_cycles']}) | {fmt(c.get('mean_survival_pct'), 1)} | {fmt(c.get('mean_sgr'))} | {fmt(c.get('mean_fcr'), 2)} |")
    L.append("")

    L.append("## 3. Research opportunities (Opportunity Discovery Agent)\n")
    L.append(f"_{opps['caveat']}_\n")
    for c in opps["candidates"]:
        L.append(f"### {c['topic']} — `{c['id']}`")
        L.append(f"**Draft question:** {c['draft_research_question']}\n")
        L.append(f"Method: {c['method']}  ")
        L.append(f"Data sufficiency: **{c['data_sufficiency']}** {('— ' + '; '.join(c['sufficiency_reasons'])) if c['sufficiency_reasons'] else ''}  ")
        if c["id"] == "thermal_mortality":
            L.append(f"Threshold: {c['high_temperature_threshold_c']:.1f} °C ({c['threshold_source']})\n")
            L.append("| Species | Cages | Mortality/day, hot days (% of stock) | Other days | Ratio | Strongest lag (d) | ρ at that lag |\n|---|---|---|---|---|---|---|")
            for sp, e in c["evidence"].items():
                h = e["hot_vs_other_days"] or {}
                lag = e["strongest_lag_days"]
                rho = e["lagged_correlation_temperature_vs_mortality"].get(str(lag), {}).get("spearman_rho") if lag is not None else None
                L.append(f"| {sp} | {e['n_cages']} | {fmt(h.get('mean_mortality_hot_days'))} | {fmt(h.get('mean_mortality_other_days'))} | {fmt(h.get('ratio'), 1)} | {lag} | {fmt(rho, 2)} |")
            L.append(f"\n{c['multiple_testing_note']}\n")
        elif c["id"] in ("temperature_growth", "temperature_fcr"):
            L.append("\n| Species | Intervals | Spearman ρ | Fitted peak (°C, descriptive) |\n|---|---|---|---|")
            for sp, e in c["evidence"].items():
                r = e["correlation"] or {}
                q = e["quadratic_fit"] or {}
                L.append(f"| {sp} | {e['n_intervals']} | {fmt(r.get('spearman_rho'), 2)} | {fmt(q.get('vertex_temperature_c'), 1)} |")
            L.append("")
        elif c["id"] == "species_survival":
            for sp, s in c["evidence"]["survival_by_species"].items():
                L.append(f"- {sp}: {s['cages']} cages, mean survival {s['mean']:.1f}%")
            t = c["evidence"]["test"]
            if t:
                L.append(f"- {t['test']}: H = {t['h_statistic']:.2f}, P = {t['p_value']:.3f}\n")
        elif c["id"] == "environmental_interaction":
            L.append("\n| Species | Hot + low DO | Hot only | Low DO only | Neither | Days hot + low DO |\n|---|---|---|---|---|---|")
            for sp, e in c["evidence"].items():
                m = e.get("combined_temperature_do_mean_mortality", {})
                L.append(f"| {sp} | {fmt(m.get('hot_and_low_do'))} | {fmt(m.get('hot_only'))} | {fmt(m.get('low_do_only'))} | {fmt(m.get('neither'))} | {m.get('n_days_hot_and_low_do')} |")
            L.append("")
        elif c["id"] == "seasonal_variation":
            for sp, e in c["evidence"].items():
                ms = e.get("mortality_by_season", {})
                L.append(f"- {sp}: mean daily mortality % by season " + ", ".join(f"{k} {v:.3f}" for k, v in ms.items()))
            L.append("")
        L.append(f"Likely confounders: {', '.join(c['likely_confounders'])}.  ")
        L.append(f"Next step: {c['next_step']}\n")
    if opps["skipped_candidates"]:
        L.append("Skipped (columns not in the data): " + ", ".join(f"`{s['id']}` needs {s['needs_roles']}" for s in opps["skipped_candidates"]) + "\n")

    L.append("## 4. Literature search candidates (Literature Review Agent)\n")
    L.append("CrossRef search hits only. None has been read or added to the reference library yet: a title is not evidence of a finding.\n")
    for q, hits in lit.items():
        L.append(f"**{q}**")
        for h in hits:
            if "error" in h:
                L.append(f"- search failed: {h['error']}")
            else:
                L.append(f"- {', '.join(a.split(',')[0] for a in h['authors'][:2]) or 'n.a.'} ({h['year']}). {h['title']}. *{h['container_title']}*. doi:{h['doi']}")
        L.append("")

    L.append("## 5. Gate G1 — proposed, awaiting your decision\n")
    L.append("Recommended: **thermal tolerance** (mortality above a temperature threshold, compared across species). Before G1 approval: replace the 90th-percentile default threshold with a literature-sourced value per species, and confirm the column mapping and the flagged data errors with the farm team.\n")
    (HERE / "phase1_report.md").write_text("\n".join(L), encoding="utf-8")
    print(json.dumps(ws.get_project_status(str(PROJECT)), indent=2, default=str))


if __name__ == "__main__":
    main()
