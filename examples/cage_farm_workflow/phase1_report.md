# Phase 1 report — research intelligence (Workflow B)

> **SYNTHETIC DATA.** These records were generated for demonstration; nothing here describes a real farm.

Dataset: `synthetic_cage_farm_records.xlsx` — 9858 rows, 10 columns, SHA-256 `78c2045cad4e979e…`

## 1. Data quality (Data Intelligence Agent)

Issues: 4 errors, 1 warnings, 11 info.

| Severity | Check | Detail | Count |
|---|---|---|---|
| error | conflicting_cage_date_rows | same cage and date recorded more than once with different values | 2 |
| error | implausible_value | temperature_c outside physically plausible range -2.0–40.0 | 1 |
| error | implausible_value | feed_kg outside physically plausible range 0.0–None | 1 |
| error | abw_possible_unit_error | cage H2: ABW fell >90% between samplings within one production cycle (kg entered instead of g?) | 1 |
| warning | exact_duplicate_rows | identical rows (likely double entry); the later copy is listed | 3 |
| info | date_gaps | cage G3: 10 day(s) without a record inside its date span | 10 |

Cleaning applied for analysis (reported, not hidden): `{"exact_duplicate_rows_dropped": 3, "implausible_values_set_to_missing": {"temperature_c": 1, "feed_kg": 1}, "rows_dropped_unparseable_date": 0, "duplicate_cage_date_rows_dropped_keep_first": 1, "production_cycles_per_cage": {"G1": 4, "G2": 4, "G3": 4, "H1": 4, "H2": 4, "H3": 4, "S1": 4, "S2": 4, "S3": 4}}`

## 2. Performance by cage

Restocking (fish count rising) starts a new production cycle; values are means over each cage's complete cycles.

| Cage | Species | Cycles (complete) | Survival % per cycle | SGR %/d | FCR (total feed / total gain) |
|---|---|---|---|---|---|
| G1 | Gabit | 4 (2) | 84.7 | 0.517 | 2.66 |
| G2 | Gabit | 4 (2) | 86.4 | 0.520 | 2.68 |
| G3 | Gabit | 4 (2) | 87.4 | 0.509 | 2.67 |
| H1 | Shaam | 4 (2) | 80.3 | 0.505 | 2.67 |
| H2 | Shaam | 4 (2) | 77.8 | 0.507 | 2.68 |
| H3 | Shaam | 4 (2) | 81.5 | 0.505 | 2.71 |
| S1 | Sobaity | 4 (2) | 72.8 | 0.515 | 2.61 |
| S2 | Sobaity | 4 (2) | 67.4 | 0.490 | 2.71 |
| S3 | Sobaity | 4 (2) | 63.2 | 0.491 | 2.75 |

## 3. Research opportunities (Opportunity Discovery Agent)

_Observational farm data: this is an association, not evidence of cause. Daily records from the same cage are autocorrelated, so p-values computed on daily rows overstate certainty. Treat as a candidate for a designed study, not a finding._

### Thermal tolerance — `thermal_mortality`
**Draft question:** Is daily mortality higher when water temperature reaches or exceeds 33.0 °C, and does the response differ between species and with a time lag?

Method: Spearman correlation of temperature (lagged 0–7 d, within cage) with mortality_rate_pct; Mann–Whitney comparison of mortality on days >= threshold vs other days, per species.  
Data sufficiency: **adequate_for_exploration**   
Threshold: 33.0 °C (90th percentile of recorded temperature (no threshold supplied — replace with a literature or species-specific value))

| Species | Cages | Mortality/day, hot days (% of stock) | Other days | Ratio | Strongest lag (d) | ρ at that lag |
|---|---|---|---|---|---|---|
| Gabit | 3 | 0.099 | 0.036 | 2.8 | 2 | 0.35 |
| Shaam | 3 | 0.224 | 0.042 | 5.3 | 2 | 0.45 |
| Sobaity | 3 | 0.461 | 0.055 | 8.4 | 2 | 0.49 |

8 lags tested per species; the 'strongest lag' is selected post hoc and must be confirmed, not reported as a finding.

Likely confounders: dissolved oxygen (falls as temperature rises), season and fish size/age, disease outbreaks, handling, grading or harvest events, feeding changes during heat.  
Next step: Pre-register the threshold from literature, then fit a mixed model (cage as random effect, temporal autocorrelation) or design a controlled thermal-challenge trial for causal evidence.

### Species comparison — `species_survival`
**Draft question:** Does survival over a production cycle differ between species reared under the same farm conditions?

Method: Per-cycle survival averaged per cage over complete production cycles (cage = experimental unit), compared across species with Kruskal–Wallis.  
Data sufficiency: **adequate_for_exploration**   
- Gabit: 3 cages, mean survival 86.2%
- Shaam: 3 cages, mean survival 79.9%
- Sobaity: 3 cages, mean survival 67.8%
- Kruskal–Wallis on per-cage survival: H = 7.20, P = 0.027

Likely confounders: stocking date and season, initial fish size and hatchery source, cage position (exposure, current), stocking density.  
Next step: Check whether species were stocked at comparable times and sizes; if not, compare within matched periods or design a side-by-side trial.

### Growth performance — `temperature_growth`
**Draft question:** How does specific growth rate change with mean water temperature over the sampling interval, and is there an optimum or upper limit for each species?

Method: Per sampling interval: SGR vs mean temperature (Spearman; descriptive quadratic fit per species).  
Data sufficiency: **adequate_for_exploration**   

| Species | Intervals | Spearman ρ | Fitted peak (°C, descriptive) |
|---|---|---|---|
| Gabit | 95 | 0.61 | 28.7 |
| Shaam | 96 | 0.46 | 25.3 |
| Sobaity | 96 | 0.21 | 26.4 |

Likely confounders: fish size (SGR falls with size regardless of temperature), feeding rate and feed type, dissolved oxygen, ABW sampling error (small samples).  
Next step: Add fish size as a covariate (e.g. mixed model with cage random effect) before interpreting a temperature effect.

### Feed efficiency — `temperature_fcr`
**Draft question:** How does feed conversion ratio change with water temperature, and above which temperature does feeding become inefficient?

Method: Per sampling interval: FCR vs mean temperature (Spearman; descriptive quadratic fit per species).  
Data sufficiency: **adequate_for_exploration**   

| Species | Intervals | Spearman ρ | Fitted peak (°C, descriptive) |
|---|---|---|---|
| Gabit | 88 | -0.41 | 28.2 |
| Shaam | 88 | -0.27 | 27.9 |
| Sobaity | 93 | -0.12 | 26.6 |

Likely confounders: fish size (SGR falls with size regardless of temperature), feeding rate and feed type, dissolved oxygen, ABW sampling error (small samples).  
Next step: Add fish size as a covariate (e.g. mixed model with cage random effect) before interpreting a temperature effect.

### Seasonal effects — `seasonal_variation`
**Draft question:** How do growth and mortality vary across seasons, and is the pattern consistent between years and species?

Method: Season means of daily mortality (Kruskal–Wallis) and interval SGR, per species. Seasons are Northern-Hemisphere meteorological seasons.  
Data sufficiency: **adequate_for_exploration**   
- Gabit: mean daily mortality % by season autumn 0.031, spring 0.030, summer 0.071, winter 0.031
- Shaam: mean daily mortality % by season autumn 0.035, spring 0.029, summer 0.151, winter 0.031
- Sobaity: mean daily mortality % by season autumn 0.042, spring 0.030, summer 0.321, winter 0.030

Likely confounders: fish age/size progression within a production cycle, stocking and harvest timing, season bundles temperature, DO, salinity and day length together.  
Next step: Compare like-for-like size classes across years; decompose season into temperature, DO and salinity effects.

### Environmental interaction — `environmental_interaction`
**Draft question:** Do low dissolved oxygen and salinity extremes add to temperature-related mortality, and is the combination of high temperature and low DO worse than either alone?

Method: Spearman correlations of DO and salinity with mortality; mean mortality in temperature (upper quartile) x DO (lower quartile) cells, per species.  
Data sufficiency: **adequate_for_exploration**   

| Species | Hot + low DO | Hot only | Low DO only | Neither | Days hot + low DO |
|---|---|---|---|---|---|
| Gabit | 0.075 | 0.050 | 0.029 | 0.031 | 711 |
| Shaam | 0.163 | 0.106 | 0.031 | 0.030 | 717 |
| Sobaity | 0.355 | 0.181 | 0.040 | 0.030 | 707 |

Likely confounders: temperature and DO are physically linked, biomass load (oxygen demand), algal blooms / weather events.  
Next step: Fit a model with temperature, DO and their interaction (cage random effect); quarter-based cells are exploratory cut-points.

Skipped (columns not in the data): `density_growth` needs ['date', 'cage', 'abw_g', 'stocking_density_kg_m3']

## 4. Literature search candidates (Literature Review Agent)

CrossRef search hits only. None has been read or added to the reference library yet: a title is not evidence of a finding.

**Sparidentex hasta temperature growth**
- Gamoori, Eryalçın (2025). Probiotic-Enriched Live Food Improves Growth, Gut Health, and Fatty Acid Profile in Sobaity Seabream (Sparidentex Hasta) Larvae. *None*. doi:10.2139/ssrn.5391529
- Munro (1948). Sparidentex hasta (Valenciennes), a New Name for Chrysophrys cuvieri Day. *Copeia*. doi:10.2307/1438716
- Monjezi Veisi, Waiho (2024). Neurophysiological responses of juvenile Sobaity seabream, Sparidentex hasta, exposed to different concentrations of selenium. *None*. doi:10.3897/arphapreprints.e120385
- Agh, Morshedi (2022). The effects of single and combined use of Lactobacillus plantarum and xylooligosacharide on growth, feed utilization, immune responses, and immune and growth related genes of sobaity (Sparidentex hasta) fingerlings. *Aquaculture Reports*. doi:10.1016/j.aqrep.2022.101271
- Taravat, Preeta (2019). Effect of Short Term Food Deprivation and Re-Feeding on Growth, Feeding and Biochemical Body Composition in Sobaity Fish, Sparidentex hasta. *Veterinary Research*. doi:10.36478/vr.2019.10.18

**sobaity seabream culture Arabian Gulf**
- Young, Shaikhi (2023). Sobaity Seabream Culture in High-Temperature Conditions. *North American Journal of Aquaculture*. doi:10.1002/naaq.10287
- Monjezi Veisi, Waiho (2024). Neurophysiological responses of juvenile Sobaity seabream, Sparidentex hasta, exposed to different concentrations of selenium. *None*. doi:10.3897/arphapreprints.e120385
- n.a. (2002). DILMUN, THE ANCIENT CULTURE OF THE GULF. *The Archaeology of the Arabian Gulf*. doi:10.4324/9780203037263-8
- Nikoo, Torfi Mozanzadeh (2024). The effects of protein hydrolysates from rainbow trout by-products on growth, digestive and antioxidant enzymes, and liver lysozyme activity in sobaity (Sparidentex hasta) and Arabian yellowfin (Acanthopagrus arabicus) seabream juveniles. *Aquaculture Reports*. doi:10.1016/j.aqrep.2024.102229
- Mohamed, Al-Hassani (2021). Population dynamics of Arabian yellowfin seabream, Acanthopagrus arabicus Iwatsuki, 2013 from Iraqi marine waters, Arabian Gulf. *International Journal of Fisheries and Aquatic Studies*. doi:10.22271/fish.2021.v9.i4a.2517

**cage aquaculture high temperature mortality sea bream**
- Jian, Cheng (2003). Temperature and salinity tolerances of yellowfin sea bream, Acanthopagrus latus, at different salinity and temperature levels. *Aquaculture Research*. doi:10.1046/j.1365-2109.2003.00800.x
- Sumithra, Krupesha Sharma (2022). Red sea bream iridovirus infection in cage farmed Asian sea bass (Lates calcarifer): Insights into the pathology, epizootiology, and genetic diversity. *Aquaculture*. doi:10.1016/j.aquaculture.2021.737571
- Woo (1990). Metabolic and osmoregulatory changes during temperature acclimation in the red sea bream, Chrysophrys major: Implications for its culture in the subtropics. *Aquaculture*. doi:10.1016/0044-8486(90)90275-r
- Mladineo, Šegvić (2009). Molecular evidence for the lack of transmission of the monogenean Sparicotyle chrysophrii (Monogenea, Polyopisthocotylea) and isopod Ceratothoa oestroides (Crustacea, Cymothoidae) between wild bogue (Boops boops) and cage-reared sea bream (Sparus aurata) and sea bass (Dicentrarchus labrax). *Aquaculture*. doi:10.1016/j.aquaculture.2009.07.017
- Mahardika (2009). ELECTRON MICROSCOPIC STUDY ON ENLARGED CELLS OF RED SEA BREAM, Pagrus major INFECTED BY THE RED SEA BREAM IRIDOVIRUS (RSIV, GENUS Megalocytivirus, FAMILY Iridoviridae). *Indonesian Aquaculture Journal*. doi:10.15578/iaj.4.1.2009.53-63

## 5. Gate G1 — proposed, awaiting your decision

Recommended: **thermal tolerance** (mortality above a temperature threshold, compared across species). Before G1 approval: replace the 90th-percentile default threshold with a literature-sourced value per species, and confirm the column mapping and the flagged data errors with the farm team.
