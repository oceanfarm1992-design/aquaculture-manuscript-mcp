# Full workflow demo: cage-farm records → research proposal (Workflow B)

**The records here are synthetic.** They imitate three years of daily offshore
cage data (Sobaity, Shaam and Gabit, three cages each, harvested and restocked
every March). Nothing here describes a real farm. User decisions at the
approval gates are **simulated** and recorded as `DEMO: simulated user decision`.
In real use the Research Director stops and waits for you at each gate.

```bash
python 01_generate_synthetic_farm_records.py   # synthetic Excel records with planted errors
python 02_run_phase1.py                        # Phase 1: quality, metrics, opportunities, literature (needs internet)
python 03_run_phases2_3.py                     # Phases 2–3: corrections, models, design, proposal
```

## What each step produced

| Step | Tool(s) | Result on this data |
|---|---|---|
| Quality check | `check_data_quality` | All planted errors found, each with its spreadsheet row number |
| Corrections | `apply_data_corrections` | 7 corrections applied to a copy in `data/processed`; 0 errors left; raw file unchanged |
| Opportunities | `discover_research_opportunities` | Thermal mortality ranked first; see [phase1_report.md](phase1_report.md) |
| G1 | `record_gate_decision` | Thermal-tolerance question (simulated approval) |
| Mortality model | `export_analysis_table` (daily, 2-day lag) → `fit_gee_model` (Poisson, log fish-count offset, AR(1)) | Mortality rate per +1 °C: Gabit ×1.13, Shaam ×1.28, Sobaity ×1.52. Caveats attached automatically: 9 cages (p-values approximate) and overdispersion |
| Growth model | `fit_mixed_model` (cage random intercept, temperature + temperature², fish size) | SGR peaks near 27 °C |
| Effect size | `estimate_effect_size_from_records` | Between-cage SD of Sobaity cycle survival 4.8 points; 10-point difference → d = 2.07 (only 2 df, flagged) |
| Sample size | `calculate_sample_size` | 5 cages per treatment (power 0.82) |
| Resources | `plan_trial_resources` | 10 cages, 126,000 fingerlings, ~57,700 kg feed (FCR and survival from the farm's own records) |
| Documents | `export_analysis_plan_xlsx`, `export_research_design_document`, `export_research_proposal`, `make_figure`, `export_presentation_pptx` | See [outputs/](outputs/) |

The proposal's budget is deliberately **incomplete**: no unit costs were
supplied, so every line says "unit cost needed" and the total is labelled
INCOMPLETE rather than estimated.

## Outputs

- [outputs/research_design_document.docx](outputs/research_design_document.docx) — 14 sections plus the gate decision record (for G2)
- [outputs/research_proposal.docx](outputs/research_proposal.docx) — 22-part proposal with Gantt chart and budget table
- [outputs/statistical_analysis_plan.xlsx](outputs/statistical_analysis_plan.xlsx)
- [outputs/summary_slides.pptx](outputs/summary_slides.pptx)
- [outputs/figures/](outputs/figures/) — temperature and mortality over time, SGR vs temperature, survival per cage

## Bugs this demo caught (fixed, with regression tests)

- **Restocking:** survival went negative and FCR reached 10¹³ because metrics
  ran across the annual harvest and restock. Restocking now starts a new production cycle.
- **Near-zero growth:** winter intervals gave absurd FCRs. Interval FCR is now
  undefined below 0.5% gain; cycle FCR is total feed ÷ total gain.
- **Pseudo-replication in a figure:** survival bars first used 6 cage-cycles as
  n; they now use the 3 cage means (the experimental unit).
- **CrossRef markup:** a reference title arrived with `<i>` tags; titles are now cleaned.
