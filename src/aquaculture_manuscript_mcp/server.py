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

from . import agents, integrity, llm_client

mcp = FastMCP("aquaculture-manuscript-writing")


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
def drafting_agent(task_input: str) -> str:
    return f"{agents.DRAFTING_AGENT_SYSTEM}\n\nTask:\n{task_input}"


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
def abstract_agent(task_input: str) -> str:
    return f"{agents.ABSTRACT_AGENT_SYSTEM}\n\nTask:\n{task_input}"


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
def integrity_agent(task_input: str) -> str:
    return f"{agents.INTEGRITY_AGENT_SYSTEM}\n\nTask:\n{task_input}"


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("aquaculture://human-only-roles")
def human_only_roles() -> str:
    """RACI roles that stay human-only no matter which AI model is used."""
    return agents.HUMAN_ONLY_ROLES


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
def draft_ai_disclosure(tool_name: str, reason: str) -> str:
    """Produce the mandatory 'Declaration of generative AI use' statement text
    (Elsevier-style) for the given tool name and reason it was used.
    """
    return agents.ai_disclosure_statement(tool_name, reason)


@mcp.tool()
def run_agent_with_external_model(
    agent_name: str,
    task_input: str,
    model: str | None = None,
    base_url: str | None = None,
) -> str:
    """Run one of the six manuscript-writing agents against an external
    OpenAI-compatible model, instead of the model your MCP client already uses.

    The API key is never passed as an argument here — set it once as the
    AQUA_API_KEY environment variable in your MCP client's server config.

    agent_name: one of "literature", "drafting", "results", "abstract",
        "copyedit", "integrity".
    model: overrides the AQUA_MODEL environment variable for this call.
    base_url: overrides the AQUA_BASE_URL environment variable for this call
        (defaults to https://api.openai.com/v1; point this at any
        OpenAI-compatible endpoint, e.g. a local Ollama/LM Studio server).
    """
    system_prompt = agents.get_system_prompt(agent_name)
    return llm_client.call(system_prompt, task_input, model=model, base_url=base_url)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
