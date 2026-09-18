import pytest

from aquaculture_manuscript_mcp.tools import water_quality


def test_unionized_ammonia_known_value():
    # Standard reference point: pH 8, 25C -> ~5.4% un-ionized fraction.
    result = water_quality.calculate_unionized_ammonia(total_ammonia_nitrogen_mg_l=1.0, ph=8.0, temperature_c=25.0)
    assert result["unionized_ammonia_percent"] == pytest.approx(5.4, abs=0.1)
    assert result["unionized_ammonia_nh3_n_mg_l"] == pytest.approx(0.054, abs=0.001)


def test_unionized_ammonia_higher_ph_increases_fraction():
    low = water_quality.calculate_unionized_ammonia(1.0, ph=7.0, temperature_c=25.0)
    high = water_quality.calculate_unionized_ammonia(1.0, ph=9.0, temperature_c=25.0)
    assert high["unionized_ammonia_fraction"] > low["unionized_ammonia_fraction"]


def test_unionized_ammonia_temperature_out_of_range_raises():
    with pytest.raises(ValueError, match="temperature_c"):
        water_quality.calculate_unionized_ammonia(1.0, ph=8.0, temperature_c=60.0)


def test_unionized_ammonia_negative_tan_raises():
    with pytest.raises(ValueError, match="negative"):
        water_quality.calculate_unionized_ammonia(-1.0, ph=8.0, temperature_c=25.0)


def test_check_water_parameter_known_species():
    result = water_quality.check_water_parameter("nile_tilapia", "dissolved_oxygen_mg_l", 6.0)
    assert result["within_cited_optimal_range"] is True
    assert "source" in result and result["source"]
    assert "caveat" in result and result["caveat"]


def test_check_water_parameter_out_of_range():
    result = water_quality.check_water_parameter("nile_tilapia", "ph", 4.0)
    assert result["within_cited_optimal_range"] is False


def test_check_water_parameter_unknown_species_raises_with_explanation():
    with pytest.raises(ValueError, match="No reference data"):
        water_quality.check_water_parameter("atlantic_salmon", "temperature_c", 10)


def test_check_water_parameter_unknown_parameter_raises():
    with pytest.raises(ValueError, match="No reference range"):
        water_quality.check_water_parameter("nile_tilapia", "made_up_parameter", 1.0)


def test_list_supported_species_only_sourced_species():
    species = water_quality.list_supported_species()
    # Only species we actually found citable ranges for should be listed.
    assert set(species) == {"nile_tilapia", "whiteleg_shrimp"}
