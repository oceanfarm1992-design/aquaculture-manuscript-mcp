"""MCP server exposing RACI-based aquaculture manuscript-writing agents.

Two ways these agents run:

1. As MCP *prompts* — the returned text becomes part of the conversation, and
   whatever model your MCP client already uses (e.g. Claude in Claude Desktop or
   Claude Code) generates the draft. No API token needed for this path.
2. As the `run_agent_with_external_model` *tool* — for when you specifically want
   a different model to do the work. It calls any OpenAI-compatible endpoint using
   a token read from the AQUA_API_KEY environment variable (never passed through
   chat or tool arguments).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import agents, integrity, journals, llm_client, pipeline
from .tools import bibtex_tools, calculators, citations, water_quality

mcp = FastMCP("aquaculture-manuscript-writing")


def _journal_context(journal: str) -> str:
    """Build the journal-specific rules block for a prompt, or — if no valid
    journal was given — an explicit instruction to ask the user rather than
    guess. Never lets a journal-specific number leak in un-asked-for.
    """
    if not journal:
        known = ", ".join(sorted(journals.JOURNALS))
        return (
            "\n\nNo target journal was specified for this task. Before applying "
            "any journal-specific limit (abstract word count, keyword count, "
            "citation style, AI-disclosure requirement), ask the user which "
            f"journal this is for. Known profiles: {known}. For any other "
            "journal, ask the user to supply the limits from that journal's own "
            "author guide rather than assuming they match one of the above."
        )
    try:
        return "\n\n" + journals.format_journal_rules(journal)
    except ValueError as exc:
        return f"\n\n{exc}"


# ---------------------------------------------------------------------------
# Prompts — run on whatever model your MCP client already provides.
# ---------------------------------------------------------------------------


@mcp.prompt(
    name="literature-agent",
    description=agents.AGENTS["literature"]["description"],
)
def literature_agent(task_input: str) -> str:
    return f"{agents.LITERATURE_AGENT_SYSTEM}\n\nTask:\n{task_input}"


@mcp.prompt(
    name="drafting-agent",
    description=agents.AGENTS["drafting"]["description"],
)
def drafting_agent(task_input: str, journal: str = "") -> str:
    return f"{agents.DRAFTING_AGENT_SYSTEM}{_journal_context(journal)}\n\nTask:\n{task_input}"


@mcp.prompt(
    name="results-agent",
    description=agents.AGENTS["results"]["description"],
)
def results_agent(task_input: str) -> str:
    return f"{agents.RESULTS_AGENT_SYSTEM}\n\nTask:\n{task_input}"


@mcp.prompt(
    name="abstract-agent",
    description=agents.AGENTS["abstract"]["description"],
)
def abstract_agent(task_input: str, journal: str = "") -> str:
    return f"{agents.ABSTRACT_AGENT_SYSTEM}{_journal_context(journal)}\n\nTask:\n{task_input}"


@mcp.prompt(
    name="copyedit-agent",
    description=agents.AGENTS["copyedit"]["description"],
)
def copyedit_agent(task_input: str) -> str:
    return f"{agents.COPYEDIT_AGENT_SYSTEM}\n\nTask:\n{task_input}"


@mcp.prompt(
    name="integrity-agent",
    description=agents.AGENTS["integrity"]["description"],
)
def integrity_agent(task_input: str, journal: str = "") -> str:
    return f"{agents.INTEGRITY_AGENT_SYSTEM}{_journal_context(journal)}\n\nTask:\n{task_input}"


@mcp.prompt(
    name="orchestrator-agent",
    description=(
        "Coordinates the other six agents with real handoff rules (e.g. a "
        "citation-overlap finding sends work back to drafting-agent for a "
        "genuine paraphrase) instead of drafting everything in one pass. "
        "Does NOT hand off to make text merely read as less AI-generated."
    ),
)
def orchestrator_agent(task_input: str, journal: str = "") -> str:
    return f"{agents.ORCHESTRATOR_AGENT_SYSTEM}{_journal_context(journal)}\n\nTask:\n{task_input}"


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("aquaculture://human-only-roles")
def human_only_roles() -> str:
    """RACI roles that stay human-only no matter which AI model is used."""
    return agents.HUMAN_ONLY_ROLES


@mcp.resource("aquaculture://handoff-rules")
def handoff_rules() -> str:
    """Trigger -> action rules for when one agent's output should hand work
    to another. Every rule fixes a specific, nameable defect; none exist to
    make accurate text merely read as less AI-generated."""
    return agents.HANDOFF_RULES


@mcp.resource("aquaculture://journals")
def journal_profiles() -> str:
    """Known journal formatting profiles (abstract limit, keyword count,
    citation style, AI-disclosure requirement) — only facts confirmed by
    reading that journal's own author guide."""
    import json

    return json.dumps(journals.JOURNALS, indent=2)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def check_citation_integrity(draft_text: str, source_texts: list[str]) -> dict:
    """Flag verbatim word-runs of 3+ words shared between a draft passage and
    one or more source texts — a real paraphrase check, not AI-detection evasion.
    """
    return integrity.check_overlap(draft_text, source_texts)


@mcp.tool()
def list_supported_journals() -> dict:
    """List known journal formatting profiles (abstract word limit, keyword
    count, citation style, AI-disclosure requirement). Use this to ask the
    user which journal applies before drafting an abstract or AI-disclosure
    statement — never assume one journal's limits apply to another.
    """
    return journals.JOURNALS


@mcp.tool()
def draft_ai_disclosure(tool_name: str, reason: str, journal: str = "") -> str:
    """Produce the 'Declaration of generative AI use' statement text for the
    given tool name and reason it was used — IF the target journal is known to
    require one. Pass `journal` (a key from list_supported_journals) so this
    can check; without it, this returns a prompt to ask the user instead of
    guessing whether a disclosure is required or what it should say.
    """
    if not journal:
        known = ", ".join(sorted(journals.JOURNALS))
        return (
            "No journal specified. Ask the user which journal this manuscript "
            f"is going to before drafting a disclosure statement. Known "
            f"profiles: {known}. For any other journal, check its research-"
            "integrity policy directly rather than assuming Elsevier's wording "
            "applies."
        )
    profile = journals.get_journal(journal)
    if profile["ai_disclosure_required"] is True and profile["ai_disclosure_template"]:
        return agents.ai_disclosure_statement(tool_name, reason)
    if profile["ai_disclosure_required"] is None:
        return (
            f"AI-disclosure requirement not confirmed for {profile['display_name']}. "
            f"{profile['notes']}"
        )
    return f"{profile['display_name']} does not require an AI-use declaration."


@mcp.tool()
def run_agent_with_external_model(
    agent_name: str,
    task_input: str,
    journal: str = "",
    model: str | None = None,
    base_url: str | None = None,
) -> str:
    """Run one of the six manuscript-writing agents against an external
    OpenAI-compatible model, instead of the model your MCP client already uses.

    The API key is never passed as an argument here — set it once as the
    AQUA_API_KEY environment variable in your MCP client's server config.

    agent_name: one of "literature", "drafting", "results", "abstract",
        "copyedit", "integrity".
    journal: a key from list_supported_journals, for agents whose rules are
        journal-specific (abstract, drafting, integrity). Leave blank and the
        agent will ask the user which journal applies instead of guessing.
    model: overrides the AQUA_MODEL environment variable for this call.
    base_url: overrides the AQUA_BASE_URL environment variable for this call
        (defaults to https://api.openai.com/v1; point this at any
        OpenAI-compatible endpoint, e.g. a local Ollama/LM Studio server).
    """
    system_prompt = agents.get_system_prompt(agent_name) + _journal_context(journal)
    return llm_client.call(system_prompt, task_input, model=model, base_url=base_url)


@mcp.tool()
def run_pipeline(
    task_input: str,
    source_texts: list[str] | None = None,
    journal: str = "",
    max_revisions: int = 2,
    model: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Draft, then automatically hand off to a revision step ONLY when a real
    citation-overlap defect is found, then copyedit — a concrete, bounded
    version of handoff rules 1 and 2 in aquaculture://handoff-rules.

    Runs against an external OpenAI-compatible model via AQUA_API_KEY (see
    run_agent_with_external_model). Returns the final text plus a full log of
    every step and what triggered it, so nothing happens silently. This loop
    never rewrites text to sound "more human" — it only fixes verbatim overlap
    with a source, and stops (reporting the issue) after max_revisions if the
    overlap isn't resolved.

    source_texts: reference texts to check the draft against. Omit if you
        don't have specific sources to check overlap against yet.
    """
    return pipeline.run_pipeline(
        task_input,
        source_texts=source_texts,
        journal=journal,
        max_revisions=max_revisions,
        model=model,
        base_url=base_url,
    )


# ---------------------------------------------------------------------------
# Domain calculators — pure math, no LLM call, no fabrication risk.
# ---------------------------------------------------------------------------


@mcp.tool()
def calculate_fcr(
    feed_given_g: float,
    initial_weight_g: float,
    final_weight_g: float,
    dry_matter_fraction: float = 1.0,
) -> dict:
    """Apparent feed conversion ratio (Yossa 2014's worked formula):
    FCR = (feed given x dry matter fraction) / (final weight - initial weight).
    """
    return calculators.calculate_fcr(feed_given_g, initial_weight_g, final_weight_g, dry_matter_fraction)


@mcp.tool()
def calculate_biomass_corrected_fcr(
    feed_given_g: float,
    initial_biomass_g: float,
    final_biomass_g: float,
    dead_or_removed_biomass_g: float = 0.0,
    dry_matter_fraction: float = 1.0,
) -> dict:
    """FCR corrected for biomass removed mid-trial (mortalities/sampling).
    Naming ("bFCR"/"corrected FCR") varies by source — state your exact
    correction method in Methods rather than relying on a label."""
    return calculators.calculate_biomass_corrected_fcr(
        feed_given_g, initial_biomass_g, final_biomass_g, dead_or_removed_biomass_g, dry_matter_fraction
    )


@mcp.tool()
def calculate_economic_fcr(
    feed_given_g: float,
    feed_cost_per_kg: float,
    weight_gain_g: float,
    product_value_per_kg: float,
) -> dict:
    """Economic FCR: feed cost / value of weight gain."""
    return calculators.calculate_economic_fcr(feed_given_g, feed_cost_per_kg, weight_gain_g, product_value_per_kg)


@mcp.tool()
def calculate_sgr(initial_weight_g: float, final_weight_g: float, days: float) -> dict:
    """Specific growth rate: SGR (%/day) = (ln(final) - ln(initial)) / days x 100."""
    return calculators.calculate_sgr(initial_weight_g, final_weight_g, days)


@mcp.tool()
def calculate_stocking_density(
    biomass_kg: float,
    volume_m3: float | None = None,
    area_m2: float | None = None,
) -> dict:
    """Stocking density as biomass per volume (kg/m3) and/or per area (kg/m2)."""
    return calculators.calculate_stocking_density(biomass_kg, volume_m3, area_m2)


@mcp.tool()
def calculate_survival_rate(initial_count: int, final_count: int) -> dict:
    """Survival % and cumulative mortality % from initial and final counts."""
    return calculators.calculate_survival_rate(initial_count, final_count)


@mcp.tool()
def calculate_unionized_ammonia(
    total_ammonia_nitrogen_mg_l: float, ph: float, temperature_c: float
) -> dict:
    """Un-ionized ammonia (NH3-N) fraction and concentration from TAN, pH,
    and temperature (Emerson et al. 1975 equilibrium equation)."""
    return water_quality.calculate_unionized_ammonia(total_ammonia_nitrogen_mg_l, ph, temperature_c)


@mcp.tool()
def list_water_quality_reference_species() -> dict:
    """Species/parameters with a cited water-quality reference range
    available. A species not listed here has no sourced range in this tool —
    that means "not yet sourced", not "no threshold exists"."""
    return water_quality.list_supported_species()


@mcp.tool()
def check_water_parameter(species: str, parameter: str, measured_value: float) -> dict:
    """Check a measured water-quality value against a cited reference range
    (see list_water_quality_reference_species for what's covered). Always
    returns the source and a caveat — never a bare pass/fail."""
    return water_quality.check_water_parameter(species, parameter, measured_value)


# ---------------------------------------------------------------------------
# Real citation lookups (CrossRef) and BibTeX validation.
# ---------------------------------------------------------------------------


@mcp.tool()
def resolve_doi_metadata(doi: str) -> dict:
    """Fetch real citation metadata for a DOI from the CrossRef registry.
    Raises if the DOI isn't registered — treat that as "could not verify
    this citation", not as permission to cite it anyway."""
    return citations.resolve_doi_metadata(doi)


@mcp.tool()
def search_citations(query: str, rows: int = 5) -> list[dict]:
    """Search CrossRef for real candidate works matching a topic/author/title
    query. Use this to find a verifiable DOI before citing something you only
    recall the gist of — confirm a result actually supports your claim before
    citing it; don't cite from this list on title match alone."""
    return citations.search_works(query, rows)


@mcp.tool()
def validate_bibtex(bibtex_text: str) -> dict:
    """Validate a .bib file: parse errors, missing required fields per entry
    type, duplicate keys, and entries with no DOI/URL to independently verify."""
    return bibtex_tools.validate_bibtex(bibtex_text)


def main() -> None:
    import os

    transport = os.environ.get("AQUA_TRANSPORT", "stdio")
    if transport not in ("stdio", "sse", "streamable-http"):
        raise ValueError(
            f"Unknown AQUA_TRANSPORT '{transport}'. Use 'stdio' (default, for "
            "Claude Desktop/Code and other local MCP clients), 'sse', or "
            "'streamable-http' (for remote/cloud deployment)."
        )
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
