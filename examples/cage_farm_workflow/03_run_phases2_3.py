"""Phases 2-3 on the synthetic cage-farm project created by 02_run_phase1.py:
corrections -> analysis tables -> models -> figures -> effect size and sample
size -> resource plan -> analysis plan -> Research Design Document -> proposal
-> summary slides.

Every number in the documents comes from a tool result in this script.
User decisions at the gates are SIMULATED for the demo and labelled as such
in the decision record ("DEMO: simulated user decision"). In real use the
Research Director stops and waits for you at each gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aquaculture_manuscript_mcp.tools import farm_data, figures, models, planning, power
from aquaculture_manuscript_mcp.tools import research_documents as rd
from aquaculture_manuscript_mcp.tools import research_workspace as ws

HERE = Path(__file__).parent
PROJECT = HERE / "project_heat_stress"
RAW = "synthetic_cage_farm_records.xlsx"
DEMO = "DEMO: simulated user decision — "
ROLES = json.loads((HERE / "column_roles.json").read_text(encoding="utf-8"))

proc = PROJECT / "data" / "processed"
docs = PROJECT / "documents"
figs = docs / "figures"


def p(x: float) -> str:
    return "P < 0.001" if x < 0.001 else f"P = {x:.3f}"


def main() -> None:
    if not (PROJECT / "project.json").exists():
        raise SystemExit("run 02_run_phase1.py first")
    raw_path = str(PROJECT / "data" / "raw" / RAW)

    # ---- G1: research question (simulated approval) -------------------------
    ws.record_gate_decision(str(PROJECT), "G1_research_question", "approved",
                            "Thermal tolerance: mortality above a temperature threshold across Sobaity, Shaam and Gabit",
                            "Strongest, most consistent signal; direct production relevance",
                            DEMO + "'Go with the thermal tolerance question.'")

    # ---- Data corrections from the quality report's row numbers -------------
    q = farm_data.check_data_quality(raw_path, ROLES)
    by = {}
    for issue in q["issues"]:
        by.setdefault(issue["check"], []).append(issue)
    corrections = []
    for issue in by.get("implausible_value", []):
        for ex in issue["examples"]:
            col = ROLES["temperature_c"] if "temperature_c" in ex else ROLES["feed_kg"]
            corrections.append({"row": ex["row"], "column": col, "new_value": None, "reason": issue["detail"]})
    for ex in by["exact_duplicate_rows"][0]["examples"]:
        corrections.append({"row": ex["row"], "action": "drop", "reason": "exact duplicate (double entry)"})
    conflict_rows = sorted(ex["row"] for ex in by["conflicting_cage_date_rows"][0]["examples"])
    corrections.append({"row": conflict_rows[-1], "action": "drop", "reason": "conflicting re-entry of the same cage-day; first entry kept after checking the paper log"})
    for issue in by.get("abw_possible_unit_error", []):
        for ex in issue["examples"]:
            corrections.append({"row": ex["row"], "column": ROLES["abw_g"], "new_value": round(ex["abw_g"] * 1000, 1), "reason": "ABW entered in kg; converted to g"})
    fix = ws.apply_data_corrections(str(PROJECT), RAW, corrections, DEMO + "'Apply all the listed corrections.'")
    clean = fix["corrected_file"]
    q2 = farm_data.check_data_quality(clean, ROLES)

    # ---- Analysis tables and models -------------------------------------------
    daily = str(proc / "daily.csv")
    interval = str(proc / "interval.csv")
    cycle = str(proc / "cycle.csv")
    farm_data.export_analysis_table(clean, ROLES, daily, "daily", temperature_lags=[2])
    farm_data.export_analysis_table(clean, ROLES, interval, "interval")
    farm_data.export_analysis_table(clean, ROLES, cycle, "cycle")

    gee = models.fit_gee_model(daily, "mortality_count", ["temperature_c_lag2", "do_mg_l", "species"], "cage",
                               family="poisson", time="day_index", offset="log_fish_count",
                               interactions=[["temperature_c_lag2", "species"]])
    mixed = models.fit_mixed_model(interval, "sgr", ["mean_temperature_c", "abw_start_g", "species"], "cage",
                                   quadratic=["mean_temperature_c"])
    ws.save_analysis(str(PROJECT), "gee_mortality", gee)
    ws.save_analysis(str(PROJECT), "mixed_sgr", mixed)

    coef = {c["term"]: c for c in gee["coefficients"]}
    base = coef["temperature_c_lag2"]
    rr = {"Gabit": base["rate_ratio"]}
    for sp in ("Shaam", "Sobaity"):
        rr[sp] = base["rate_ratio"] * coef[f"temperature_c_lag2:C(species)[T.{sp}]"]["rate_ratio"]
    for sp, v in rr.items():
        ws.log_claim(str(PROJECT), f"{sp}: mortality rate x{v:.2f} per +1 °C (2-day lag)", "analysis", "analysis/*_gee_mortality.json")

    # ---- Figures ------------------------------------------------------------
    f1 = figures.make_figure(daily, "line", "date", "temperature_c", str(figs / "fig1_temperature.png"), group="species",
                             resample="W", ylabel="Water temperature (°C), weekly mean", xlabel="")
    f2 = figures.make_figure(daily, "line", "date", "mortality_rate_pct", str(figs / "fig2_mortality.png"), group="species",
                             resample="W", ylabel="Daily mortality (% of stock), weekly mean", xlabel="")
    f3 = figures.make_figure(interval, "scatter", "mean_temperature_c", "sgr", str(figs / "fig3_sgr_temperature.png"),
                             group="species", xlabel="Mean temperature over interval (°C)", ylabel="SGR (% day⁻¹)")
    cyc = pd.read_csv(cycle)
    complete = cyc[cyc["complete"]]
    # One row per cage (the experimental unit): mean over its complete cycles.
    per_cage = complete.groupby(["cage", "species"], as_index=False)["survival_pct"].mean()
    per_cage.to_csv(proc / "cage_survival_complete_cycles.csv", index=False)
    f4 = figures.make_figure(str(proc / "cage_survival_complete_cycles.csv"), "mean_bar", "species", "survival_pct",
                             str(figs / "fig4_survival.png"), ylabel="Survival per production cycle (%), cage means", xlabel="")

    # ---- Effect size and sample size for the follow-up trial ----------------
    sob = complete[complete["species"] == "Sobaity"]
    sob_cage = str(proc / "sobaity_complete_cycles.csv")
    sob.to_csv(sob_cage, index=False)
    es = models.estimate_effect_size_from_records(
        sob_cage, "survival_pct", "cage", 10.0,
        "a 10-percentage-point change in cycle survival is the smallest change farm management would act on",
    )
    n = power.calculate_sample_size("two_sample_t", es["cohens_d"], es["effect_size_source"])
    units = max(n["units_per_group"], 3)
    achieved = power.calculate_achieved_power("two_sample_t", es["cohens_d"], es["effect_size_source"], units)

    # ---- Resource plan --------------------------------------------------------
    sob_fcr = float(sob["fcr"].mean())
    sob_surv = float(sob["survival_pct"].mean())
    plan = planning.plan_trial_resources(
        treatments=2, units_per_treatment=units, fish_per_unit=12000, initial_weight_g=35, expected_final_weight_g=250,
        duration_days=150, expected_fcr=round(sob_fcr, 2), expected_fcr_source="mean cycle FCR of Sobaity cages, synthetic farm records 2022–2024",
        expected_survival_pct=round(sob_surv, 1), expected_survival_source="mean complete-cycle survival of Sobaity cages, synthetic farm records",
        fish_sampled_per_unit_per_event=30, sampling_events=6, spare_fish_pct=5,
    )

    # ---- Analysis plan ------------------------------------------------------
    plan_rows = [
        {"hypothesis_id": "H1", "hypothesis": "Reduced feeding on days ≥ 32 °C lowers cumulative summer mortality of Sobaity compared with normal feeding.",
         "response": "Cumulative mortality % per cage (June–October)", "predictors": "Feeding treatment (normal vs reduced)",
         "experimental_unit": "Cage", "model": "Welch two-sample t-test on cage-level cumulative mortality; GEE Poisson on daily deaths (offset log fish count, AR(1)) as secondary",
         "assumption_checks": "Shapiro–Wilk on cage values; Pearson dispersion for GEE", "alpha": 0.05,
         "multiple_comparisons": "Single primary test; secondary analyses reported as supporting", "missing_data": "Cage lost to non-thermal event: excluded and reported; no imputation",
         "notes": f"{units} cages per treatment ({n['units_per_group']} from power calculation)"},
        {"hypothesis_id": "H2", "hypothesis": "Reduced feeding during heat does not lower SGR over the full cycle by more than 5%.",
         "response": "SGR (% day⁻¹) per cage over the trial", "predictors": "Feeding treatment; initial ABW as covariate",
         "experimental_unit": "Cage", "model": "Linear model on cage SGR with initial ABW (ANCOVA)",
         "assumption_checks": "Residual normality, homogeneity of slopes", "alpha": 0.05,
         "multiple_comparisons": "Not applicable", "missing_data": "As H1", "notes": "Secondary outcome"},
    ]
    xlsx = rd.export_analysis_plan_xlsx(str(docs / "statistical_analysis_plan.xlsx"), "Statistical analysis plan — heat-period feeding trial (SYNTHETIC DEMO)", plan_rows)

    # ---- Research Design Document (G2) --------------------------------------
    b0, b1 = plan["biomass_kg"]["initial_per_unit"], plan["biomass_kg"]["final_per_unit"]
    design = {
        "research_question": "Does reducing the feeding ration on days when water temperature reaches 32 °C or more lower summer mortality of Sobaity in offshore cages, without an unacceptable loss of growth?",
        "hypotheses": "- H1 (primary): cages fed a reduced ration on days ≥ 32 °C have lower cumulative June–October mortality than cages fed normally.\n- H2 (secondary): SGR over the trial is not more than 5% lower with reduced heat-day feeding.",
        "study_type": (
            "Controlled on-farm trial. The farm records show an association between high temperature and mortality "
            f"(GEE rate ratio for Sobaity ×{rr['Sobaity']:.2f} per +1 °C, 2-day lag; {gee['n_groups']} cages), but observational "
            "data cannot show whether a management change would reduce losses. A randomised cage trial can."
        ),
        "experimental_unit": "The cage. Fish within a cage share water, feeding and handling, so cages, not fish, are the replicates.",
        "treatments_and_control": "- Control: normal feeding regime throughout.\n- Treatment: ration reduced on any day with morning water temperature ≥ 32 °C (reduction level to be set with the feed manager); normal feeding otherwise.",
        "replication_and_sample_size": (
            f"Effect size from the farm's own records: {es['effect_size_source']}. Cohen's d = {es['cohens_d']:.2f}. "
            f"Two-sample t-test, alpha 0.05, power 0.80 → {n['units_per_group']} cages per treatment; {units} cages per treatment are planned "
            f"(achieved power {achieved['power']:.2f}). Caveat: {es['caveats'][0]}"
        ),
        "randomisation_and_blocking": "Cages are paired by position in the farm (exposure to current) and one cage of each pair is randomly assigned to each treatment (coin toss, recorded). All cages stocked from one hatchery batch on the same day.",
        "sampling_schedule": f"Daily: temperature, DO, salinity (morning), feed given, mortalities removed and counted. Monthly: ABW from 30 fish per cage ({plan['fish']['removed_by_sampling']} fish removed in total over 6 samplings).",
        "response_variables": "- Cumulative mortality % per cage (primary).\n- SGR, biomass-corrected FCR and survival per cage (secondary), computed with the same formulas as the farm-data tools.\n- Mortality cause recorded where possible (gill, parasite, unknown).",
        "statistical_analysis_plan": "See statistical_analysis_plan.xlsx. Primary: Welch t-test on cage cumulative mortality. Secondary: Poisson GEE on daily deaths with log(fish count) offset and AR(1) correlation; ANCOVA on SGR with initial ABW.",
        "threats_to_validity": "- Cage position effects: controlled by pairing.\n- Different stocking batches: single batch, same day.\n- Disease outbreak unrelated to temperature: recorded and analysed as a sensitivity check.\n- Few cages: limited power for secondary outcomes; stated as a limitation.",
        "data_management": "Daily sheets with the column headings used by the farm-data tools; weekly entry and check_data_quality run; raw files registered in the project with checksum; corrections only through apply_data_corrections with approval.",
        "ethics_and_permits": "Humane endpoint: if daily mortality in any cage exceeds an agreed threshold, feeding returns to farm standard for that cage and the event is reported. Institutional animal-ethics approval and any authority permit to be obtained by the PI before stocking.",
        "resources_and_feasibility": (
            f"{plan['design']['total_units']} cages, {plan['fish']['to_procure']:,} fingerlings (incl. 5% spare), "
            f"expected feed {plan['feed_kg']['total']:,.0f} kg (FCR {sob_fcr:.2f} from records), "
            f"biomass per cage {b0:,.0f} → {b1:,.0f} kg over 150 days. Costs: unit costs needed."
        ),
    }
    dd = rd.export_research_design_document(str(docs / "research_design_document.docx"),
                                            "Heat-period feeding and Sobaity mortality (SYNTHETIC DEMO)", design,
                                            json.loads((PROJECT / "decisions.json").read_text()), "v1 for G2 review")
    ws.record_gate_decision(str(PROJECT), "G2_study_design", "approved", "Paired randomised cage trial, heat-day feeding",
                            "Design document complete; sample size from farm records", DEMO + "'Design approved, go ahead with the proposal.'")

    # ---- References (verified via CrossRef) ---------------------------------
    for doi, note in (("10.1002/naaq.10287", "Sobaity culture under high-temperature conditions"),
                      ("10.1046/j.1365-2109.2003.00800.x", "temperature and salinity tolerance of yellowfin sea bream")):
        try:
            ws.add_verified_reference(str(PROJECT), doi, note)
        except Exception as exc:
            print(f"reference {doi} not added: {exc}")
    refs = []
    for r in ws.list_references(str(PROJECT)):
        names = [a.split(",")[0] for a in r["authors"]]
        who = names[0] + (" et al." if len(names) > 2 else (f" and {names[1]}" if len(names) == 2 else ""))
        refs.append(f"{who}, {r['year']}. {r['title']}. {r['container_title']} {r.get('volume') or ''}, {r.get('page') or ''}. https://doi.org/{r['doi']}")

    # ---- Proposal (G3) --------------------------------------------------------
    sections = {
        "abstract": (
            "SYNTHETIC DEMONSTRATION. Three years of daily records from nine offshore cages show that mortality of Sobaity, "
            f"Shaam and Gabit rises with water temperature, most steeply in Sobaity (mortality rate ×{rr['Sobaity']:.2f} per +1 °C, "
            "two days later, in a repeated-measures model). These records cannot show whether management can reduce the losses. "
            f"We propose a paired, randomised trial in {plan['design']['total_units']} cages comparing normal feeding with reduced "
            "feeding on days of 32 °C or more, measuring cumulative summer mortality, growth and feed conversion."
        ),
        "introduction": "In the farm's records, summer water temperature in the offshore cages exceeds 32 °C each year. These daily records (temperature, oxygen, feed, mortality, fish weight) show where losses concentrate and can guide which management trials are worth running.",
        "problem_statement": "In the farm records, mortality peaks every summer and is highest in Sobaity. The records show an association with temperature, but not whether any management action reduces it.",
        "justification": "A change in feeding needs no new equipment (its cost is to be confirmed in the budget). If it lowers summer mortality without cutting growth, it is directly usable on the farm; if not, the farm avoids adopting an untested practice.",
        "literature_review": (
            "The literature search so far found two directly relevant works: Young and Shaikhi (2023) examined Sobaity culture in "
            "high-temperature conditions, and Jian et al. (2003) studied temperature and salinity tolerance in yellowfin sea bream. Their "
            "findings will be summarised once the full texts have been reviewed; this demonstration cites them only for the topics they cover."
        ),
        "research_gap": "No controlled cage-scale test of heat-day feeding for Sobaity was identified in the literature search so far.",
        "research_questions": "- Does reduced feeding on days ≥ 32 °C lower Sobaity summer mortality?\n- What does it cost in growth and feed conversion?",
        "objectives": "General: test a low-cost management response to summer heat stress in Sobaity.\n\n- Compare cumulative summer mortality between feeding treatments.\n- Compare SGR and FCR between treatments.\n- Record causes of mortality during heat events.",
        "hypotheses": design["hypotheses"],
        "conceptual_framework": "Observed in the farm records: dissolved oxygen falls as temperature rises, and mortality rises after hot days. Proposed mechanism, to be supported from the literature before G3: feeding adds oxygen demand from digestion, so reducing feed on hot days may lower total oxygen demand and stress, at some cost to growth. Confounders: cage position, stocking batch, disease.",
        "materials_methods": design["sampling_schedule"] + "\n\n" + design["response_variables"],
        "study_design": design["treatments_and_control"] + "\n\n" + design["randomisation_and_blocking"],
        "sampling_and_sample_size": design["replication_and_sample_size"],
        "data_collection": design["data_management"],
        "statistical_analysis_plan": design["statistical_analysis_plan"],
        "ethics": design["ethics_and_permits"],
        "expected_results": "If H1 holds, reduced heat-day feeding will show lower cumulative summer mortality than control. These are hypotheses, not results.",
        "limitations": "One farm, one season and one species; few cages limit power for secondary outcomes. The effect size comes from observational variation between cages and may differ in a controlled trial. All data in this demonstration are synthetic.",
        "work_plan": "The trial runs through one summer, with approvals and stocking beforehand and analysis afterwards.",
        "budget": "Quantities come from the resource plan. Unit costs must be supplied by the farm before the budget is complete.",
        "references_appendices": "Appendix A: statistical_analysis_plan.xlsx. Appendix B: research_design_document.docx.",
    }
    budget = [
        {"item": "Sobaity fingerlings", "quantity": plan["fish"]["to_procure"], "unit": "fish", "unit_cost": None},
        {"item": "Feed", "quantity": round(plan["feed_kg"]["total"]), "unit": "kg", "unit_cost": None},
        {"item": "Water-quality probe calibration", "quantity": 2, "unit": "service", "unit_cost": None},
        {"item": "Mortality diagnostics", "quantity": 20, "unit": "samples", "unit_cost": None},
    ]
    gantt = [
        {"task": "Ethics approval and permits", "start_month": 1, "end_month": 2},
        {"task": "Cage preparation and stocking", "start_month": 2, "end_month": 3},
        {"task": "Trial (heat season)", "start_month": 3, "end_month": 8},
        {"task": "Data checking and analysis", "start_month": 8, "end_month": 9},
        {"task": "Report and manuscript", "start_month": 9, "end_month": 10},
    ]
    prop = rd.export_research_proposal(str(docs / "research_proposal.docx"),
                                       "Heat-day feeding to reduce summer mortality of Sobaity in offshore cages (SYNTHETIC DEMO)",
                                       sections, ["Example PI", "Example co-investigator"], gantt, 10, budget, "KWD", refs)
    ws.record_gate_decision(str(PROJECT), "G3_proposal", "proposed", "Proposal v1", "Budget unit costs still needed")

    # ---- Slides -----------------------------------------------------------------
    deck = rd.export_presentation_pptx(str(docs / "summary_slides.pptx"), "Heat stress in offshore cages",
                                       "Synthetic demonstration of the research workflow", [
        {"title": "Temperature cycle", "bullets": ["Weekly mean water temperature per species", "Summer peaks above 32 °C"], "image_path": f1["file_path"]},
        {"title": "Mortality follows temperature", "bullets": [f"{sp}: ×{v:.2f} per +1 °C" for sp, v in rr.items()] + [f"GEE, {gee['n_groups']} cages: p-values approximate"], "image_path": f2["file_path"]},
        {"title": "Survival per production cycle", "bullets": ["Mean of complete cycles per cage", f"n = {min(f4['n_by_group'].values())} cages per species; bars show mean ± SD"], "image_path": f4["file_path"]},
        {"title": "Proposed trial", "bullets": [f"{units} cages per treatment, paired and randomised", "Normal vs reduced feeding on days ≥ 32 °C", "Primary outcome: summer mortality"]},
    ])

    summary = {
        "corrections_applied": len(fix["applied"]),
        "quality_errors_after_corrections": q2["issue_counts"]["error"],
        "gee_rate_ratio_per_degC": rr,
        "gee_caveats": gee["caveats"],
        "mixed_model_sgr": {f["term"]: (round(f["estimate"], 5), round(f["p_value"], 4)) for f in mixed["fixed_effects"]},
        "effect_size": {"d": es["cohens_d"], "sd": es["between_unit_sd"], "n_units": es["n_units"]},
        "sample_size": {"per_group": n["units_per_group"], "planned": units, "achieved_power": achieved["power"]},
        "resources": {"fish": plan["fish"]["to_procure"], "feed_kg": plan["feed_kg"]["total"]},
        "design_document_missing": dd["missing_sections"],
        "proposal_missing": prop["missing_sections"],
        "budget": prop["budget"],
        "analysis_plan_missing": xlsx["missing_fields"],
        "figures_n": {"fig4": f4["n_by_group"]},
        "references": len(refs),
        "slides": deck["slides"],
    }
    (HERE / "phases2_3_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    # Copy the deliverables out of the (git-ignored) project folder for review.
    import shutil

    out = HERE / "outputs"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(docs, out)
    print(json.dumps(summary, indent=2, default=str))
    print(json.dumps(ws.get_project_status(str(PROJECT))["gates"], indent=2))


if __name__ == "__main__":
    main()
