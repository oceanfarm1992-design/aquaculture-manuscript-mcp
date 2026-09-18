from aquaculture_manuscript_mcp.tools import bibtex_tools

VALID_ENTRY = """
@article{yossa2014,
  author = {Yossa, Rodrigue},
  title = {Writing a Scientific Manuscript from Original Aquaculture Research},
  journal = {Journal of Applied Aquaculture},
  year = {2014},
  doi = {10.1080/10454438.2014.965572},
}
"""


def test_valid_entry_is_clean():
    result = bibtex_tools.validate_bibtex(VALID_ENTRY)
    assert result["clean"] is True
    assert result["entry_count"] == 1
    assert result["entries_missing_required_fields"] == []


def test_missing_required_fields_detected():
    text = """
    @article{missing_fields,
      author = {Someone, S.},
      title = {A paper with no journal or year},
    }
    """
    result = bibtex_tools.validate_bibtex(text)
    assert result["clean"] is False
    assert result["entries_missing_required_fields"][0]["key"] == "missing_fields"
    assert set(result["entries_missing_required_fields"][0]["missing_fields"]) == {"journal", "year"}


def test_entry_missing_doi_or_url_flagged():
    text = """
    @article{no_identifier,
      author = {A, B},
      title = {T},
      journal = {J},
      year = {2020},
    }
    """
    result = bibtex_tools.validate_bibtex(text)
    assert "no_identifier" in result["entries_missing_doi_or_url"]


def test_duplicate_key_surfaces_as_parse_error():
    text = VALID_ENTRY + """
    @article{yossa2014,
      author = {Duplicate, D.},
      title = {Duplicate key test},
      journal = {X},
      year = {2020},
    }
    """
    result = bibtex_tools.validate_bibtex(text)
    assert result["clean"] is False
    assert len(result["parse_errors"]) >= 1


def test_malformed_bibtex_reports_parse_error():
    text = "@article{broken_entry\n  author = {No Closing Brace\n"
    result = bibtex_tools.validate_bibtex(text)
    assert result["clean"] is False
    assert len(result["parse_errors"]) >= 1
