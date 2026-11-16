# Phase 1 demo: research intelligence on cage-farm records (Workflow B)

**The records here are synthetic.** They imitate three years of daily offshore
cage data (Sobaity, Shaam and Gabit, three cages each, harvested and restocked
every March). Nothing here describes a real farm.

The generator builds in known patterns so you can check what the agents find:

| Built into the data | What Phase 1 reported |
|---|---|
| Heat mortality above ~32 °C: Sobaity most sensitive, Gabit least | Mortality on hot days vs other days: Sobaity 8.4×, Shaam 5.3×, Gabit 2.8× |
| Mortality lags temperature by ~2 days | Strongest lag 2 days for all three species (flagged as post hoc) |
| Low DO on hot days adds mortality | Hot + low-DO days worse than hot-only days in every species |
| Growth peaks near 26–28 °C | Descriptive SGR peak 27.7–28.7 °C |
| Planted errors: 99 °C reading, negative feed, duplicates, conflicting cage-day, ABW entered in kg, 10-day gap | All flagged by `check_data_quality` |

Read the output: [phase1_report.md](phase1_report.md).

Run it from this folder with the repo's venv:

```bash
python 01_generate_synthetic_farm_records.py
python 02_run_phase1.py
```

`02_run_phase1.py` creates `project_heat_stress/` (raw data with checksum,
saved analyses, a G1 decision recorded as *proposed*) and writes the report.
It searches CrossRef, so it needs internet access.

## Bugs this demo caught (now fixed and covered by tests)

- **Restocking.** Survival went negative and FCR reached 10¹³ because metrics
  ran across the annual harvest and restock. A rise in fish count now starts a
  new production cycle, and nothing is computed across one.
- **Near-zero growth.** Winter intervals with ~0 biomass gain gave absurd FCRs.
  Interval FCR is now undefined below 0.5% gain, and cycle FCR is total feed ÷
  total gain.
