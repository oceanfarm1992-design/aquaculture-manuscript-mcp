"""Concrete agent-to-agent handoff loop for the external-model (BYOK) path.

Implements handoff rules 1 and 2 from agents.HANDOFF_RULES mechanically:
draft -> copyedit -> citation-integrity check -> (if overlap found) revise ->
re-check -> stop once clean or max_revisions is reached.

This only fixes a nameable defect (verbatim source overlap) by asking for a
genuine paraphrase. It never rewrites text to read as "more human" for its own
sake — see agents.HANDOFF_RULES for the boundary this loop is built to.
"""

from __future__ import annotations

from . import agents, integrity, journals, llm_client


def _journal_block(journal: str) -> str:
    if not journal:
        return ""
    try:
        return "\n\n" + journals.format_journal_rules(journal)
    except ValueError:
        return ""


def run_pipeline(
    task_input: str,
    source_texts: list[str] | None = None,
    journal: str = "",
    max_revisions: int = 2,
    model: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Draft, copyedit, and citation-check a section, looping a revision back
    to the drafting step only when a real verbatim-overlap defect is found.

    Returns a dict with the final text and a step-by-step log, so the caller
    (and the user) can see exactly what triggered each handoff — nothing here
    happens silently.
    """
    source_texts = source_texts or []
    journal_block = _journal_block(journal)
    log: list[dict] = []

    draft_system = agents.DRAFTING_AGENT_SYSTEM + journal_block
    draft = llm_client.call(draft_system, task_input, model=model, base_url=base_url)
    log.append({"step": "drafting-agent", "action": "initial draft", "output": draft})

    revisions_used = 0
    while True:
        check = integrity.check_overlap(draft, source_texts) if source_texts else {
            "clean": True,
            "findings": [],
            "overlap_count": 0,
        }
        log.append({"step": "check_citation_integrity", "action": "scan draft", "result": check})

        if check["clean"] or revisions_used >= max_revisions:
            break

        flagged = "; ".join(f'"{f["phrase"]}"' for f in check["findings"])
        revision_task = (
            f"The following phrase(s) verbatim-overlap a source and must be "
            f"paraphrased in original sentence structure (not synonym-swapped): "
            f"{flagged}\n\nHere is the current draft to revise:\n\n{draft}"
        )
        draft = llm_client.call(draft_system, revision_task, model=model, base_url=base_url)
        revisions_used += 1
        log.append(
            {
                "step": "drafting-agent",
                "action": f"revision {revisions_used} (triggered by citation-overlap handoff)",
                "output": draft,
            }
        )

    copyedit_system = agents.COPYEDIT_AGENT_SYSTEM
    final_text = llm_client.call(copyedit_system, draft, model=model, base_url=base_url)
    log.append({"step": "copyedit-agent", "action": "final polish", "output": final_text})

    return {
        "final_text": final_text,
        "revisions_used": revisions_used,
        "clean": log[-2]["result"]["clean"] if source_texts else None,
        "log": log,
    }
