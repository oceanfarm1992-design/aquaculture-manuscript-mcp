# Aquaculture Research Intelligence System — design

An extension of this MCP server that turns a farm's own operational records,
environmental observations and the scientific literature into research
opportunities, study designs, research proposals and, later, publications.

**Mission.** Make existing farm data a source of scientific research, not
only of day-to-day management, without ever letting the system invent a
result, reference, sample size or conclusion.

## 1. Decisions this design is built on

| Decision | Choice | Effect on the design |
|---|---|---|
| Research scope | All aquaculture research | Agents and tools are species- and system-neutral. Marine/offshore cage culture (e.g. Sobaity, Shaam, Gabit) is the first worked domain. |
| Data sources | Any records the user provides, plus literature | Excel/CSV/exported databases are read through a confirmed `column_roles` mapping rather than a fixed schema. Literature comes through CrossRef. |
| Autonomy | Agents work on their own between gates; the user approves key decisions | Four approval gates (G1–G4). Agents may *propose* a gate decision; only the user approves it. |

## 2. Architecture

One Research Director and eleven specialists, connected hub-and-spoke:
specialists never call each other. Every handoff goes Director → specialist
→ Director, so the Director reviews each output before it travels on. This is
deliberate: twelve agents talking freely would be expensive, hard to debug
and prone to contradicting each other.

```
                        User (requests, data, approvals at G1–G4)
                                         │
                                 Research Director
     ┌──────────────┬──────────────┬─────┴────────┬──────────────┬──────────────┐
  Phase 1         Phase 1        Phase 1        Phase 2        Phase 3        Phase 4
 Data Intel.   Opportunity    Literature    Question/Hyp.   Feasibility   Publication
               Discovery       Review        Statistics      Proposal      (uses the 6
                                             Exp. Design     Ethics &       manuscript
                                             Methodology     Validation     agents)
     └──────────────┴───────── tools in this server ───────────┴──────────────┘
   farm_data · statistics · power · calculators · water_quality · CrossRef · docx export
                                         │
                Research project folder (memory, data, references, gates, audit)
```

Agents are MCP **prompts**: the model already running in the user's MCP client
(Claude Desktop, Claude Code) does the reasoning and writing. All computation
goes through MCP **tools** (pandas, scipy, statsmodels, CrossRef), so numbers
never come from the model.

### Standard output block

Every specialist ends with the same block, which is what the Director reviews:

```
### Agent output
- Agent / Task received / Inputs used / Outputs
- Key claims and their sources   (claim -> dataset, analysis file, DOI, calculation, user)
- Assumptions made
- Limitations and open questions
- Recommended next agent
- Gate status                    (none / proposes G1–G4 decision)
```

## 3. The twelve agents

| # | Prompt name | Phase | Responsible for | Backed by tools | Status |
|---|---|---|---|---|---|
| 01 | `research-director` | 0 | Workflow choice, routing, review, gates, final package | workspace tools, `import_pasted_table` + all agents | Built |
| 02 | `data-intelligence-agent` | 1 | Profiling, column-role confirmation, quality checks, approved corrections, SGR/FCR/survival, analysis tables | `profile_dataset`, `suggest_column_roles`, `check_data_quality`, `apply_data_corrections`, `compute_performance_metrics`, `export_analysis_table` | Built + tested |
| 03 | `opportunity-discovery-agent` | 1 | Candidate research topics from validated data | `discover_research_opportunities`, `make_figure` | Built + tested |
| 04 | `literature-review-agent` | 1 | Evidence, conflicts, gaps; verified reference library | `search_citations`, `resolve_doi_metadata`, `add_verified_reference` | Built + tested |
| 05 | `question-hypothesis-agent` | 2 | Questions, objectives, hypotheses, conceptual framework → G1 | workspace tools | Prompt (reasoning task) |
| 06 | `statistical-analysis-agent` | 2 | Models for repeated cage data, effect size, power, analysis plan | `fit_gee_model`, `fit_mixed_model`, `estimate_effect_size_from_records`, `calculate_sample_size`, `export_analysis_plan_xlsx` + statistics tools | Built + tested |
| 07 | `experimental-design-agent` | 2 | Treatments, units, replication, randomisation, sampling → Research Design Document, G2 | `export_research_design_document`, power tools | Built + tested |
| 08 | `methodology-agent` | 2 | Field/lab protocols, data-collection templates, QC | water-quality tools | Prompt (reasoning task) |
| 09 | `feasibility-agent` | 3 | Fish, cages, feed, density, costs, risks | `plan_trial_resources`, performance metrics | Built + tested |
| 10 | `proposal-writing-agent` | 3 | 22-part proposal after G2, Gantt chart, budget | `export_research_proposal`, reference library | Built + tested |
| 11 | `ethics-validation-agent` | 3 | Welfare, permits, biosecurity, validity, unsupported claims, before G3/G4 | `check_citation_integrity`, audit trail | Prompt (reasoning task) |
| 12 | `publication-agent` | 4 | Manuscripts, figures, slides via the six manuscript agents → G4 | manuscript agents, `make_figure`, `export_presentation_pptx`, docx export | Built + tested |

"Prompt (reasoning task)" means the work is judgement and writing (choosing
hypotheses, drafting protocols, reviewing ethics), done by the model under the
agent's instructions and checked against the audit trail; there is no
calculation for a dedicated tool to do.

## 4. Workflows and approval gates

**Workflow A — question first** (e.g. effect of high water temperature on Sobaity, Shaam and Gabit):
idea → literature review + opportunity scan → questions and hypotheses **[G1]**
→ experimental design + statistical plan → feasibility + ethics → Research
Design Document **[G2]** → full proposal **[G3]**.

**Workflow B — data first** (e.g. three years of growth, mortality, feeding and temperature records):
data quality and validation → exploratory analysis → pattern discovery →
literature comparison → research gap → questions and hypotheses **[G1]** →
statistical feasibility → design → Research Design Document **[G2]** →
data-driven proposal with limitations stated **[G3]**.

**Execution and publication**: new data → statistical analysis → publication
agent (results, drafting, abstract, copyedit, integrity agents) → ethics and
validation → **[G4]**.

| Gate | Decision the user makes |
|---|---|
| G1_research_question | Which research question(s) to pursue |
| G2_study_design | Final design, sample size and statistical plan (the Research Design Document) |
| G3_proposal | Proposal ready for scientific/management review |
| G4_publication | Results and manuscript cleared for submission or release |

`record_gate_decision` refuses `approved`/`rejected` without a quoted user
confirmation. The Research Design Document must pass G2 before a full proposal
is written, because a well-written proposal can still describe a weak experiment.

## 5. Observational data: what the system will and won't claim

Farm records reveal associations, trends and possible explanations; they do not
prove cause. Accordingly, `discover_research_opportunities`:

- labels every candidate `evidence_type: "observational association"`;
- reports **data sufficiency** using the cage (not the fish or the daily row) as
  the independent unit, and says why when it is limited;
- lists **likely confounders** for each candidate (e.g. DO falls as temperature
  rises; SGR falls with fish size regardless of temperature);
- flags post-hoc choices (e.g. the "strongest" of eight time lags) as
  hypotheses to confirm;
- labels a temperature threshold as a default (90th percentile) unless the user
  or a verified reference supplied it;
- recommends a controlled follow-up study when the question is causal.

Candidate scans implemented: thermal tolerance (temperature vs mortality, lags
0–7 d, hot vs other days), species survival comparison, temperature vs SGR,
temperature vs FCR, seasonal variation, temperature × DO/salinity interaction,
stocking density vs growth. A scan whose required columns are missing is listed
under `skipped_candidates` with the columns it needs.

## 6. System capabilities

| Capability | Implementation |
|---|---|
| Research memory | Project folder: `project.json`, `decisions.json` (gate history), saved analyses |
| Reference library | `references/library.json`, CrossRef-verified entries only (`add_verified_reference`) |
| Data repository | `data/raw` (originals copied unchanged, SHA-256 in `manifest.json`) and `data/processed`, kept apart |
| Scientific audit | `audit.jsonl` via `log_claim`; a claim cannot be logged without a source reference |
| Document generator | Research Design Document and proposal (`.docx`, Gantt and budget), manuscript (`.docx`), analysis plan (`.xlsx`), figures (300-dpi PNG), slides (`.pptx`). PDF: save the Word file as PDF |
| Data corrections | `apply_data_corrections`: by spreadsheet row number, with a reason per change and the user's quoted approval; writes a corrected copy to `data/processed` and a correction log, never edits the raw file |
| Pasted data | `import_pasted_table`: CSV text pasted into chat becomes a registered raw dataset (for clients where attachments have no file path) |

One project folder per study, plain files, so it can live in git.

## 6a. Models for repeated cage data

Daily or monthly rows from the same cage are not independent, so Phase 2 uses:

- `fit_gee_model`: generalized estimating equations, robust SEs (bias-reduced
  below 40 cages), working correlation AR(1) over `day_index`, exchangeable or
  independence. For daily deaths: Poisson family with offset `log_fish_count`;
  coefficients come with rate ratios. Pearson dispersion is reported.
- `fit_mixed_model`: linear mixed model, random intercept per cage, for
  interval SGR/FCR or cycle outcomes; reports the ICC and convergence.
- `estimate_effect_size_from_records`: d = minimum important difference /
  between-cage SD, so a trial's sample size comes from the farm's own variation.

Both model tools copy column names to internal names before building the
formula, and attach caveats (few cages, overdispersion, non-convergence) to
their output.

## 7. Integrity rules (every agent)

1. Never invent experimental results, data values, references, DOIs, sample
   sizes, effect sizes, costs or statistical conclusions.
2. Observational data → associations, not causes.
3. The cage/tank is the experimental unit.
4. Computation goes through tools; agents interpret.
5. Stop at gates; only the user approves.
6. Stay in role; ethics approval, permits, biosecurity sign-off, budgets and
   physical sampling belong to people.
7. Save outputs and log claims in the project folder.

Tool-level enforcement: `calculate_sample_size` requires `effect_size_source`;
`add_verified_reference` refuses DOIs that don't resolve; `log_claim` refuses
claims without a source; `record_gate_decision` refuses approvals without a
quoted user decision; Tukey letters are never auto-assigned.

## 8. Roadmap

| Phase | Agents | Status |
|---|---|---|
| 1 Research intelligence | Data Intelligence, Opportunity Discovery, Literature Review | Built and tested |
| 2 Research design | Question/Hypothesis, Statistics, Experimental Design, Methodology | Built and tested (GEE, mixed models, effect size, power, design document, analysis plan) |
| 3 Proposal | Feasibility, Proposal Writing, Ethics & Validation | Built and tested (resource planner, 22-part proposal with Gantt and budget) |
| 4 Publication | Publication + Director | Built and tested (figures, slides, manuscript agents) |

The whole workflow runs end to end on synthetic records in
[examples/cage_farm_workflow](../examples/cage_farm_workflow/README.md).

Remaining work, in order of value:
1. Run on real farm records; tune plausibility ranges and column-name heuristics per site.
2. Time-to-event (survival) models and negative-binomial count models, if the
   real data show strong overdispersion.
3. Shared storage (PostgreSQL/Supabase) and a vector index over papers, once
   several people work on the same projects. The plain-file project folder
   covers single-user work.
4. R integration for analyses with no Python equivalent.
