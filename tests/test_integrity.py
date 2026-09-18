from aquaculture_manuscript_mcp import integrity


def test_flags_verbatim_overlap():
    draft = "Growth improved significantly under the modified feeding regime used here."
    source = ["Growth improved significantly under a modified feeding regime in prior trials."]
    result = integrity.check_overlap(draft, source)
    assert result["clean"] is False
    assert result["overlap_count"] > 0
    assert any("growth improved significantly" in f["phrase"] for f in result["findings"])


def test_clean_when_no_overlap():
    draft = "Fish grew markedly faster once we adjusted the feeding schedule in this trial."
    source = ["Growth improved significantly under a modified feeding regime in prior trials."]
    result = integrity.check_overlap(draft, source)
    assert result["clean"] is True
    assert result["overlap_count"] == 0


def test_clean_with_no_sources():
    result = integrity.check_overlap("Any text at all.", [])
    assert result["clean"] is True


def test_two_word_overlap_not_flagged_below_threshold():
    draft = "The water temperature was measured daily."
    source = ["The water temperature fluctuated throughout the trial period."]
    result = integrity.check_overlap(draft, source, min_run=3)
    # "The water temperature" is exactly 3 words and IS shared -> should flag.
    assert result["overlap_count"] >= 1
