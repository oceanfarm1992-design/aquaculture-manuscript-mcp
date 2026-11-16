"""Assemble the worked-example manuscript and export it as .docx.

Every number in the text is formatted from results.json (02_analyze.py), so
the prose cannot drift from the computed statistics. Every reference is one
that resolved in CrossRef (03_verify_references.py).

THE DATA ARE SYNTHETIC. The title, abstract, and Methods say so explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

from aquaculture_manuscript_mcp import agents
from aquaculture_manuscript_mcp import journals
from aquaculture_manuscript_mcp.tools import calculators as calc
from aquaculture_manuscript_mcp.tools.docx_export import export_manuscript_docx

HERE = Path(__file__).parent
R = json.loads((HERE / "results.json").read_text())
REFS = {v["doi"].lower(): v for v in json.loads((HERE / "verified_references.json").read_text())["verified"]}
JOURNAL = "elsevier_aquaculture"


# ---------- formatting helpers ----------

def p(value: float) -> str:
    return "P < 0.001" if value < 0.001 else f"P = {value:.3f}"


def term(resp: str, name: str) -> dict:
    return R["responses"][resp]["two_way_anova"]["terms"][name]


def F(resp: str, name: str) -> str:
    t = term(resp, name)
    resid_df = int(term(resp, "Residual")["df"])
    return f"F({int(t['df'])},{resid_df}) = {t['f_statistic']:.2f}, {p(t['p_value'])}"


def main_mean(resp: str, factor: str, level: str, nd: int = 2) -> str:
    key = "cp_main_means" if factor == "cp" else "ff_main_means"
    s = R["responses"][resp][key][level]
    return f"{s['mean']:.{nd}f} ± {s['sd']:.{nd}f}"


def m(resp: str, factor: str, level: str, nd: int = 2) -> str:
    key = "cp_main_means" if factor == "cp" else "ff_main_means"
    return f"{R['responses'][resp][key][level]['mean']:.{nd}f}"


def tukey(resp: str, a: str, b: str) -> dict:
    for c in R["responses"][resp]["tukey_protein"]["pairwise_comparisons"]:
        if {c["group1"], c["group2"]} == {a, b}:
            return c
    raise KeyError((resp, a, b))


def cell(resp: str, cp: int, ff: int, nd: int) -> str:
    s = R["responses"][resp]["cell_stats"][f"CP{cp}_F{ff}"]
    return f"{s['mean']:.{nd}f} ± {s['sd']:.{nd}f}"


def wq(name: str, nd: int) -> str:
    s = R["water_quality"][name]
    return f"{s['mean']:.{nd}f} ± {s['sd']:.{nd}f}"


INIT = R["initial_weight"]
PROT, FF, INT = "protein", "feeding_frequency", "protein:feeding_frequency (interaction)"
FW_GAIN_F3 = (float(m("final_weight_g", "ff", "F3")) / float(m("final_weight_g", "ff", "F2")) - 1) * 100
CORR = R["sgr_vs_fcr"]
KW = R["responses"]["survival_pct"]["kruskal_wallis_cells"]

# Initial stocking density from the package calculator (200-L tanks).
_initial_biomass_kg = INIT["mean"] * 20 / 1000
DENSITY0 = calc.calculate_stocking_density(_initial_biomass_kg, volume_m3=0.2)["density_kg_per_m3"]
_final_biomass_kg = max(t["final_weight_g"] for t in R["per_tank"]) * 20 / 1000
DENSITY_MAX = calc.calculate_stocking_density(_final_biomass_kg, volume_m3=0.2)["density_kg_per_m3"]

# Significance letters for protein main effects, assigned BY HAND from the
# Tukey pairwise matrix in results.json (the package deliberately does not
# auto-generate letters). Checked: growth/FCR -> CP25 differs from CP30 and
# CP35, CP30 vs CP35 not different; PER -> all three pairs differ; survival ->
# no pair differs.
LETTERS = {
    "final_weight_g": {"CP25": "b", "CP30": "a", "CP35": "a"},
    "weight_gain_pct": {"CP25": "b", "CP30": "a", "CP35": "a"},
    "sgr": {"CP25": "b", "CP30": "a", "CP35": "a"},
    "fcr": {"CP25": "a", "CP30": "b", "CP35": "b"},
    "per": {"CP25": "a", "CP30": "b", "CP35": "c"},
    "survival_pct": {"CP25": "", "CP30": "", "CP35": ""},
}


def _check_letters() -> None:
    """Fail loudly if the hand-assigned letters contradict the Tukey matrix."""
    for resp, letters in LETTERS.items():
        for c in R["responses"][resp]["tukey_protein"]["pairwise_comparisons"]:
            share = bool(set(letters[c["group1"]]) & set(letters[c["group2"]])) or (
                letters[c["group1"]] == letters[c["group2"]] == ""
            )
            if share == c["significant_at_alpha_0.05"]:
                raise SystemExit(f"letter mismatch for {resp}: {c['group1']} vs {c['group2']}")


_check_letters()


# ---------- reference list (Elsevier Aquaculture-style author-date) ----------

def _journal_ref(doi: str) -> str:
    v = REFS[doi.lower()]
    authors = _format_author_list(v["authors"])
    vol = f" {v['volume']}," if v.get("volume") else ""
    pages = f" {v['page']}." if v.get("page") else ""
    return f"{authors}, {v['year']}. {v['title']}. {v['container_title']}{vol}{pages} https://doi.org/{v['doi']}"


def _format_author_list(raw: list[str]) -> str:
    out = []
    for a in raw:
        family, _, given = a.partition(", ")
        if not family:
            continue
        initials = "".join(f"{w[0]}." for w in given.replace("-", " ").replace(".", " ").split())
        out.append(f"{family}, {initials}" if initials else family)
    if len(out) > 10:
        return ", ".join(out[:10]) + ", et al."
    if len(out) == 1:
        return out[0]
    return ", ".join(out[:-1]) + ", " + out[-1]


REFERENCES = sorted(
    [
        # Corporate-author works: CrossRef confirms DOI, title, year and publisher but lists no personal authors.
        "FAO, 2024. The State of World Fisheries and Aquaculture 2024. Blue Transformation in action. FAO, Rome. https://doi.org/10.4060/cd0683en",
        "National Research Council, 2011. Nutrient Requirements of Fish and Shrimp. National Academies Press, Washington, DC. https://doi.org/10.17226/13039",
        _journal_ref("10.1139/f75-274"),
        _journal_ref("10.1016/0044-8486(88)90007-5"),
        _journal_ref("10.1016/j.aquaculture.2009.10.027"),
        _journal_ref("10.1016/j.aquaculture.2003.12.012"),
        _journal_ref("10.1371/journal.pbio.3000410"),
        _journal_ref("10.1038/s41592-019-0686-2"),
        _journal_ref("10.25080/majora-92bf1922-011"),
        _journal_ref("10.1080/10454438.2014.965572"),
    ],
    key=str.lower,
)


# ---------- text ----------

TITLE = (
    "[SYNTHETIC WORKED EXAMPLE — NOT REAL DATA] Effects of dietary protein level and "
    "feeding frequency on growth and feed utilisation of juvenile Nile tilapia "
    "(Oreochromis niloticus)"
)
AUTHORS = ["Example Author A", "Example Author B", "Example Author C (corresponding author)"]

ABSTRACT = (
    "This manuscript is a worked example generated by aquaculture-manuscript-mcp; all data are synthetic "
    "and no animals were used. It illustrates how a two-factor nutrition trial would be reported. "
    "Juvenile Nile tilapia (Oreochromis niloticus; initial weight "
    f"{INIT['mean']:.2f} ± {INIT['sd']:.2f} g) were assigned to a 3 × 2 factorial design combining three "
    "dietary crude protein levels (25, 30 and 35%) with two feeding frequencies (two or three meals per day), "
    "with three replicate tanks per treatment, for 56 days. Dietary protein affected final weight, weight gain, "
    "specific growth rate (SGR), feed conversion ratio (FCR) and protein efficiency ratio (PER) "
    f"({p(term('final_weight_g', PROT)['p_value'])} for each). Fish fed 30 or 35% protein grew faster than "
    f"those fed 25% (SGR {m('sgr','cp','CP30')} and {m('sgr','cp','CP35')} vs {m('sgr','cp','CP25')}% per day) "
    "and converted feed more efficiently, while growth and FCR did not differ between 30 and 35% protein. "
    f"PER declined progressively with increasing dietary protein. Three daily meals increased final weight by "
    f"{FW_GAIN_F3:.1f}% and improved FCR relative to two meals. No protein × feeding-frequency interaction was "
    "detected for any response, and survival was not affected by either factor. Within the conditions of this "
    "synthetic example, a 30% protein diet fed three times daily gave growth and feed conversion equivalent to "
    "the 35% diet with better protein efficiency."
)

KEYWORDS = [
    "Nile tilapia",
    "dietary protein",
    "feeding frequency",
    "feed conversion ratio",
    "protein efficiency ratio",
    "factorial design",
]

INTRODUCTION = f"""\
Aquaculture now supplies a large and growing share of the aquatic animal food consumed worldwide (FAO, 2024), and tilapias, led by Nile tilapia (Oreochromis niloticus), are among the most widely farmed finfish. Feed is usually the largest single operating cost in semi-intensive and intensive tilapia production, and protein is the most expensive macronutrient in that feed. Choosing a dietary protein level that supports good growth without supplying protein in excess of what the fish can use is therefore both an economic and an environmental decision, because surplus protein is deaminated and excreted as ammonia.

Dietary protein requirements of Nile tilapia have been studied for decades and are summarised in the National Research Council (2011) nutrient-requirement tables. Requirements are not a single value: Siddiqui et al. (1988) found that the protein level supporting best growth differed between fry and young fish, and Abdel-Tawwab et al. (2010) showed that dietary protein level interacted with initial body weight in determining growth, feed utilisation and physiological responses. A requirement estimated in one size class or rearing system cannot be transferred unchanged to another.

Feeding frequency is a second management variable that can change how efficiently a given diet is used. Riche et al. (2004) measured gastric evacuation and the return of appetite in Nile tilapia, providing a physiological basis for spacing meals. Because protein level and meal frequency are both set by the farmer and may act together, testing them in a crossed design allows their main effects and any interaction to be estimated in the same trial.

The present manuscript is a worked example. It reports a 3 × 2 factorial trial combining three dietary protein levels with two feeding frequencies in juvenile Nile tilapia, using a synthetic dataset so that every calculation and statistical step can be reproduced end to end. The aim was to test whether protein level and feeding frequency affect growth, feed conversion, protein efficiency and survival, and whether the two factors interact."""

METHODS = f"""\
Data provenance. All values reported in this manuscript are synthetic. They were generated by a seeded random model (examples/tilapia_protein_feeding_frequency/01_generate_synthetic_data.py, seed 20261116) whose cell means were chosen to resemble plausible tilapia growth data. No fish were reared, and no result here should be cited as empirical evidence. The Methods below describe the trial as it would be reported had it been carried out.

Ethics statement. In a real study, this section would name the institutional animal care and use committee that approved the protocol and give its approval number, and the study would be reported following the ARRIVE 2.0 guidelines (Percie du Sert et al., 2020). Because no animals were used in this synthetic example, no approval applies.

Experimental design and fish. A 3 × 2 factorial design was used, crossing three dietary crude protein (CP) levels (25, 30 and 35% of diet) with two feeding frequencies (two or three meals per day). Each of the six treatment combinations was assigned to three replicate tanks (18 tanks in total; the tank was the experimental unit). Juvenile Nile tilapia (initial mean weight {INIT['mean']:.2f} ± {INIT['sd']:.2f} g, range {INIT['min']:.2f}–{INIT['max']:.2f} g) were stocked at 20 fish per 200-L tank in a recirculating system, giving an initial stocking density of {DENSITY0:.2f} kg m−3. Initial weight did not differ among treatments (one-way ANOVA, F({R['initial_weight_anova']['df_between']},{R['initial_weight_anova']['df_within']}) = {R['initial_weight_anova']['f_statistic']:.2f}, {p(R['initial_weight_anova']['p_value'])}). The trial lasted 56 days.

Diets and feeding. Three isoenergetic diets were formulated to contain 25, 30 and 35% crude protein; the dry-matter content of all diets was taken as 92%. (A real manuscript would give the full ingredient formulation and proximate composition in a table here.) Fish were fed to apparent satiation at each meal, either at 09:00 and 16:00 h (two meals) or at 08:00, 12:00 and 16:00 h (three meals). Feed offered was recorded daily per tank. Dead fish were removed, counted and weighed daily.

Water quality. Temperature, dissolved oxygen (DO) and pH were recorded daily and total ammonia nitrogen (TAN) weekly in every tank. Un-ionised ammonia (NH3-N) was calculated from TAN, pH and temperature using the equilibrium equation of Emerson et al. (1975).

Calculations. All per-tank performance indices were computed with the calculator functions of aquaculture-manuscript-mcp:
Weight gain (%) = (final mean weight − initial mean weight) / initial mean weight × 100.
Specific growth rate (SGR, % day−1) = (ln final mean weight − ln initial mean weight) / 56 × 100.
Survival (%) = final fish count / initial fish count × 100.
Feed conversion ratio (FCR) was calculated on a dry-matter basis and corrected for the biomass of fish that died during the trial: FCR = (feed offered × 0.92) / ((final biomass + biomass of dead fish) − initial biomass), following the dry-matter FCR formulation in Yossa (2014). The biomass of dead fish was estimated as the number of mortalities multiplied by the mean of the tank's initial and final mean weights.
Protein efficiency ratio (PER) = biomass gain (as defined for FCR) / dry protein offered, where dry protein offered = feed offered × 0.92 × dietary CP fraction.

Statistical analysis. Each response was analysed by two-way ANOVA with dietary protein level, feeding frequency and their interaction as fixed factors (Type II sums of squares), with the tank as the experimental unit (n = 3 per treatment). Normality of the ANOVA residuals was checked with the Shapiro–Wilk test and homogeneity of variance across the six treatment cells with Levene's test. Where the protein main effect was significant, the three protein levels (pooled across feeding frequencies, n = 6 per level) were compared with Tukey's HSD test. Significance letters were assigned by hand from the full pairwise Tukey matrix. Survival percentages were additionally compared among the six treatment cells with the Kruskal–Wallis test. The association between SGR and FCR across tanks was assessed with Pearson's correlation. Effect sizes are reported as (non-partial) eta-squared. Analyses used SciPy (Virtanen et al., 2020) and statsmodels (Seabold and Perktold, 2010) through the statistics tools of aquaculture-manuscript-mcp. Significance was set at α = 0.05. Values are means ± standard deviation (SD)."""


def _assumptions_sentence() -> str:
    sw = [R["responses"][k]["normality_of_residuals"]["p_value"] for k in R["responses"]]
    lv = [R["responses"][k]["levene_across_cells"]["p_value"] for k in R["responses"]]
    return (
        "Residuals were consistent with normality for every response (Shapiro–Wilk, "
        f"P ≥ {min(sw):.3f}) and variances were homogeneous across treatment cells (Levene's test, "
        f"P ≥ {min(lv):.3f}), so no transformation was applied."
    )


T = lambda resp, a, b: tukey(resp, a, b)  # noqa: E731

RESULTS = f"""\
Water quality. Across tanks, mean temperature was {wq('temp', 1)} °C, DO {wq('do', 2)} mg L−1, pH {wq('ph', 2)} and TAN {wq('tan', 2)} mg L−1, giving a calculated un-ionised ammonia concentration of {wq('nh3_mg_l', 4)} mg NH3-N L−1. DO, pH and TAN were within the reference ranges for Nile tilapia used by the water-quality checker of aquaculture-manuscript-mcp. Mean temperature ({R['water_quality']['temp']['mean']:.2f} °C) lay marginally above the upper bound of the narrow 25–27 °C optimal range in that reference set, but well within the species' survival limits.

Statistical assumptions. {_assumptions_sentence()}

Growth. Dietary protein level had a significant effect on final weight ({F('final_weight_g', PROT)}; η² = {term('final_weight_g', PROT)['eta_squared']:.2f}), weight gain ({F('weight_gain_pct', PROT)}) and SGR ({F('sgr', PROT)}; η² = {term('sgr', PROT)['eta_squared']:.2f}) (Tables 2 and 3). Fish fed 25% CP reached a final weight of {main_mean('final_weight_g','cp','CP25')} g, compared with {main_mean('final_weight_g','cp','CP30')} g at 30% CP and {main_mean('final_weight_g','cp','CP35')} g at 35% CP. Tukey's test showed that the 25% CP group grew less than both the 30% (SGR difference {T('sgr','CP25','CP30')['mean_difference']:.2f}% day−1, {p(T('sgr','CP25','CP30')['p_adjusted'])}) and the 35% CP groups ({p(T('sgr','CP25','CP35')['p_adjusted'])}), whereas the 30% and 35% CP groups did not differ ({p(T('sgr','CP30','CP35')['p_adjusted'])}).

Feeding frequency also affected final weight ({F('final_weight_g', FF)}; η² = {term('final_weight_g', FF)['eta_squared']:.2f}), weight gain ({F('weight_gain_pct', FF)}) and SGR ({F('sgr', FF)}). Fish fed three meals per day reached {main_mean('final_weight_g','ff','F3')} g, {FW_GAIN_F3:.1f}% heavier than fish fed two meals ({main_mean('final_weight_g','ff','F2')} g). The protein × feeding-frequency interaction was not significant for any growth response ({F('final_weight_g', INT)} for final weight).

Feed utilisation. FCR was affected by dietary protein ({F('fcr', PROT)}; η² = {term('fcr', PROT)['eta_squared']:.2f}) and by feeding frequency ({F('fcr', FF)}), with no interaction ({F('fcr', INT)}). FCR was highest at 25% CP ({main_mean('fcr','cp','CP25')}) and lower at 30% ({main_mean('fcr','cp','CP30')}) and 35% CP ({main_mean('fcr','cp','CP35')}), which did not differ from each other ({p(T('fcr','CP30','CP35')['p_adjusted'])}). Three daily meals gave a lower FCR ({main_mean('fcr','ff','F3')}) than two ({main_mean('fcr','ff','F2')}). PER responded to protein level ({F('per', PROT)}; η² = {term('per', PROT)['eta_squared']:.2f}) and feeding frequency ({F('per', FF)}), again without interaction ({F('per', INT)}). Unlike growth and FCR, PER differed among all three protein levels, declining from {main_mean('per','cp','CP25')} at 25% CP to {main_mean('per','cp','CP30')} at 30% and {main_mean('per','cp','CP35')} at 35% CP (all pairwise {p(max(T('per',a,b)['p_adjusted'] for a, b in [('CP25','CP30'),('CP25','CP35'),('CP30','CP35')]))} or lower).

Across all 18 tanks, SGR and FCR were strongly negatively correlated (Pearson r = {CORR['r']:.2f}, n = {CORR['n']}, {p(CORR['p_value'])}).

Survival. Survival ranged from {min(t['survival_pct'] for t in R['per_tank']):.0f} to {max(t['survival_pct'] for t in R['per_tank']):.0f}% and was not affected by dietary protein ({F('survival_pct', PROT)}), feeding frequency ({F('survival_pct', FF)}) or their interaction ({F('survival_pct', INT)}). The Kruskal–Wallis test across the six treatment cells gave the same conclusion (H = {KW['h_statistic']:.2f}, {p(KW['p_value'])})."""

DISCUSSION = f"""\
In this synthetic dataset, raising dietary protein from 25 to 30% improved growth and feed conversion, but a further increase to 35% produced no detectable additional gain in final weight, SGR or FCR, while protein efficiency continued to fall. This pattern, a growth plateau accompanied by declining PER, is the response usually interpreted as the dietary protein supply exceeding the level the fish can deposit as tissue, with the surplus used as an energy source. In the size range simulated here, the data therefore point to roughly 30% CP as sufficient. This is consistent with the general finding that tilapia protein requirements fall as fish grow (Siddiqui et al., 1988; Abdel-Tawwab et al., 2010), but the example is not evidence for that finding and should not be cited as such.

Feeding three meals rather than two increased final weight by {FW_GAIN_F3:.1f}% and lowered FCR, with feeding frequency explaining a smaller share of the variance than protein level (η² = {term('final_weight_g', FF)['eta_squared']:.2f} vs {term('final_weight_g', PROT)['eta_squared']:.2f} for final weight). A plausible mechanism, which this design cannot test directly, is that smaller, more frequent meals better match gastric capacity and the return of appetite (Riche et al., 2004), reducing waste and improving digestive efficiency. No protein × feeding-frequency interaction was detected for any response, which suggests that the two decisions can be made largely independently within the ranges tested. However, at 35% CP the FCR was practically identical with two and three meals ({cell('fcr', 35, 2, 2)} vs {cell('fcr', 35, 3, 2)}), whereas a third meal lowered FCR at 25% and 30% CP. With three tanks per treatment, a smaller benefit of the extra meal at the highest protein level therefore cannot be ruled out.

The strong negative correlation between SGR and FCR (r = {CORR['r']:.2f}) indicates that tanks that grew faster also converted feed more efficiently. This is expected when feed is offered to satiation and maintenance costs are spread over a larger weight gain, and it is a useful consistency check on tank-level data.

Survival was high in every treatment and unaffected by either factor, so the growth differences cannot be attributed to differential mortality. The biomass-corrected FCR further prevents mortalities from inflating apparent feed conversion in the tanks that lost fish.

This example has limitations that a real study would need to address. With three tanks per treatment the design has limited power to detect small interactions, so a non-significant interaction should not be read as proof that none exists. Whole-body composition, nutrient retention, digestibility and economic return were not measured, and the 30% versus 35% comparison should be confirmed with a cost analysis, for example using the economic FCR calculator. Most importantly, the data are synthetic, so the biological interpretation above demonstrates how results would be discussed, not what tilapia actually do.

Conclusions. Within this synthetic worked example, juvenile Nile tilapia fed a 30% crude protein diet grew as well and converted feed as efficiently as those fed 35% protein, with higher protein efficiency. Three meals per day improved growth and FCR over two meals overall, with no statistically detectable interaction between the two factors."""

ABBREVIATIONS = "CP, crude protein; DO, dissolved oxygen; FCR, feed conversion ratio; PER, protein efficiency ratio; SGR, specific growth rate; TAN, total ammonia nitrogen."

DATA_AVAILABILITY = (
    "The synthetic dataset (synthetic_tank_data.csv), all computed statistics (results.json) and the scripts "
    "that generate them are included in examples/tilapia_protein_feeding_frequency/ of the "
    "aquaculture-manuscript-mcp repository."
)

CREDIT = (
    "In a real manuscript, each author's contribution would be listed here using the CRediT taxonomy. "
    "AI tools must not be listed as authors (Elsevier Aquaculture guide for authors)."
)

FUNDING_AND_COI = "Funding: none (synthetic example). Declaration of competing interest: none."


# ---------- tables ----------

ND ={"final_weight_g": 2, "weight_gain_pct": 1, "sgr": 2, "fcr": 2, "per": 2, "survival_pct": 1}
LABELS = {
    "final_weight_g": "Final weight (g)",
    "weight_gain_pct": "Weight gain (%)",
    "sgr": "SGR (% day−1)",
    "fcr": "FCR",
    "per": "PER",
    "survival_pct": "Survival (%)",
}

TABLE1 = {
    "caption": "Table 1. Water quality across all 18 tanks (mean ± SD, min–max). Synthetic data.",
    "headers": ["Parameter", "Mean ± SD", "Range"],
    "rows": [
        ["Temperature (°C)", wq("temp", 1), f"{R['water_quality']['temp']['min']:.1f}–{R['water_quality']['temp']['max']:.1f}"],
        ["Dissolved oxygen (mg L−1)", wq("do", 2), f"{R['water_quality']['do']['min']:.2f}–{R['water_quality']['do']['max']:.2f}"],
        ["pH", wq("ph", 2), f"{R['water_quality']['ph']['min']:.2f}–{R['water_quality']['ph']['max']:.2f}"],
        ["TAN (mg L−1)", wq("tan", 2), f"{R['water_quality']['tan']['min']:.2f}–{R['water_quality']['tan']['max']:.2f}"],
        ["NH3-N (mg L−1)", wq("nh3_mg_l", 4), f"{R['water_quality']['nh3_mg_l']['min']:.4f}–{R['water_quality']['nh3_mg_l']['max']:.4f}"],
    ],
}

_t2_rows = []
for resp in LABELS:
    nd = ND[resp]
    row = [LABELS[resp]]
    for cp in (25, 30, 35):
        for ff in (2, 3):
            row.append(cell(resp, cp, ff, nd))
    for cp in (25, 30, 35):
        row.append(f"{m(resp, 'cp', f'CP{cp}', nd)}{LETTERS[resp][f'CP{cp}']}")
    row += [m(resp, "ff", "F2", nd), m(resp, "ff", "F3", nd)]
    _t2_rows.append(row)

TABLE2 = {
    "caption": (
        "Table 2. Growth performance, feed utilisation and survival of juvenile Nile tilapia fed three dietary "
        "protein levels at two feeding frequencies for 56 days (treatment means ± SD, n = 3 tanks; main-effect "
        "means n = 6 for protein and n = 9 for feeding frequency). Protein main-effect means not sharing a "
        "superscript letter differ (Tukey's HSD, P < 0.05). Synthetic data."
    ),
    "headers": [
        "Response",
        "25% CP, 2 meals", "25% CP, 3 meals",
        "30% CP, 2 meals", "30% CP, 3 meals",
        "35% CP, 2 meals", "35% CP, 3 meals",
        "Mean 25% CP", "Mean 30% CP", "Mean 35% CP",
        "Mean 2 meals", "Mean 3 meals",
    ],
    "rows": _t2_rows,
}

_t3_rows = []
for resp in LABELS:
    row = [LABELS[resp]]
    for name in (PROT, FF, INT):
        t = term(resp, name)
        row.append(f"{t['f_statistic']:.2f} ({p(t['p_value'])}; η² = {t['eta_squared']:.2f})")
    _t3_rows.append(row)

TABLE3 = {
    "caption": (
        "Table 3. Two-way ANOVA (Type II SS) for each response: F statistic, P value and eta-squared. "
        "Degrees of freedom: protein 2, feeding frequency 1, interaction 2, residual 12. Synthetic data."
    ),
    "headers": ["Response", "Protein level", "Feeding frequency", "Protein × feeding frequency"],
    "rows": _t3_rows,
}


def main() -> None:
    rules = journals.get_journal(JOURNAL)
    n_abs = len(ABSTRACT.split())
    if n_abs > rules["abstract_max_words"]:
        raise SystemExit(f"abstract is {n_abs} words, over the {rules['abstract_max_words']}-word limit")
    lo, hi = (int(x) for x in rules["keyword_count"].split("-"))
    if not lo <= len(KEYWORDS) <= hi:
        raise SystemExit(f"{len(KEYWORDS)} keywords, journal wants {rules['keyword_count']}")

    disclosure = agents.ai_disclosure_statement(
        "Claude (Anthropic) via the aquaculture-manuscript-mcp server",
        "generate a synthetic example dataset, run the statistical analysis with scipy/statsmodels, "
        "and draft the text of this worked-example manuscript",
    )

    out = HERE / "example_manuscript_tilapia.docx"
    result = export_manuscript_docx(
        output_path=str(out),
        title=TITLE,
        abstract=ABSTRACT,
        keywords=KEYWORDS,
        authors=AUTHORS,
        sections=[
            {"heading": "Abbreviations", "body": ABBREVIATIONS},
            {"heading": "1. Introduction", "body": INTRODUCTION},
            {"heading": "2. Materials and methods", "body": METHODS},
            {"heading": "3. Results", "body": RESULTS},
            {"heading": "4. Discussion", "body": DISCUSSION},
            {"heading": "CRediT authorship contribution statement", "body": CREDIT},
            {"heading": "Funding and declaration of competing interest", "body": FUNDING_AND_COI},
            {"heading": "Data availability", "body": DATA_AVAILABILITY},
        ],
        tables=[TABLE1, TABLE2, TABLE3],
        references=REFERENCES,
        ai_disclosure=disclosure,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
