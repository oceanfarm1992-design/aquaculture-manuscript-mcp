"""Mechanical citation-integrity checking — pure text comparison, no LLM call.

Flags runs of 3+ consecutive words shared between a draft passage and a source
text, which is the threshold this project's style guide treats as "not actually
paraphrased." This is a genuine originality check, not an AI-detection-evasion
tool.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def check_overlap(
    draft_text: str, source_texts: list[str], min_run: int = 3
) -> dict:
    """Find verbatim word-runs of at least `min_run` words shared between the
    draft and any supplied source text.

    Returns a dict with a list of findings, each naming the source index and the
    overlapping phrase, so the drafting/integrity agent can point at exactly what
    to paraphrase.
    """
    draft_tokens = _tokenize(draft_text)
    draft_ngrams = _ngrams(draft_tokens, min_run)

    findings = []
    for idx, source in enumerate(source_texts):
        source_tokens = _tokenize(source)
        source_ngrams = _ngrams(source_tokens, min_run)
        shared = draft_ngrams & source_ngrams
        for phrase in shared:
            findings.append(
                {
                    "source_index": idx,
                    "phrase": " ".join(phrase),
                }
            )

    findings.sort(key=lambda f: (f["source_index"], f["phrase"]))
    return {
        "min_run_length": min_run,
        "overlap_count": len(findings),
        "findings": findings,
        "clean": len(findings) == 0,
    }
