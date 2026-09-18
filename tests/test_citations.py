"""Tests against the real CrossRef API. Marked 'network' so they can be
excluded with `pytest -m "not network"` in offline environments; CI runs them
by default since CrossRef is stable and this is exactly what the tool
promises to verify against."""

import pytest

from aquaculture_manuscript_mcp.tools import citations

pytestmark = pytest.mark.network


def test_resolve_known_doi():
    # The actual Yossa (2014) DOI, confirmed by reading the source PDF.
    result = citations.resolve_doi_metadata("10.1080/10454438.2014.965572")
    assert result["title"] == "Writing a Scientific Manuscript from Original Aquaculture Research"
    assert result["year"] == 2014
    assert "Yossa" in result["authors"][0]


def test_resolve_unknown_doi_raises():
    with pytest.raises(ValueError, match="not registered"):
        citations.resolve_doi_metadata("10.9999/not-a-real-doi-xyz-12345")


def test_search_returns_results():
    results = citations.search_works("aquaculture manuscript writing", rows=3)
    assert len(results) == 3
    assert all("doi" in r for r in results)


def test_search_rejects_invalid_rows():
    with pytest.raises(ValueError, match="rows"):
        citations.search_works("test", rows=100)
