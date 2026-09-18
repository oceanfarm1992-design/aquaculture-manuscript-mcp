"""Water-quality chemistry and reference-range checking.

Two different confidence levels live in this file, and the functions keep
them separate rather than blending them into one "safe/unsafe" verdict:

1. calculate_unionized_ammonia — real, unambiguous aquatic chemistry
   (Emerson et al. 1975), independent of species. High confidence.
2. check_water_parameter — species "typical range" lookups. These come from
   a small number of specific sources (cited per entry) and the aquaculture
   literature does not fully agree on exact numbers even for well-studied
   species — a web search for this project turned up meaningfully different
   figures across sources. Treat every result as a sanity-check flag to
   verify against current, species/strain-specific literature — NOT as a
   citable threshold for a manuscript by itself.

Only two species are covered (Nile tilapia, Pacific whiteleg shrimp) because
those are the ones a source-backed range could actually be found for in the
time available. Do not add another species without a specific citation per
parameter — an uncited "typical range" is exactly the fabrication risk this
whole project is built to avoid.
"""

from __future__ import annotations

# Each entry: (low, high, unit, citation). `None` bounds mean "no established
# lower/upper bound found" rather than "no limit exists" — still flag it.
REFERENCE_RANGES: dict[str, dict[str, dict]] = {
    "nile_tilapia": {
        "display_name": "Nile tilapia (Oreochromis niloticus)",
        "parameters": {
            "temperature_c": {
                "optimal_low": 25.0,
                "optimal_high": 27.0,
                "survival_low": 11.0,
                "survival_high": 42.0,
                "unit": "degrees C",
                "source": "FAO Cultured Aquatic Species Information Programme, Oreochromis niloticus (FAO, 2012) — survival limits; commonly cited optimal growth range from recent growth-performance studies.",
            },
            "ph": {
                "optimal_low": 6.0,
                "optimal_high": 9.0,
                "unit": "pH",
                "source": "Commonly cited tolerant range across recent Nile tilapia water-quality studies (e.g. Fisheries and Aquatic Sciences 20:30, 2017).",
            },
            "dissolved_oxygen_mg_l": {
                "optimal_low": 5.0,
                "optimal_high": None,
                "unit": "mg/L",
                "source": "Nile tilapia is broadly oxygen-tolerant relative to other cultured species (FAO CASIP); one growth-performance study reports optimal DO 5.49-5.87 mg/L. Treat as approximate, not a strict cutoff.",
            },
            "total_ammonia_nitrogen_mg_l": {
                "optimal_low": 0.0,
                "optimal_high": 0.34,
                "unit": "mg/L TAN",
                "source": "Reported optimal TAN range 0.29-0.34 mg/L in a Nile tilapia juvenile growth study; check unionized-fraction toxicity separately via calculate_unionized_ammonia, since TAN alone doesn't determine toxicity.",
            },
        },
    },
    "whiteleg_shrimp": {
        "display_name": "Pacific whiteleg shrimp (Litopenaeus vannamei)",
        "parameters": {
            "dissolved_oxygen_mg_l": {
                "optimal_low": 5.0,
                "optimal_high": None,
                "unit": "mg/L",
                "source": "Widely cited minimum for optimal L. vannamei culture across recent intensive-system studies.",
            },
            "salinity_ppt": {
                "optimal_low": 15.0,
                "optimal_high": 25.0,
                "tolerance_low": 5.0,
                "tolerance_high": 35.0,
                "unit": "ppt",
                "source": "Commonly cited tolerance (5-35 ppt) and optimal (15-25 ppt) ranges for L. vannamei culture.",
            },
        },
    },
}


def calculate_unionized_ammonia(
    total_ammonia_nitrogen_mg_l: float, ph: float, temperature_c: float
) -> dict:
    """Fraction and concentration of un-ionized ammonia (NH3-N) from total
    ammonia nitrogen (TAN), pH, and temperature.

    Formula (Emerson, K., Russo, R.C., Lund, R.E. and Thurston, R.V. 1975.
    Aqueous Ammonia Equilibrium Calculations: Effect of pH and Temperature.
    J. Fish. Res. Board Can. 32:2379-2383), valid for 0-50 degrees C:
        pKa = 0.09018 + 2729.92 / (temperature_C + 273.15)
        NH3 fraction = 1 / (1 + 10^(pKa - pH))

    This is general aquatic chemistry, not species-specific — species differ
    in how much NH3-N they tolerate, not in this equilibrium calculation.
    """
    if total_ammonia_nitrogen_mg_l < 0:
        raise ValueError("total_ammonia_nitrogen_mg_l cannot be negative")
    if not (0 <= temperature_c <= 50):
        raise ValueError("temperature_c must be within 0-50 (the range the Emerson et al. 1975 equation was fit to)")
    if not (0 < ph < 14):
        raise ValueError("ph must be between 0 and 14")

    pka = 0.09018 + 2729.92 / (temperature_c + 273.15)
    nh3_fraction = 1 / (1 + 10 ** (pka - ph))
    nh3_mg_l = total_ammonia_nitrogen_mg_l * nh3_fraction

    return {
        "unionized_ammonia_fraction": nh3_fraction,
        "unionized_ammonia_percent": nh3_fraction * 100,
        "unionized_ammonia_nh3_n_mg_l": nh3_mg_l,
        "pka": pka,
        "source": "Emerson et al. (1975), J. Fish. Res. Board Can. 32:2379-2383",
        "note": "This calculates the chemistry only. Species-specific NH3 toxicity thresholds are not applied here — check the primary literature for your species.",
    }


def list_supported_species() -> dict:
    """Species/parameters with a cited reference range available. Anything
    not listed here has no reference data in this tool — that means "not yet
    sourced", not "no limit exists"."""
    return {
        key: {
            "display_name": v["display_name"],
            "parameters": sorted(v["parameters"]),
        }
        for key, v in REFERENCE_RANGES.items()
    }


def check_water_parameter(species: str, parameter: str, measured_value: float) -> dict:
    """Check a measured value against a cited reference range, if one exists.

    Never returns a bare pass/fail — always includes the source and a
    reminder that this is a sanity check, not a citable threshold by itself.
    """
    if species not in REFERENCE_RANGES:
        known = ", ".join(sorted(REFERENCE_RANGES))
        raise ValueError(
            f"No reference data for species '{species}'. Known: {known}. "
            "This means no source-backed range was found for other species "
            "in the time available — it does not mean no threshold exists. "
            "Add one only with a specific citation."
        )
    params = REFERENCE_RANGES[species]["parameters"]
    if parameter not in params:
        known = ", ".join(sorted(params))
        raise ValueError(
            f"No reference range for parameter '{parameter}' in "
            f"{REFERENCE_RANGES[species]['display_name']}. Known parameters "
            f"for this species: {known}."
        )

    ref = params[parameter]
    low = ref.get("optimal_low")
    high = ref.get("optimal_high")
    within_optimal = (low is None or measured_value >= low) and (high is None or measured_value <= high)

    return {
        "species": REFERENCE_RANGES[species]["display_name"],
        "parameter": parameter,
        "measured_value": measured_value,
        "unit": ref["unit"],
        "optimal_range": [low, high],
        "within_cited_optimal_range": within_optimal,
        "source": ref["source"],
        "caveat": (
            "This range is a sanity-check flag from a limited literature "
            "search, not a verified universal threshold — confirm against "
            "current, strain/system-specific literature before citing it in "
            "a manuscript."
        ),
    }
