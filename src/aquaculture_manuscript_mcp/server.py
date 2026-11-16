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

from aquaculture_manuscript_mcp import agents, integrity, journals, llm_client, pipeline, research_agents
from aquaculture_manuscript_mcp.tools import (
    bibtex_tools,
    calculators,
    citations,
    docx_export,
    farm_data,
    power as power_tool,
    research_workspace,
    statistics as statistics_tool,
    water_quality,
)

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


# Aquaculture Research Intelligence System — Research Director + 11
# specialists (see research_agents.py and docs/research-intelligence-system.md).


def _make_research_prompt(agent_name: str):
    def research_prompt(task_input: str, project_dir: str = "") -> str:
        project = (
            f"\n\nResearch project folder: {project_dir} (use get_project_status first)."
            if project_dir
            else "\n\nNo research project folder given. Offer to create one if this work will span several steps."
        )
        return f"{research_agents.get_research_prompt(agent_name)}{project}\n\nTask:\n{task_input}"

    return research_prompt


for _name, _spec in research_agents.RESEARCH_AGENTS.items():
    mcp.prompt(name=_name, description=_spec["description"])(_make_research_prompt(_name))


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


@mcp.resource("aquaculture://research-system")
def research_system() -> str:
    """Rules, approval gates and agent roster of the Aquaculture Research
    Intelligence System."""
    roster = "\n".join(
        f"- {name} (phase {spec['phase']}): {spec['description']}"
        for name, spec in research_agents.RESEARCH_AGENTS.items()
    )
    return f"{research_agents.RESEARCH_RULES}\nAgents:\n{roster}\n"


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


# ---------------------------------------------------------------------------
# Real statistics — scipy/statsmodels compute every number; the model only
# interprets the result. Never ask a model to compute a p-value itself.
# ---------------------------------------------------------------------------


@mcp.tool()
def descriptive_stats(values: list[float]) -> dict:
    """n, mean, SD, SEM, min, max, coefficient of variation."""
    return statistics_tool.descriptive_stats(values)


@mcp.tool()
def check_normality(values: list[float]) -> dict:
    """Shapiro-Wilk normality test."""
    return statistics_tool.check_normality(values)


@mcp.tool()
def check_variance_homogeneity(groups: list[list[float]]) -> dict:
    """Levene's test for equal variances across 2+ groups."""
    return statistics_tool.check_variance_homogeneity(groups)


@mcp.tool()
def analyze_ttest(
    group_a: list[float],
    group_b: list[float],
    paired: bool = False,
    equal_var: bool | None = None,
) -> dict:
    """Two-sample t-test. Defaults to Welch's t-test (unequal variances);
    pass equal_var=True to force Student's t-test, or paired=True for a
    paired t-test."""
    return statistics_tool.analyze_ttest(group_a, group_b, paired, equal_var)


@mcp.tool()
def analyze_anova(groups: list[list[float]], group_labels: list[str] | None = None) -> dict:
    """One-way ANOVA (F-test) across 2+ groups."""
    return statistics_tool.analyze_anova(groups, group_labels)


@mcp.tool()
def analyze_kruskal_wallis(groups: list[list[float]], group_labels: list[str] | None = None) -> dict:
    """Kruskal-Wallis H-test — non-parametric alternative to one-way ANOVA."""
    return statistics_tool.analyze_kruskal_wallis(groups, group_labels)


@mcp.tool()
def analyze_posthoc_tukey(groups: list[list[float]], group_labels: list[str] | None = None) -> dict:
    """Tukey HSD pairwise post-hoc comparisons for 3+ groups. Returns every
    pairwise adjusted p-value and CI — not auto-generated significance
    letters (see the tool's module docstring for why that's deliberately
    not implemented)."""
    return statistics_tool.analyze_posthoc_tukey(groups, group_labels)


@mcp.tool()
def calculate_effect_size_cohens_d(group_a: list[float], group_b: list[float]) -> dict:
    """Cohen's d for two independent groups."""
    return statistics_tool.calculate_effect_size_cohens_d(group_a, group_b)


@mcp.tool()
def calculate_eta_squared(groups: list[list[float]]) -> dict:
    """Eta-squared (variance explained) from a one-way ANOVA design."""
    return statistics_tool.calculate_eta_squared(groups)


@mcp.tool()
def calculate_confidence_interval(values: list[float], confidence: float = 0.95) -> dict:
    """Confidence interval for the mean via the t-distribution."""
    return statistics_tool.calculate_confidence_interval(values, confidence)


@mcp.tool()
def analyze_two_way_anova(
    values: list[float],
    factor1: list[str],
    factor2: list[str],
    factor1_name: str = "factor1",
    factor2_name: str = "factor2",
) -> dict:
    """Two-way factorial ANOVA with interaction term (Type II sum of
    squares) — the standard design for trials crossing two treatments (e.g.
    diet x feeding frequency). values/factor1/factor2 are one entry PER
    OBSERVATION (long format), all the same length."""
    return statistics_tool.analyze_two_way_anova(values, factor1, factor2, factor1_name, factor2_name)


@mcp.tool()
def calculate_pearson_correlation(x: list[float], y: list[float]) -> dict:
    """Pearson correlation coefficient between two continuous variables."""
    return statistics_tool.calculate_pearson_correlation(x, y)


# ---------------------------------------------------------------------------
# Manuscript export — assembles real content into a real .docx file. Never
# invents content; a missing section stays missing rather than being filled
# with something plausible-sounding.
# ---------------------------------------------------------------------------


@mcp.tool()
def export_manuscript_docx(
    output_path: str,
    title: str,
    abstract: str,
    keywords: list[str],
    sections: list[dict],
    authors: list[str] | None = None,
    tables: list[dict] | None = None,
    references: list[str] | None = None,
    ai_disclosure: str | None = None,
) -> dict:
    """Write a real .docx manuscript file to output_path, with standard
    academic formatting (Times New Roman, title/abstract/keywords block,
    heading-per-section, native Word tables, hanging-indent references).

    sections: ordered list of {"heading": str, "body": str}.
    tables: optional list of {"caption": str, "headers": [...], "rows": [[...]]}.
    references: optional list of pre-formatted citation strings — this tool
        doesn't format or verify them (see resolve_doi_metadata/validate_bibtex).
    ai_disclosure: optional exact text from draft_ai_disclosure, placed in its
        own section before the references list.
    """
    return docx_export.export_manuscript_docx(
        output_path, title, abstract, keywords, sections, authors, tables, references, ai_disclosure
    )


# ---------------------------------------------------------------------------
# Farm-data intelligence (Phase 1 of the research system). Reads the user's
# own Excel/CSV records; column meanings come from a confirmed column_roles
# mapping, never assumed.
# ---------------------------------------------------------------------------


def _maybe_save(project_dir: str, name: str, result: dict, inputs: dict) -> dict:
    if project_dir:
        result["saved"] = research_workspace.save_analysis(project_dir, name, result, inputs)
    return result


@mcp.tool()
def suggest_column_roles(path: str, sheet: str | None = None) -> dict:
    """Guess which spreadsheet column is the date, cage, species,
    temperature, DO, salinity, feed, mortality, ABW, fish count, etc., from
    column names. A starting point only: confirm every mapping and unit with
    the user before passing it as column_roles to the analysis tools."""
    return farm_data.suggest_column_roles(path, sheet)


@mcp.tool()
def profile_dataset(path: str, sheet: str | None = None) -> dict:
    """Structure of a CSV/Excel dataset: rows, columns, types, missing
    values, duplicates, numeric summaries, categorical levels, date ranges."""
    return farm_data.profile_dataset(path, sheet)


@mcp.tool()
def check_data_quality(
    path: str, column_roles: dict[str, str], sheet: str | None = None, project_dir: str = ""
) -> dict:
    """Quality report for farm records: missing values, duplicate and
    conflicting cage-day rows, physically implausible values, extreme
    outliers, date gaps, ABW drops between samplings, fish counts rising
    without restocking. column_roles maps canonical roles (date, cage,
    species, temperature_c, salinity_ppt, do_mg_l, ph, feed_kg,
    mortality_count, abw_g, fish_count, stocking_density_kg_m3, biomass_kg,
    cost, batch) to the file's column names. Pass project_dir to save the
    report into the research project."""
    result = farm_data.check_data_quality(path, column_roles, sheet)
    return _maybe_save(project_dir, "data_quality", result, {"path": path, "column_roles": column_roles})


@mcp.tool()
def compute_performance_metrics(
    path: str, column_roles: dict[str, str], sheet: str | None = None, project_dir: str = ""
) -> dict:
    """Per-cage and per-sampling-interval SGR, biomass-corrected FCR and
    survival from raw farm records, with the cleaning steps applied listed
    in cleaning_log. Pass project_dir to save the output."""
    result = farm_data.compute_performance_metrics(path, column_roles, sheet)
    return _maybe_save(project_dir, "performance_metrics", result, {"path": path, "column_roles": column_roles})


@mcp.tool()
def discover_research_opportunities(
    path: str,
    column_roles: dict[str, str],
    sheet: str | None = None,
    high_temperature_threshold_c: float | None = None,
    max_lag_days: int = 7,
    project_dir: str = "",
) -> dict:
    """Scan validated farm records for candidate research questions: thermal
    stress and mortality (with time lags), species survival, temperature vs
    growth and FCR, seasonal variation, temperature x DO/salinity
    interaction, stocking density vs growth. Each candidate carries its
    computed evidence, data sufficiency, likely confounders and next step.
    All are observational associations, not findings. Supply
    high_temperature_threshold_c from the user or literature if available."""
    result = farm_data.discover_research_opportunities(
        path, column_roles, sheet, high_temperature_threshold_c, max_lag_days
    )
    return _maybe_save(
        project_dir,
        "research_opportunities",
        result,
        {"path": path, "column_roles": column_roles, "high_temperature_threshold_c": high_temperature_threshold_c, "max_lag_days": max_lag_days},
    )


# ---------------------------------------------------------------------------
# Sample size and power — effect size must come with its source.
# ---------------------------------------------------------------------------


@mcp.tool()
def calculate_sample_size(
    test: str,
    effect_size: float,
    effect_size_source: str,
    alpha: float = 0.05,
    power: float = 0.8,
    k_groups: int = 2,
) -> dict:
    """Experimental units (cages/tanks) needed per group. test:
    "two_sample_t" (effect_size = Cohen's d) or "one_way_anova" (Cohen's f).
    effect_size_source is required: pilot data, farm records or a cited study."""
    return power_tool.calculate_sample_size(test, effect_size, effect_size_source, alpha, power, k_groups)


@mcp.tool()
def calculate_achieved_power(
    test: str,
    effect_size: float,
    effect_size_source: str,
    units_per_group: int,
    alpha: float = 0.05,
    k_groups: int = 2,
) -> dict:
    """Statistical power of a design with a given number of units per group."""
    return power_tool.calculate_achieved_power(test, effect_size, effect_size_source, units_per_group, alpha, k_groups)


# ---------------------------------------------------------------------------
# Research project workspace — memory, data repository, reference library,
# approval gates and audit trail as plain files in one project folder.
# ---------------------------------------------------------------------------


@mcp.tool()
def create_research_project(project_dir: str, name: str, description: str, workflow: str) -> dict:
    """Create a research project folder (data/raw, data/processed, analysis,
    references, documents, decisions, audit trail). workflow:
    "A_question_first" or "B_data_first"."""
    return research_workspace.create_research_project(project_dir, name, description, workflow)


@mcp.tool()
def register_dataset(project_dir: str, source_path: str, description: str) -> dict:
    """Copy an original dataset into the project's data/raw unchanged and
    record its SHA-256 checksum."""
    return research_workspace.register_dataset(project_dir, source_path, description)


@mcp.tool()
def save_analysis(project_dir: str, name: str, result: dict, inputs: dict | None = None) -> dict:
    """Save an analysis result (with its inputs) into the project's analysis folder."""
    return research_workspace.save_analysis(project_dir, name, result, inputs)


@mcp.tool()
def add_verified_reference(project_dir: str, doi: str, relevance_note: str) -> dict:
    """Resolve a DOI in CrossRef and add it to the project's reference
    library. Unresolvable DOIs are refused."""
    return research_workspace.add_verified_reference(project_dir, doi, relevance_note)


@mcp.tool()
def list_references(project_dir: str) -> list[dict]:
    """The project's verified reference library."""
    return research_workspace.list_references(project_dir)


@mcp.tool()
def record_gate_decision(
    project_dir: str, gate: str, status: str, summary: str, rationale: str, user_confirmation: str = ""
) -> dict:
    """Record a decision at approval gate G1_research_question,
    G2_study_design, G3_proposal or G4_publication. Agents may record
    status "proposed". "approved"/"rejected" only after the user explicitly
    decided in the conversation, quoted in user_confirmation."""
    return research_workspace.record_gate_decision(project_dir, gate, status, summary, rationale, user_confirmation)


@mcp.tool()
def log_claim(project_dir: str, claim: str, source_type: str, source_ref: str) -> dict:
    """Add a claim and its origin to the project's audit trail. source_type:
    dataset, analysis, reference, calculation or user_statement."""
    return research_workspace.log_claim(project_dir, claim, source_type, source_ref)


@mcp.tool()
def get_project_status(project_dir: str) -> dict:
    """Datasets, analyses, references, documents, gate status and audit-trail
    size for a research project."""
    return research_workspace.get_project_status(project_dir)


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
