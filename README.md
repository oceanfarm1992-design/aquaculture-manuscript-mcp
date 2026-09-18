# Aquaculture Manuscript MCP

An [MCP](https://modelcontextprotocol.io) server that exposes aquaculture
manuscript-writing agents — derived from this project's RACI matrix — to Claude
Desktop, Claude Code, or any other MCP-compatible client. Once installed and
connected, the agents show up inside your normal chat; no copy-pasting prompts.
They also hand work to each other on real defects (see "Agents talking to each
other" below) rather than drafting everything in one uncoordinated pass.

## What it is

Six writing agents, one per AI-automatable role in the RACI matrix, plus an
orchestrator that hands work between them:

| Agent | RACI role | Does |
|---|---|---|
| `literature-agent` | Information & Lit Experts | Finds/vets real citations, never fabricates them |
| `drafting-agent` | Writing & Editorial | Drafts Introduction, Materials & Methods, Discussion |
| `results-agent` | Writing & Editorial (from supplied data) | Turns your real data/tables into Results prose |
| `abstract-agent` | Writing & Editorial | Title, Abstract, Keywords (journal-specific limits) |
| `copyedit-agent` | Writing & Editorial | Sentence-level polishing, never changes claims/data |
| `integrity-agent` | AI & Plagiarism | Real citation-overlap check + journal-aware AI-use disclosure |
| `orchestrator-agent` | — | Coordinates the six above using real handoff rules |

Roles that stay human-only regardless of model (PI accountability, IACUC/legal,
physical data collection, grant sign-off, peer review, running an actual
similarity-scan tool) are listed via the `aquaculture://human-only-roles`
resource — the server does not attempt them.

**Journal rules are not hard-coded.** Abstract word limits, keyword counts,
citation style, and whether an AI-use declaration is required all differ by
journal (confirmed: Elsevier's *Aquaculture* requires a 250-word abstract, 5-7
keywords, and a mandatory AI-disclosure statement; Wiley's *Aquaculture
Research* is a 200-word abstract, 4-6 keywords, APA citations, and its
AI-disclosure policy wasn't visible in the guide pages checked). The
`abstract-agent`, `drafting-agent`, and `integrity-agent` prompts take an
optional `journal` argument (a key from `list_supported_journals`); without
one, they're instructed to ask you which journal applies rather than default
to a number from a different one.

**This server does not help evade AI-detection or plagiarism-scan tools.** Every
agent is built to disclose AI assistance (see `integrity-agent` /
`draft_ai_disclosure`) and to never fabricate data or citations. See
`src/aquaculture_manuscript_mcp/agents.py` for the exact rules baked into each one.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/oceanfarm1992-design/aquaculture-manuscript-mcp.git
cd aquaculture-manuscript-mcp
pip install -e .
```

This installs the `aquaculture-manuscript-mcp` command, which runs the server
over stdio (the standard MCP transport for desktop clients).

### Find the right `command` path for your MCP client — read this before wiring it up

This is the step that actually trips people up, so it gets its own section.
**Your MCP client (Claude Desktop, Claude Code, etc.) launches the server as
its own process — it does NOT inherit your terminal's activated virtualenv.**

- If you installed with **no virtualenv** (system/user Python) and your
  Python Scripts/bin directory is on `PATH`, the bare command
  `aquaculture-manuscript-mcp` will work as-is in the config below.
- If you installed inside a **virtualenv** (recommended, and what these docs'
  own testing used), the bare command will silently fail to launch — the
  client has no way to find it. Use the **absolute path** to that venv's copy
  of the entry point instead:
  - Windows: `<path-to-repo>\.venv\Scripts\aquaculture-manuscript-mcp.exe`
  - macOS/Linux: `<path-to-repo>/.venv/bin/aquaculture-manuscript-mcp`

  Find it quickly with `where aquaculture-manuscript-mcp` (Windows, venv
  activated) or `which aquaculture-manuscript-mcp` (macOS/Linux).

## Connect it to Claude Desktop

Edit Claude Desktop's config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an entry under `mcpServers`, using whichever `command` applies from the
section above (Windows paths need double backslashes in JSON):

```json
{
  "mcpServers": {
    "aquaculture-manuscript-writing": {
      "command": "aquaculture-manuscript-mcp"
    }
  }
}
```

or, for a virtualenv install on Windows:

```json
{
  "mcpServers": {
    "aquaculture-manuscript-writing": {
      "command": "C:\\path\\to\\aquaculture-manuscript-mcp\\.venv\\Scripts\\aquaculture-manuscript-mcp.exe"
    }
  }
}
```

Restart Claude Desktop. The six agents now appear as prompts you can attach to a
conversation (paperclip / prompts menu), and the two tools (citation-integrity
check, AI-disclosure drafting) are available for Claude to call directly.

When run this way, **the prompts use Claude itself** to draft — no API key needed.

## Connect it to Claude Code or any other MCP client

Any MCP-compatible client works the same way — point it at the same `command`
(same caveat about venv vs. system Python applies). For Claude Code
specifically, add the same `mcpServers` block to a `.mcp.json` file in your
project root instead of editing a global config file. Consult other clients'
docs for where they keep MCP server config.

### Verify it's working before wiring it into a client

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) can
connect directly to the installed command and let you call tools by hand —
useful for confirming the install before trusting a client's UI. Its exact
CLI flags differ between v1 and v2 and are moving targets, so check its own
README for the current invocation; point it at the same `command` path from
the section above.

## Using a different / specific model (bring your own token)

If you want a particular agent to run against a specific model — not just
whatever model your MCP client happens to use — call the
`run_agent_with_external_model` tool. It talks to **any OpenAI-compatible
endpoint** (OpenAI itself, a local Ollama/LM Studio server, or any other provider
that mirrors the OpenAI chat-completions API).

Set these as environment variables in your MCP client's server config (`env`
block) — **never** pass the API key as a tool argument or in chat:

```json
{
  "mcpServers": {
    "aquaculture-manuscript-writing": {
      "command": "aquaculture-manuscript-mcp",
      "env": {
        "AQUA_API_KEY": "sk-...",
        "AQUA_BASE_URL": "https://api.openai.com/v1",
        "AQUA_MODEL": "gpt-4o-mini"
      }
    }
  }
}
```

`AQUA_BASE_URL` defaults to `https://api.openai.com/v1` if omitted; point it at
any other OpenAI-compatible base URL to use a different provider. See
`.env.example` for a local-development template (useful if you run/test the
server outside an MCP client).

## Agents talking to each other

The agents hand work back and forth when a *specific, nameable defect* is
found — not to make accurate text merely read as less AI-generated. Full rules
are in `aquaculture://handoff-rules` (also in `agents.HANDOFF_RULES`); the
short version:

- `drafting-agent` output goes to `copyedit-agent`, then `integrity-agent`.
- `integrity-agent` (or `check_citation_integrity`) finds a verbatim overlap
  with a source -> the flagged phrase goes back to `drafting-agent` with an
  explicit instruction to paraphrase in original sentence structure -> re-check.
- `integrity-agent` finds an unsupported *background* claim -> handed to
  `literature-agent` to find a real citation. An unsupported *results* claim is
  never handed off to be invented — the loop stops and asks you instead.
- `abstract-agent`'s numbers get cross-checked against `results-agent`'s actual
  output before anything is called final.

Two ways to use this:

1. **`orchestrator-agent` prompt** — attach it in Claude Desktop (or any MCP
   client) instead of an individual agent prompt. It instructs the connected
   model to call the other prompts/tools in the right order and actually
   perform the handoffs, using no API key (it runs on your client's model).
2. **`run_pipeline` tool** — a concrete, bounded implementation of the
   citation-overlap handoff (rules 1–2 above) that runs headlessly against an
   external model via `AQUA_API_KEY`: draft -> check -> revise (only if a real
   overlap was found) -> re-check -> copyedit, capped at `max_revisions` and
   returning a full step-by-step log so nothing happens silently.

## Tools reference

- `check_citation_integrity(draft_text, source_texts)` — flags any run of 3+
  consecutive words shared between your draft and a source, no LLM call
  involved. A real paraphrase check.
- `list_supported_journals()` — returns the known journal profiles (abstract
  limit, keyword count, citation style, AI-disclosure requirement), each with
  only facts confirmed by actually reading that journal's author guide.
- `draft_ai_disclosure(tool_name, reason, journal="")` — returns the exact
  "Declaration of generative AI use" paragraph text, but only once `journal`
  identifies a profile confirmed to require one; otherwise it tells you to ask
  rather than guessing.
- `run_agent_with_external_model(agent_name, task_input, journal="", model=None, base_url=None)`
  — runs any of the six agents against an external OpenAI-compatible model using
  `AQUA_API_KEY`.
- `run_pipeline(task_input, source_texts=None, journal="", max_revisions=2, model=None, base_url=None)`
  — the bounded draft/check/revise/copyedit loop described above; returns
  `{final_text, revisions_used, clean, log}`.

### Domain calculators (pure math, no LLM call, fully unit-tested)

- `calculate_fcr`, `calculate_biomass_corrected_fcr`, `calculate_economic_fcr`
  — feed conversion ratio and its variants (formula documented per function;
  terminology for "eFCR"/"bFCR" varies by source, so state your exact method
  in Methods rather than relying on the label).
- `calculate_sgr` — specific growth rate, `SGR = (ln(Wf) - ln(Wi)) / days x 100`.
- `calculate_stocking_density` — biomass per volume (kg/m3) and/or area (kg/m2).
- `calculate_survival_rate` — survival % and cumulative mortality %.
- `calculate_unionized_ammonia` — NH3-N fraction/concentration from TAN, pH,
  and temperature (Emerson et al. 1975 equilibrium equation — general aquatic
  chemistry, not species-specific).
- `check_water_parameter(species, parameter, measured_value)` /
  `list_water_quality_reference_species()` — checks a value against a cited
  reference range. **Only two species are covered** (Nile tilapia, Pacific
  whiteleg shrimp) because those are what a source-backed range could
  actually be found for — an unlisted species means "not yet sourced," not
  "no threshold exists." Every result carries its source and a caveat that
  it's a sanity check, not a citable threshold by itself.

### Real citation tools

- `resolve_doi_metadata(doi)` / `search_citations(query, rows=5)` — real
  lookups against the CrossRef registry (api.crossref.org), so the
  literature-agent's "never fabricate a citation" rule has an actual external
  source to check against instead of relying on model memory.
- `validate_bibtex(bibtex_text)` — parse errors, missing required fields per
  entry type, duplicate keys, entries with no DOI/URL.

### Real statistics (scipy/statsmodels — the model never computes a p-value itself)

- `descriptive_stats`, `check_normality` (Shapiro-Wilk), `check_variance_homogeneity` (Levene's).
- `analyze_ttest` (Welch's by default), `analyze_anova`, `analyze_kruskal_wallis`.
- `analyze_posthoc_tukey` — pairwise Tukey HSD with adjusted p-values and CIs
  for 3+ groups. **Does not auto-generate a/b/c significance letters.**
  Naive greedy letter-assignment gets this wrong in cases where a group must
  share a letter with two other groups that are themselves significantly
  different from each other — this is exactly why R's `multcompView` package
  exists as dedicated, carefully-verified machinery rather than a one-line
  loop. Getting it wrong would silently mislabel a published table, so this
  tool returns the full, unambiguous pairwise matrix instead and leaves
  letter-assignment to a human (or a future, properly-verified
  implementation) — see the module docstring in `tools/statistics.py`.
- `calculate_effect_size_cohens_d`, `calculate_eta_squared`,
  `calculate_confidence_interval`.

## Deployment

Default transport is `stdio` (what Claude Desktop/Code and most local MCP
clients expect). For a remote/cloud deployment, set `AQUA_TRANSPORT=sse` or
`AQUA_TRANSPORT=streamable-http` in the environment before running the
server. A `Dockerfile` is included:

```bash
docker build -t aquaculture-manuscript-mcp .
docker run -e AQUA_TRANSPORT=stdio -i aquaculture-manuscript-mcp
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest -q                    # or: pytest -q -m "not network" to skip CrossRef calls
aquaculture-manuscript-mcp   # runs the stdio server directly, for manual testing
```

`mcp dev src/aquaculture_manuscript_mcp/server.py` also works (launches the
MCP Inspector against this file directly) as long as the package itself is
installed in the environment `mcp dev` runs in — it imports `server.py` in a
way that requires `aquaculture_manuscript_mcp` to already be a real,
importable package, not just a loose file.

## License

MIT — see `LICENSE`.
