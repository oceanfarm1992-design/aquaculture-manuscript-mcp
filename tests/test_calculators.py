import math

import pytest

from aquaculture_manuscript_mcp.tools import calculators


def test_fcr_matches_yossa_worked_example():
    # FCR = (feed x dry matter) / (final - initial)
    result = calculators.calculate_fcr(feed_given_g=100, initial_weight_g=50, final_weight_g=100, dry_matter_fraction=0.9)
    assert result["dry_feed_given_g"] == pytest.approx(90.0)
    assert result["weight_gain_g"] == pytest.approx(50.0)
    assert result["fcr"] == pytest.approx(1.8)


def test_fcr_zero_weight_gain_raises():
    with pytest.raises(ValueError, match="weight gain"):
        calculators.calculate_fcr(feed_given_g=100, initial_weight_g=50, final_weight_g=50)


def test_fcr_negative_weight_gain_raises():
    with pytest.raises(ValueError, match="weight gain"):
        calculators.calculate_fcr(feed_given_g=100, initial_weight_g=60, final_weight_g=50)


def test_fcr_bad_dry_matter_fraction_raises():
    with pytest.raises(ValueError, match="dry_matter_fraction"):
        calculators.calculate_fcr(feed_given_g=100, initial_weight_g=50, final_weight_g=100, dry_matter_fraction=1.5)


def test_biomass_corrected_fcr_credits_mortality_biomass():
    result = calculators.calculate_biomass_corrected_fcr(
        feed_given_g=200, initial_biomass_g=1000, final_biomass_g=1400, dead_or_removed_biomass_g=100
    )
    # adjusted gain = (1400 + 100) - 1000 = 500
    assert result["adjusted_gain_g"] == pytest.approx(500.0)
    assert result["biomass_corrected_fcr"] == pytest.approx(200 / 500)


def test_economic_fcr():
    result = calculators.calculate_economic_fcr(
        feed_given_g=1000, feed_cost_per_kg=2.0, weight_gain_g=500, product_value_per_kg=6.0
    )
    # feed cost = 1kg * 2 = 2; gain value = 0.5kg * 6 = 3; ratio = 2/3
    assert result["feed_cost"] == pytest.approx(2.0)
    assert result["gain_value"] == pytest.approx(3.0)
    assert result["economic_fcr"] == pytest.approx(2 / 3)


def test_sgr_matches_formula():
    result = calculators.calculate_sgr(initial_weight_g=10, final_weight_g=50, days=30)
    expected = (math.log(50) - math.log(10)) / 30 * 100
    assert result["sgr_percent_per_day"] == pytest.approx(expected)


def test_sgr_zero_days_raises():
    with pytest.raises(ValueError, match="days"):
        calculators.calculate_sgr(initial_weight_g=10, final_weight_g=50, days=0)


def test_sgr_nonpositive_weight_raises():
    with pytest.raises(ValueError, match="weights"):
        calculators.calculate_sgr(initial_weight_g=0, final_weight_g=50, days=30)


def test_stocking_density_volume_and_area():
    result = calculators.calculate_stocking_density(biomass_kg=100, volume_m3=20, area_m2=50)
    assert result["density_kg_per_m3"] == pytest.approx(5.0)
    assert result["density_kg_per_m2"] == pytest.approx(2.0)


def test_stocking_density_requires_volume_or_area():
    with pytest.raises(ValueError, match="volume_m3 or area_m2"):
        calculators.calculate_stocking_density(biomass_kg=100)


def test_survival_rate_basic():
    result = calculators.calculate_survival_rate(initial_count=100, final_count=85)
    assert result["survival_percent"] == pytest.approx(85.0)
    assert result["cumulative_mortality_percent"] == pytest.approx(15.0)
    assert result["mortality_count"] == 15


def test_survival_rate_final_exceeds_initial_raises():
    with pytest.raises(ValueError, match="exceeds"):
        calculators.calculate_survival_rate(initial_count=50, final_count=60)


def test_survival_rate_zero_initial_raises():
    with pytest.raises(ValueError, match="positive"):
        calculators.calculate_survival_rate(initial_count=0, final_count=0)
