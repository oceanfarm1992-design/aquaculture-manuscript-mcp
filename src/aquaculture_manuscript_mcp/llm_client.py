"""Thin client for calling any OpenAI-compatible chat-completions endpoint.

The API key is read ONLY from the AQUA_API_KEY environment variable, set by the
user in their MCP client's server config (the `env` block) or shell environment.
It is never accepted as a tool argument, so it never passes through the model's
context or any conversation log.
"""

from __future__ import annotations

import os

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60.0


class MissingAPIKeyError(RuntimeError):
    pass


class MissingModelError(RuntimeError):
    pass


def call(
    system_prompt: str,
    user_input: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    api_key = os.environ.get("AQUA_API_KEY")
    if not api_key:
        raise MissingAPIKeyError(
            "AQUA_API_KEY environment variable is not set. Set it in your MCP "
            "client's server config (env block) or shell environment — never "
            "pass it as a tool argument or in chat."
        )

    resolved_base_url = (base_url or os.environ.get("AQUA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    resolved_model = model or os.environ.get("AQUA_MODEL")
    if not resolved_model:
        raise MissingModelError(
            "No model specified. Set the AQUA_MODEL environment variable, or "
            "pass a model name explicitly to this tool."
        )

    response = httpx.post(
        f"{resolved_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]
