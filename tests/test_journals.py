import pytest

from aquaculture_manuscript_mcp import journals


def test_get_journal_known_key():
    profile = journals.get_journal("elsevier_aquaculture")
    assert profile["abstract_max_words"] == 250
    assert profile["ai_disclosure_required"] is True


def test_get_journal_unknown_key_raises_with_known_list():
    with pytest.raises(ValueError, match="Known profiles"):
        journals.get_journal("not_a_real_journal")


def test_format_journal_rules_includes_limits():
    text = journals.format_journal_rules("wiley_aquaculture_research")
    assert "200 words" in text
    assert "4-6" in text


def test_wiley_ai_disclosure_marked_unconfirmed_not_false():
    # Must not silently claim "not required" when it was never confirmed.
    profile = journals.get_journal("wiley_aquaculture_research")
    assert profile["ai_disclosure_required"] is None
