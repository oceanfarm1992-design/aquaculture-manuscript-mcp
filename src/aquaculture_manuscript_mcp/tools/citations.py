"""Real citation lookups against the CrossRef public registry (api.crossref.org).

This exists specifically to back the literature-agent's "never fabricate a
citation" rule with an actual external source instead of model memory. A
result from here is a real, registered work; anything the model can't find
here should be treated as unverified, not cited as fact.
"""

from __future__ import annotations

import httpx

CROSSREF_BASE = "https://api.crossref.org"
# CrossRef asks polite-pool users to identify themselves via User-Agent.
_HEADERS = {"User-Agent": "aquaculture-manuscript-mcp/0.1 (https://github.com/oceanfarm1992-design/aquaculture-manuscript-mcp)"}
_TIMEOUT = 20.0


def resolve_doi_metadata(doi: str) -> dict:
    """Fetch real metadata for a DOI from CrossRef. Raises if the DOI isn't
    registered — that means the citation could not be verified, not that it's
    safe to cite anyway.
    """
    doi = doi.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    response = httpx.get(f"{CROSSREF_BASE}/works/{doi}", headers=_HEADERS, timeout=_TIMEOUT)
    if response.status_code == 404:
        raise ValueError(f"DOI '{doi}' is not registered in CrossRef — cannot verify this citation")
    response.raise_for_status()
    message = response.json()["message"]

    authors = [
        f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
        for a in message.get("author", [])
    ]
    return {
        "doi": message.get("DOI"),
        "title": (message.get("title") or [None])[0],
        "authors": authors,
        "container_title": (message.get("container-title") or [None])[0],
        "year": _extract_year(message),
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "page": message.get("page"),
        "publisher": message.get("publisher"),
        "type": message.get("type"),
        "url": message.get("URL"),
    }


def search_works(query: str, rows: int = 5) -> list[dict]:
    """Search CrossRef for candidate works matching a free-text query (title/
    author/topic). Use this to find a real DOI before citing something you
    only recall the gist of — never cite from this list without confirming
    the result actually supports the claim you're making.
    """
    if rows < 1 or rows > 20:
        raise ValueError("rows must be between 1 and 20")
    response = httpx.get(
        f"{CROSSREF_BASE}/works",
        params={"query": query, "rows": rows},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    items = response.json()["message"]["items"]

    results = []
    for message in items:
        authors = [
            f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            for a in message.get("author", [])
        ]
        results.append(
            {
                "doi": message.get("DOI"),
                "title": (message.get("title") or [None])[0],
                "authors": authors,
                "container_title": (message.get("container-title") or [None])[0],
                "year": _extract_year(message),
                "score": message.get("score"),
            }
        )
    return results


def _extract_year(message: dict) -> int | None:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = message.get(key, {}).get("date-parts")
        if parts and parts[0]:
            return parts[0][0]
    return None
