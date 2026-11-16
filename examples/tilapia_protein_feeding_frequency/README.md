# Worked example: full manuscript from synthetic data

**All data in this folder are synthetic.** No fish were reared. The example
shows the full path from tank-level data to a submission-formatted `.docx`
using only this package's own tools. Do not cite its results.

Study simulated: juvenile Nile tilapia, 3 dietary protein levels (25/30/35 %
CP) x 2 feeding frequencies (2 or 3 meals/day), 3 tanks per treatment, 56 days.
Formatted for Elsevier *Aquaculture* (`elsevier_aquaculture` profile: 250-word
abstract, 5-7 keywords, AI-use declaration).

| Step | Script | Output | Package tools used |
|---|---|---|---|
| 1 | `01_generate_synthetic_data.py` | `synthetic_tank_data.csv` | none (seeded numpy) |
| 2 | `02_analyze.py` | `results.json` | `calculate_sgr`, `calculate_biomass_corrected_fcr`, `calculate_survival_rate`, `calculate_unionized_ammonia`, `check_water_parameter`, `descriptive_stats`, `check_normality`, `check_variance_homogeneity`, `analyze_two_way_anova`, `analyze_posthoc_tukey`, `analyze_kruskal_wallis`, `analyze_anova`, `calculate_pearson_correlation` |
| 3 | `03_verify_references.py` | `verified_references.json` | `resolve_doi_metadata`, `search_citations` (network) |
| 4 | `04_build_manuscript.py` | `example_manuscript_tilapia.docx` | `calculate_stocking_density`, `draft_ai_disclosure`, `export_manuscript_docx` |

Every number in the text is formatted from `results.json`, so prose and
statistics cannot drift apart. Every reference resolved in CrossRef. Tukey
significance letters were assigned by hand (the package deliberately doesn't
auto-assign them), and `04_build_manuscript.py` fails if they contradict the
pairwise matrix.

Run from this folder with the repo's venv:

```bash
python 01_generate_synthetic_data.py
python 02_analyze.py
python 03_verify_references.py
python 04_build_manuscript.py
```
