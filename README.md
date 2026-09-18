# Aquaculture Manuscript MCP

An [MCP](https://modelcontextprotocol.io) server that exposes six aquaculture
manuscript-writing agents — derived from this project's RACI matrix — to Claude
Desktop, Claude Code, or any other MCP-compatible client. Once installed and
connected, the agents show up inside your normal chat; no copy-pasting prompts.

## What it is

Six agents, one per AI-automatable role in the RACI matrix:

| Agent | RACI role | Does |
|---|---|---|
| `literature-agent` | Information & Lit Experts | Finds/vets real citations, never fabricates them |
| `drafting-agent` | Writing & Editorial | Drafts Introduction, Materials & Methods, Discussion |
| `results-agent` | Writing & Editorial (from supplied data) | Turns your real data/tables into Results prose |
| `abstract-agent` | Writing & Editorial | Title, Abstract (<=250 words), Keywords |
| `copyedit-agent` | Writing & Editorial | Sentence-level polishing, never changes claims/data |
| `integrity-agent` | AI & Plagiarism | Real citation-overlap check + drafts the mandatory AI-use disclosure |

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
git clone https://github.com/<your-org>/aquaculture-manuscript-mcp.git
cd aquaculture-manuscript-mcp
pip install -e .
```

This installs the `aquaculture-manuscript-mcp` command, which runs the server
over stdio (the standard MCP transport for desktop clients).

## Connect it to Claude Desktop

Edit Claude Desktop's config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an entry under `mcpServers`:

```json
{
  "mcpServers": {
    "aquaculture-manuscript-writing": {
      "command": "aquaculture-manuscript-mcp"
    }
  }
}
```

Restart Claude Desktop. The six agents now appear as prompts you can attach to a
conversation (paperclip / prompts menu), and the two tools (citation-integrity
check, AI-disclosure drafting) are available for Claude to call directly.

When run this way, **the prompts use Claude itself** to draft — no API key needed.

## Connect it to Claude Code or any other MCP client

Any MCP-compatible client works the same way — point it at the
`aquaculture-manuscript-mcp` command over stdio. Consult that client's docs for
where it keeps its MCP server config.

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

## Development

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
aquaculture-manuscript-mcp   # runs the stdio server directly, for manual testing
```

## License

MIT — see `LICENSE`.
