"""Per-journal formatting rules.

Only include facts actually confirmed by reading that journal's own author guide.
Leave a field as None rather than guessing — the agents are instructed to say
"not confirmed, check the journal's guide" rather than fill gaps with a plausible
number pulled from a different journal.
"""

from __future__ import annotations

JOURNALS: dict[str, dict] = {
    "elsevier_aquaculture": {
        "display_name": "Elsevier Aquaculture (ISSN 0044-8486)",
        "abstract_max_words": 250,
        "keyword_count": "5-7",
        "citation_style": None,
        "ai_disclosure_required": True,
        "ai_disclosure_template": (
            "Declaration of generative AI and AI-assisted technologies in the "
            "manuscript preparation process.\n\n"
            "During the preparation of this work, the author(s) used "
            "[NAME OF TOOL/SERVICE] in order to [REASON]. After using this "
            "tool/service, the author(s) reviewed and edited the content as "
            "needed and take full responsibility for the content of the "
            "published article."
        ),
        "notes": (
            "Single-paragraph abstract, no citations/abbreviations. Source "
            "files must be .doc/.docx or .tex, single-column (double-column "
            "only for LaTeX). AI tools must not be listed as an author. "
            "Confirmed by reading the journal's own guide-for-authors page."
        ),
    },
    "wiley_aquaculture_research": {
        "display_name": "Wiley Aquaculture Research",
        "abstract_max_words": 200,
        "keyword_count": "4-6",
        "citation_style": "APA 6th edition, author-date in-text citations",
        "ai_disclosure_required": None,
        "ai_disclosure_template": None,
        "notes": (
            "Ethics Statement required in the Methods section naming the "
            "approving body. ARRIVE guidelines encouraged for animal studies. "
            "Short Communications <=1500 words excluding keywords/tables/"
            "references. Generative-AI disclosure policy was not visible in "
            "the author-guide pages available when this profile was built — "
            "confirm directly with Wiley's Best Practice Guidelines on "
            "Research Integrity and Publishing Ethics before assuming none is "
            "required."
        ),
    },
}


def list_journals() -> dict[str, dict]:
    return JOURNALS


def get_journal(journal_key: str) -> dict:
    try:
        return JOURNALS[journal_key]
    except KeyError as exc:
        valid = ", ".join(sorted(JOURNALS))
        raise ValueError(
            f"Unknown journal '{journal_key}'. Known profiles: {valid}. "
            "If your target journal isn't listed, read its actual author "
            "guide and supply the limits directly rather than guessing."
        ) from exc


def format_journal_rules(journal_key: str) -> str:
    j = get_journal(journal_key)
    lines = [f"Target journal: {j['display_name']}"]
    lines.append(
        f"Abstract limit: {j['abstract_max_words']} words"
        if j["abstract_max_words"] is not None
        else "Abstract limit: not confirmed — ask the user or check the journal's guide."
    )
    lines.append(f"Keyword count: {j['keyword_count']}")
    lines.append(
        f"Citation style: {j['citation_style']}"
        if j["citation_style"]
        else "Citation style: not confirmed for this journal — check its author guide."
    )
    if j["ai_disclosure_required"] is True:
        lines.append("AI-use declaration: required before the references list (template available).")
    elif j["ai_disclosure_required"] is None:
        lines.append(
            "AI-use declaration: not confirmed for this journal — check its "
            "research-integrity policy before assuming one isn't required."
        )
    else:
        lines.append("AI-use declaration: not required by this journal.")
    lines.append(f"Notes: {j['notes']}")
    return "\n".join(lines)
