"""Offline: CrossRef titles can contain inline markup (seen on
10.1046/j.1365-2109.2003.00800.x), which must not leak into documents."""

from aquaculture_manuscript_mcp.tools.citations import clean_title


def test_markup_removed_and_spacing_fixed():
    raw = "Temperature and salinity tolerances of yellowfin sea bream,<i>Acanthopagrus latus,</i>at different salinity and temperature levels"
    assert clean_title(raw) == "Temperature and salinity tolerances of yellowfin sea bream, Acanthopagrus latus, at different salinity and temperature levels"


def test_parentheses_entities_and_plain_titles():
    assert clean_title("Growth of sobaity (<i>Sparidentex hasta</i>) &amp; diet") == "Growth of sobaity (Sparidentex hasta) & diet"
    assert clean_title("Plain title") == "Plain title"
    assert clean_title(None) is None
