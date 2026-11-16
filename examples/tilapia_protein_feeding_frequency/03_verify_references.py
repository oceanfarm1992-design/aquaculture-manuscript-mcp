"""Verify every reference the example manuscript cites against CrossRef,
using this package's resolve_doi_metadata / search_works. Anything that fails
to resolve is reported and must be dropped from the manuscript, not cited
from memory.

Writes verified_references.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aquaculture_manuscript_mcp.tools import citations

# Generic client name for this example run.
citations._HEADERS = {"User-Agent": "manuscript-example-reference-check/0.1"}

HERE = Path(__file__).parent

DOIS = [
    "10.1139/f75-274",                    # Emerson et al. 1975, ammonia equilibrium
    "10.1016/0044-8486(88)90007-5",       # Siddiqui et al. 1988, protein level, Nile tilapia
    "10.1016/j.aquaculture.2009.10.027",  # Abdel-Tawwab et al. 2010, protein x body weight
    "10.1016/j.aquaculture.2003.12.012",  # Riche et al. 2004, feeding frequency, tilapia
    "10.17226/13039",                     # NRC 2011, Nutrient Requirements of Fish and Shrimp
    "10.4060/cd0683en",                   # FAO 2024, State of World Fisheries and Aquaculture
    "10.1371/journal.pbio.3000410",       # Percie du Sert et al. 2020, ARRIVE 2.0
    "10.1038/s41592-019-0686-2",          # Virtanen et al. 2020, SciPy 1.0
    "10.25080/Majora-92bf1922-011",       # Seabold & Perktold 2010, statsmodels
    "10.1079/9780851990149.0000",         # El-Sayed 2006, Tilapia Culture
]

SEARCHES = [
    "Yossa feed conversion ratio fish nutrition Journal of Applied Aquaculture 2014",
]


def main() -> None:
    verified, failed = [], []
    for doi in DOIS:
        try:
            verified.append(citations.resolve_doi_metadata(doi))
        except Exception as exc:  # report, never silently keep
            failed.append({"doi": doi, "error": str(exc)})
    search_hits = {q: citations.search_works(q, rows=3) for q in SEARCHES}
    out = {"verified": verified, "failed": failed, "search_hits": search_hits}
    (HERE / "verified_references.json").write_text(json.dumps(out, indent=2))
    for v in verified:
        print(f"OK   {v['doi']} | {v['year']} | {', '.join(a.split(',')[0] for a in v['authors'][:3])} | {v['title']} | {v['container_title']} {v['volume']}:{v['page']}")
    for f in failed:
        print(f"FAIL {f['doi']} | {f['error']}")
    for q, hits in search_hits.items():
        print(f"\nsearch: {q}")
        for h in hits:
            print(f"  {h['doi']} | {h['year']} | {', '.join(a.split(',')[0] for a in h['authors'][:3])} | {h['title']} | {h['container_title']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
