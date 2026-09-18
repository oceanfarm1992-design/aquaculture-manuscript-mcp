"""BibTeX validation — parse errors, missing required fields, duplicate keys.

Pure structural validation via bibtexparser; does not verify a citation is
real (see citations.py / resolve_doi_metadata for that) or that it supports
the claim it's attached to (that stays a human/model judgment call).
"""

from __future__ import annotations

import bibtexparser

# Minimal required-field sets per common entry type (not exhaustive BibTeX
# spec — flags the fields a reviewer would actually notice missing).
_REQUIRED_FIELDS: dict[str, set[str]] = {
    "article": {"author", "title", "journal", "year"},
    "book": {"author", "title", "publisher", "year"},
    "inbook": {"author", "title", "publisher", "year"},
    "incollection": {"author", "title", "booktitle", "publisher", "year"},
    "inproceedings": {"author", "title", "booktitle", "year"},
    "conference": {"author", "title", "booktitle", "year"},
    "phdthesis": {"author", "title", "school", "year"},
    "mastersthesis": {"author", "title", "school", "year"},
    "techreport": {"author", "title", "institution", "year"},
    "misc": {"title"},
    "online": {"title"},
}


def validate_bibtex(bibtex_text: str) -> dict:
    """Validate a .bib file's contents. Returns parse errors, missing
    required fields per entry, duplicate keys, and entries with no DOI/URL
    (harder to independently verify)."""
    library = bibtexparser.parse_string(bibtex_text)

    parse_errors = [
        {
            "line": getattr(block, "start_line", None),
            "message": str(getattr(block, "error", block)),
        }
        for block in library.failed_blocks
    ]

    seen_keys: dict[str, int] = {}
    duplicate_keys = []
    entries_missing_fields = []
    entries_missing_identifier = []

    for entry in library.entries:
        seen_keys[entry.key] = seen_keys.get(entry.key, 0) + 1

        entry_type = entry.entry_type.lower()
        field_names = {f.key.lower() for f in entry.fields}
        required = _REQUIRED_FIELDS.get(entry_type, {"title", "year"})
        missing = sorted(required - field_names)
        if missing:
            entries_missing_fields.append({"key": entry.key, "type": entry_type, "missing_fields": missing})

        if "doi" not in field_names and "url" not in field_names:
            entries_missing_identifier.append(entry.key)

    duplicate_keys = sorted(k for k, count in seen_keys.items() if count > 1)

    return {
        "entry_count": len(library.entries),
        "parse_errors": parse_errors,
        "duplicate_keys": duplicate_keys,
        "entries_missing_required_fields": entries_missing_fields,
        "entries_missing_doi_or_url": entries_missing_identifier,
        "clean": not (parse_errors or duplicate_keys or entries_missing_fields),
    }
